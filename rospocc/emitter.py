import io
import os
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Dict, Optional

import abi
from emitter_calls import emit_call
from emitter_expr import emit_expr as emit_expression
from emitter_intrinsics import intrinsic_break, intrinsic_lb, intrinsic_sb
from emitter_registers import alloc_var_reg, ensure_var_reg, load_imm
from emitter_stmt import emit_statement as emit_statement_impl
from register_allocator import RegAllocation, RegisterAllocator
from tracked_writer import TrackedWriter


def _escape_ros_string(value: str) -> str:
    # Keep .STR payload as a single escaped token for the assembler grammar.
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
        .replace("\0", "\\0")
    )


class Emitter:
    def __init__(
        self,
        source_file: Optional[str] = None,
        source_lines: Optional[list] = None,
        label_namespace: str = "",
    ):
        self.label_counter = 0
        self.label_namespace = label_namespace
        self.reg_free = list(abi.TEMP_REGS)
        self.var_regs = {}
        # track simple type hints: var name -> 'char_ptr' | 'int_ptr' | 'int' | 'char' | struct type name
        self.var_types = {}
        # globals type hints collected from translation unit
        self.global_types = {}
        # global symbol -> label/immediate value to materialize when referenced in code
        self.global_value_inits = {}
        # function return type hints collected from translation unit
        self.func_return_types = {}
        # struct type definitions: name -> {members: [...], size: int}
        self.struct_types = {}
        # collected global space directives for lifted large buffers
        self.global_spaces = []
        # inline functions: name -> function definition
        self.inline_functions = {}
        # inline constants: name -> constant value
        self.inline_constants = {}
        # intrinsic handlers: name -> callable(args, out)
        self.intrinsics = {
            "__lb": self._intrinsic_lb,
            "__sb": self._intrinsic_sb,
            "__break": self._intrinsic_break,
        }
        # Source tracking for debug info
        self.source_file = source_file
        self.source_lines = source_lines or []
        self.tracked_writer = None
        # Register allocation sidecar tracking
        self.register_allocator = RegisterAllocator()
        self.current_context_origin: Optional[str] = None
        self.temp_counter = 0
        # Spill tracking for temporary allocations under register pressure.
        self._spill_depth = {}
        # Depth of expression-temporary borrows for registers that may also map vars.
        self._borrowed_temp_depth = {}
        # For spill-borrowed registers, preserve and restore var aliases across PUSH/POP.
        self._spilled_var_aliases = {}
        # Global spill push order for safe stack-correct restore logic.
        self._spill_stack = []
        # Pinned regs are protected from spill while their current value is needed.
        self._pinned_regs = {}
        # CFG-aware statement liveness: live-after sets plus per-statement read counts.
        self._stmt_live_after = {}
        self._statement_stack = []
        # Control-flow aware liveness guards.
        self._control_flow_depth = 0
        self._protected_var_depth = {}
        # Stack of block scopes used to release block-local declarations safely.
        self._var_scope_stack = []
        # Flag to indicate we're inside an inline function expansion
        self._in_inline_context = False
        # Target register for inline function return value
        self._inline_return_target = None

    def _get_source_text(self, line_num: int) -> str:
        """Get the source text for a given line number (1-indexed)."""
        if 1 <= line_num <= len(self.source_lines):
            return self.source_lines[line_num - 1]
        return ""

    def _set_source_context(self, node: Dict[str, Any], out):
        """Set source context based on node metadata."""
        if isinstance(node, dict) and "_line" in node:
            line_num = node["_line"]
            source_text = self._get_source_text(line_num)
            if hasattr(out, "set_source_context"):
                out.set_source_context(line_num, source_text)
        elif hasattr(out, "set_source_context"):
            out.set_source_context(None, None)

    # helper: write an immediate into a register
    def _load_imm(self, reg: str, value, out):
        load_imm(out, reg, value)

    # helper: allocate a register for a variable and optionally initialize it
    def _alloc_var_reg(
        self, name: str, out, init_value=None, typ="int", is_label=False, comment=None
    ):
        return alloc_var_reg(
            self,
            name,
            out,
            init_value=init_value,
            typ=typ,
            is_label=is_label,
            comment=comment,
        )

    def _collect_global_types(self, ast: Dict[str, Any]):
        for g in ast.get("globals", []):
            print("collecting global type for:", g)
            if g.get("kind") == "string":
                self.global_types[g.get("name")] = "char_ptr"
                self.global_value_inits[g.get("name")] = g.get("name")
            if g.get("kind") == "blob":
                self.global_types[g.get("name")] = "char_ptr"
                self.global_value_inits[g.get("name")] = g.get("name")
            if g.get("kind") == "inline_const":
                # Store inline constants for lookup during expression evaluation
                name = g.get("name")
                value = g.get("value")
                self.inline_constants[name] = value
                self.var_types[name] = g.get("type", "int")

        for fn in ast.get("functions", []):
            name = fn.get("name")
            return_type = fn.get("return_type")
            if name and return_type:
                self.func_return_types[name] = return_type
            # Collect inline functions for inlining at call sites
            if fn.get("inline"):
                self.inline_functions[name] = fn

        # Collect struct type definitions
        for typ in ast.get("types", []):
            if typ.get("kind") == "struct":
                struct_name = typ.get("name")
                if struct_name:
                    self.struct_types[struct_name] = {
                        "members": typ.get("members", []),
                        "size": typ.get("size", 0),
                    }

    def _write_file_header(self, out):
        out.write("// Generated .ros by rospocc.emitter (starter)\n")
        out.write("// Functions\n")
        out.write(".SEG 0xFFFF_FFFC\n")

    def _write_lifted_spaces(self, out):
        for sp in self.global_spaces:
            lbl = sp.get("name")
            size = int(sp.get("size", 0))
            out.write(f"{lbl}:\n")
            out.write(f"  .SPACE {size} // lifted buffer\n\n")

    def gen_label(self, prefix="L") -> str:
        self.label_counter += 1
        return f"{self.label_namespace}{prefix}{self.label_counter}"

    def alloc_reg(self, track_as_temp: bool = True) -> str:
        borrowed_spill = False
        if not self.reg_free:
            self.reclaim_dead_var_regs()

        if not self.reg_free:
            reg = None
            if track_as_temp:
                for candidate in abi.TEMP_REGS:
                    if self._pinned_regs.get(candidate, 0) > 0:
                        continue
                    if self._spill_depth.get(candidate, 0) > 0:
                        continue
                    if self._borrowed_temp_depth.get(candidate, 0) > 0:
                        continue
                    reg = candidate
                    break

            print(
                f"Register pressure: no free registers, spilling {reg} for temp allocation"
            )
            if reg is not None and self.tracked_writer is not None and track_as_temp:
                self.tracked_writer.write(
                    f"  PUSH {reg}    // spill live temp for reg pressure\n"
                )
                aliases = [
                    name
                    for name, mapped_reg in self.var_regs.items()
                    if mapped_reg == reg
                ]
                if aliases:
                    self._spilled_var_aliases.setdefault(reg, []).append(list(aliases))
                    for name in aliases:
                        del self.var_regs[name]
                else:
                    self._spilled_var_aliases.setdefault(reg, []).append([])
                self._spill_stack.append(
                    {
                        "reg": reg,
                        "aliases": list(aliases),
                        "restored_early": False,
                    }
                )
                self._spill_depth[reg] = self._spill_depth.get(reg, 0) + 1
                self._borrowed_temp_depth[reg] = (
                    self._borrowed_temp_depth.get(reg, 0) + 1
                )
                borrowed_spill = True
            elif track_as_temp:
                raise RuntimeError(
                    "Out of registers for temporary expression evaluation; no spill-safe candidate available"
                )
            else:
                raise RuntimeError(
                    "Out of registers for variable allocation; consider reducing simultaneously-live variables"
                )
        else:
            reg = self.reg_free.pop(0)

        if track_as_temp and not borrowed_spill:
            self.temp_counter += 1
            temp_name = f"$tmp{self.temp_counter}"
            if self.tracked_writer is not None:
                self.register_allocator.set_output_line(
                    self.tracked_writer.get_current_output_line()
                )
            self.register_allocator.allocate(
                register=reg,
                variable_name=temp_name,
                variable_type="int",
                var_kind="temp",
                origin=self.current_context_origin,
            )
        return reg

    def free_reg(self, reg: str):
        writer = self.tracked_writer

        def _dec_spill_depth(r: str):
            depth = self._spill_depth.get(r, 0)
            if depth <= 1:
                self._spill_depth.pop(r, None)
            else:
                self._spill_depth[r] = depth - 1

        def _restore_aliases(r: str, aliases: list[str]):
            for name in aliases:
                if name not in self.var_regs:
                    self.var_regs[name] = r

        def _discard_stale_spill_tops():
            if writer is None:
                return
            while self._spill_stack and self._spill_stack[-1].get(
                "restored_early", False
            ):
                stale = self._spill_stack.pop()
                stale_reg = stale.get("reg")
                writer.write(
                    f"  ADDI {abi.SP_REG}, {abi.SP_REG}, 4    // discard stale spill slot for {stale_reg}\n"
                )
                _dec_spill_depth(stale_reg)

        spill_depth = self._spill_depth.get(reg, 0)
        if spill_depth > 0:
            if writer is None:
                raise RuntimeError(
                    "Cannot restore spilled register without tracked_writer"
                )

            # Find the most recent spill slot for this register.
            target_idx = None
            for i in range(len(self._spill_stack) - 1, -1, -1):
                if self._spill_stack[i].get("reg") == reg:
                    target_idx = i
                    break

            if target_idx is None:
                # Fallback for legacy state mismatch.
                writer.write(f"  POP {reg}    // restore spilled temp\n")
                _dec_spill_depth(reg)
                return

            top_idx = len(self._spill_stack) - 1

            # Fast path: normal LIFO restore.
            if target_idx == top_idx:
                entry = self._spill_stack[-1]
                if entry.get("restored_early", False):
                    _discard_stale_spill_tops()
                else:
                    self._spill_stack.pop()
                    writer.write(
                        f"  POP {reg}    // restore spilled temp\n"
                    )
                    _restore_aliases(reg, entry.get("aliases", []))
                    _dec_spill_depth(reg)
                # Keep legacy alias stack roughly in sync.
                alias_stack = self._spilled_var_aliases.get(reg, [])
                if alias_stack:
                    alias_stack.pop()
                    if alias_stack:
                        self._spilled_var_aliases[reg] = alias_stack
                    else:
                        self._spilled_var_aliases.pop(reg, None)
                elif not entry.get("restored_early", False):
                    self._spilled_var_aliases.pop(reg, None)
                _discard_stale_spill_tops()
                return

            # Non-top restore request.
            above_entries = self._spill_stack[target_idx + 1 :]

            # Safe to reverse-pop/rewind only if all above entries are not currently borrowed
            # and were not already early-restored placeholders.
            can_unwind = True
            for e in above_entries:
                e_reg = e.get("reg")
                if e.get("restored_early", False):
                    can_unwind = False
                    break
                if self._borrowed_temp_depth.get(e_reg, 0) > 0:
                    can_unwind = False
                    break
                if self._pinned_regs.get(e_reg, 0) > 0:
                    can_unwind = False
                    break

            if can_unwind:
                # Unwind top entries (reverse order), restore target, then re-spill unwound entries.
                for e in reversed(above_entries):
                    e_reg = e.get("reg")
                    writer.write(
                        f"  POP {e_reg}    // unwind spill stack for restoring {reg}\n"
                    )

                writer.write(f"  POP {reg}    // restore spilled temp\n")
                target_entry = self._spill_stack[target_idx]
                _restore_aliases(reg, target_entry.get("aliases", []))
                _dec_spill_depth(reg)

                for e in above_entries:
                    e_reg = e.get("reg")
                    writer.write(
                        f"  PUSH {e_reg}    // rewind spill stack after restoring {reg}\n"
                    )

                # Remove target entry; above entries remain spilled in same relative order.
                self._spill_stack = self._spill_stack[:target_idx] + above_entries

                alias_stack = self._spilled_var_aliases.get(reg, [])
                if alias_stack:
                    alias_stack.pop()
                    if alias_stack:
                        self._spilled_var_aliases[reg] = alias_stack
                    else:
                        self._spilled_var_aliases.pop(reg, None)
                else:
                    self._spilled_var_aliases.pop(reg, None)
                return

            # Unsafe to unwind: restore value from stack slot without disturbing top spill order.
            slots_from_top = top_idx - target_idx
            byte_off = slots_from_top * 4
            writer.write(
                f"  LW {reg}, {abi.SP_REG}, {byte_off}    // restore spilled temp from stack slot\n"
            )
            target_entry = self._spill_stack[target_idx]
            if not target_entry.get("restored_early", False):
                _restore_aliases(reg, target_entry.get("aliases", []))
                target_entry["aliases"] = []
                target_entry["restored_early"] = True

            alias_stack = self._spilled_var_aliases.get(reg, [])
            if alias_stack:
                alias_stack.pop()
                if alias_stack:
                    self._spilled_var_aliases[reg] = alias_stack
                else:
                    self._spilled_var_aliases.pop(reg, None)
            else:
                self._spilled_var_aliases.pop(reg, None)
            return

        if (
            reg
            and reg.startswith("r")
            and reg not in self.reg_free
            and reg in abi.TEMP_REGS
        ):
            if self.tracked_writer is not None:
                self.register_allocator.set_output_line(
                    self.tracked_writer.get_current_output_line()
                )
            self.register_allocator.deallocate(reg)
            self.reg_free.append(reg)

    def is_var_reg(self, reg: str) -> bool:
        return reg in self.var_regs.values()

    def release_expr_reg(self, reg: str):
        # Only expression temporaries are releasable; variable-backed registers must stay live.
        if not reg or reg not in abi.TEMP_REGS:
            return

        borrowed_depth = self._borrowed_temp_depth.get(reg, 0)
        if borrowed_depth > 0:
            if borrowed_depth == 1:
                del self._borrowed_temp_depth[reg]
            else:
                self._borrowed_temp_depth[reg] = borrowed_depth - 1
            self.free_reg(reg)
            return

        if not self.is_var_reg(reg):
            self.free_reg(reg)

    def pin_reg(self, reg: Optional[str]):
        if reg and reg in abi.TEMP_REGS:
            self._pinned_regs[reg] = self._pinned_regs.get(reg, 0) + 1

    def unpin_reg(self, reg: Optional[str]):
        if not reg or reg not in abi.TEMP_REGS:
            return
        depth = self._pinned_regs.get(reg, 0)
        if depth <= 1:
            self._pinned_regs.pop(reg, None)
        else:
            self._pinned_regs[reg] = depth - 1

    # Helper: ensure a var has a register (allocate+zero-init if not)
    def _ensure_var_reg(self, name: str, out) -> str:
        return ensure_var_reg(self, name, out)

    def _count_expr_var_reads(
        self, expr: Optional[Dict[str, Any]], counts: Dict[str, int]
    ):
        if not isinstance(expr, dict):
            return

        et = expr.get("type")
        if et == "var":
            name = expr.get("name")
            if isinstance(name, str):
                counts[name] = counts.get(name, 0) + 1
            return

        if et == "binop":
            self._count_expr_var_reads(expr.get("left"), counts)
            self._count_expr_var_reads(expr.get("right"), counts)
            return

        if et == "unop":
            self._count_expr_var_reads(expr.get("operand"), counts)
            return

        if et in ("deref", "addr_of"):
            self._count_expr_var_reads(expr.get("expr"), counts)
            return

        if et == "member_access":
            self._count_expr_var_reads(expr.get("base"), counts)
            return

        if et == "call":
            for arg in expr.get("args", []) or []:
                self._count_expr_var_reads(arg, counts)
            return

        if et == "assign":
            target = expr.get("target")
            if isinstance(target, dict):
                target_type = target.get("type")
                if target_type == "deref":
                    self._count_expr_var_reads(target.get("expr"), counts)
                elif target_type == "member_access":
                    self._count_expr_var_reads(target.get("base"), counts)
            self._count_expr_var_reads(expr.get("value"), counts)

    def _count_stmt_var_reads(
        self, stmt: Optional[Dict[str, Any]], counts: Dict[str, int]
    ):
        if not isinstance(stmt, dict):
            return

        st = stmt.get("type")
        if st == "decl":
            self._count_expr_var_reads(stmt.get("init"), counts)
            return

        if st == "assign":
            target = stmt.get("target")
            if isinstance(target, dict):
                target_type = target.get("type")
                if target_type == "deref":
                    self._count_expr_var_reads(target.get("expr"), counts)
                elif target_type == "member_access":
                    self._count_expr_var_reads(target.get("base"), counts)
            self._count_expr_var_reads(stmt.get("value"), counts)
            return

        if st == "return":
            self._count_expr_var_reads(stmt.get("value"), counts)
            return

        if st == "if":
            self._count_expr_var_reads(stmt.get("cond"), counts)
            for child in stmt.get("then", []) or []:
                self._count_stmt_var_reads(child, counts)
            for child in stmt.get("else", []) or []:
                self._count_stmt_var_reads(child, counts)
            return

        if st == "while":
            self._count_expr_var_reads(stmt.get("cond"), counts)
            for child in stmt.get("body", []) or []:
                self._count_stmt_var_reads(child, counts)
            return

        if st == "call_stmt":
            for arg in stmt.get("args", []) or []:
                self._count_expr_var_reads(arg, counts)

    def _count_stmt_self_var_reads(
        self, stmt: Optional[Dict[str, Any]], counts: Dict[str, int]
    ):
        if not isinstance(stmt, dict):
            return

        st = stmt.get("type")
        if st == "decl":
            self._count_expr_var_reads(stmt.get("init"), counts)
            return

        if st == "assign":
            target = stmt.get("target")
            if isinstance(target, dict):
                target_type = target.get("type")
                if target_type == "deref":
                    self._count_expr_var_reads(target.get("expr"), counts)
                elif target_type == "member_access":
                    self._count_expr_var_reads(target.get("base"), counts)
            self._count_expr_var_reads(stmt.get("value"), counts)
            return

        if st == "return":
            self._count_expr_var_reads(stmt.get("value"), counts)
            return

        if st == "call_stmt":
            for arg in stmt.get("args", []) or []:
                self._count_expr_var_reads(arg, counts)
            return

        if st in ("if", "while"):
            self._count_expr_var_reads(stmt.get("cond"), counts)

    def _count_stmt_self_var_reads_set(self, stmt: Optional[Dict[str, Any]]) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        self._count_stmt_self_var_reads(stmt, counts)
        return counts

    def _collect_expr_vars(self, expr: Optional[Dict[str, Any]], names: set[str]):
        if not isinstance(expr, dict):
            return

        et = expr.get("type")
        if et == "var":
            name = expr.get("name")
            if isinstance(name, str):
                names.add(name)
            return

        if et == "binop":
            self._collect_expr_vars(expr.get("left"), names)
            self._collect_expr_vars(expr.get("right"), names)
            return

        if et == "unop":
            self._collect_expr_vars(expr.get("operand"), names)
            return

        if et in ("deref", "addr_of"):
            self._collect_expr_vars(expr.get("expr"), names)
            return

        if et == "member_access":
            self._collect_expr_vars(expr.get("base"), names)
            return

        if et == "call":
            for arg in expr.get("args", []) or []:
                self._collect_expr_vars(arg, names)
            return

        if et == "assign":
            target = expr.get("target")
            if isinstance(target, dict):
                target_type = target.get("type")
                if target_type == "deref":
                    self._collect_expr_vars(target.get("expr"), names)
                elif target_type == "member_access":
                    self._collect_expr_vars(target.get("base"), names)
            self._collect_expr_vars(expr.get("value"), names)

    def _collect_stmt_defs(self, stmt: Optional[Dict[str, Any]]) -> set[str]:
        names: set[str] = set()
        if not isinstance(stmt, dict):
            return names

        st = stmt.get("type")
        if st == "decl":
            name = stmt.get("name")
            if isinstance(name, str):
                names.add(name)
            return names

        if st == "assign":
            target = stmt.get("target")
            if isinstance(target, dict) and target.get("type") == "var":
                name = target.get("name")
                if isinstance(name, str):
                    names.add(name)
            elif isinstance(target, str):
                names.add(target)
        return names

    def _analyze_stmt_liveness(
        self, stmt: Optional[Dict[str, Any]], live_out: set[str]
    ) -> set[str]:
        if not isinstance(stmt, dict):
            return set(live_out)

        stmt_id = id(stmt)
        live_out_set = set(live_out)
        self._stmt_live_after[stmt_id] = live_out_set
        st = stmt.get("type")

        if st == "if":
            cond_names: set[str] = set()
            self._collect_expr_vars(stmt.get("cond"), cond_names)
            then_live_in = self._analyze_stmt_list_liveness(
                stmt.get("then", []) or [], live_out_set
            )
            else_live_in = self._analyze_stmt_list_liveness(
                stmt.get("else", []) or [], live_out_set
            )
            return cond_names | then_live_in | else_live_in

        if st == "while":
            cond_names: set[str] = set()
            self._collect_expr_vars(stmt.get("cond"), cond_names)
            loop_live = set(live_out_set) | cond_names
            while True:
                body_live_in = self._analyze_stmt_list_liveness(
                    stmt.get("body", []) or [], loop_live
                )
                new_loop_live = cond_names | body_live_in | live_out_set
                if new_loop_live == loop_live:
                    break
                loop_live = new_loop_live
            self._analyze_stmt_list_liveness(stmt.get("body", []) or [], loop_live)
            return loop_live

        uses: set[str] = set()
        if st == "decl":
            self._collect_expr_vars(stmt.get("init"), uses)
        elif st == "assign":
            target = stmt.get("target")
            if isinstance(target, dict):
                target_type = target.get("type")
                if target_type == "deref":
                    self._collect_expr_vars(target.get("expr"), uses)
                elif target_type == "member_access":
                    self._collect_expr_vars(target.get("base"), uses)
            self._collect_expr_vars(stmt.get("value"), uses)
        elif st == "return":
            self._collect_expr_vars(stmt.get("value"), uses)
        elif st == "call_stmt":
            for arg in stmt.get("args", []) or []:
                self._collect_expr_vars(arg, uses)

        defs = self._collect_stmt_defs(stmt)
        return uses | (live_out_set - defs)

    def _analyze_stmt_list_liveness(
        self, stmts: list[Dict[str, Any]], live_out: set[str]
    ) -> set[str]:
        current = set(live_out)
        for stmt in reversed(stmts):
            current = self._analyze_stmt_liveness(stmt, current)
        return current

    def get_expr_read_vars(self, expr: Optional[Dict[str, Any]]) -> set[str]:
        counts: Dict[str, int] = {}
        self._count_expr_var_reads(expr, counts)
        return {name for name, count in counts.items() if count > 0}

    def get_stmt_read_vars(self, stmt: Optional[Dict[str, Any]]) -> set[str]:
        counts: Dict[str, int] = {}
        self._count_stmt_var_reads(stmt, counts)
        return {name for name, count in counts.items() if count > 0}

    def enter_control_context(self, protected_vars: set[str]):
        self._control_flow_depth += 1
        for name in protected_vars:
            self._protected_var_depth[name] = self._protected_var_depth.get(name, 0) + 1

    def exit_control_context(self, protected_vars: set[str]):
        for name in protected_vars:
            depth = self._protected_var_depth.get(name, 0)
            if depth <= 1:
                self._protected_var_depth.pop(name, None)
            else:
                self._protected_var_depth[name] = depth - 1
        if self._control_flow_depth > 0:
            self._control_flow_depth -= 1

    def prepare_function_liveness(self, fn: Dict[str, Any]):
        self._stmt_live_after = {}
        self._statement_stack = []
        self._analyze_stmt_list_liveness(fn.get("body", []) or [], set())

    def _push_statement_frame(self, stmt: Dict[str, Any]):
        stmt_id = id(stmt)
        self._statement_stack.append(
            {
                "stmt_id": stmt_id,
                "live_after": set(self._stmt_live_after.get(stmt_id, set())),
                "remaining_reads": self._count_stmt_self_var_reads_set(stmt),
            }
        )

    def _pop_statement_frame(self):
        if self._statement_stack:
            self._statement_stack.pop()

    def _current_statement_frame(self):
        if not self._statement_stack:
            return None
        return self._statement_stack[-1]

    def _try_release_reg_aliases_if_dead(self, reg: str, live_after: Optional[set[str]] = None):
        if self._pinned_regs.get(reg, 0) > 0:
            return
        if self._spill_depth.get(reg, 0) > 0:
            return
        if self._borrowed_temp_depth.get(reg, 0) > 0:
            return

        frame = self._current_statement_frame()
        if live_after is None and frame is not None:
            live_after = frame.get("live_after", set())
        live_after = live_after or set()

        aliases = [
            name for name, mapped_reg in self.var_regs.items() if mapped_reg == reg
        ]
        if not aliases:
            return

        for name in aliases:
            if frame is not None and frame.get("remaining_reads", {}).get(name, 0) > 0:
                return
            if self._protected_var_depth.get(name, 0) > 0:
                return
            if name in live_after:
                return

        for name in aliases:
            del self.var_regs[name]
        self.free_reg(reg)

    def reclaim_dead_var_regs(self):
        frame = self._current_statement_frame()
        if frame is None:
            return

        live_after: set[str] = set(frame.get("live_after", set()))
        for reg in list(dict.fromkeys(self.var_regs.values())):
            self._try_release_reg_aliases_if_dead(reg, live_after=live_after)

    def consume_var_read(self, name: Optional[str]):
        if not isinstance(name, str):
            return
        frame = self._current_statement_frame()
        if frame is None:
            return
        remaining_reads = frame.get("remaining_reads", {})
        if name not in remaining_reads:
            return
        remaining = remaining_reads.get(name, 0)
        if remaining > 0:
            remaining_reads[name] = remaining - 1
        if self._protected_var_depth.get(name, 0) > 0:
            return
        if name in frame.get("live_after", set()):
            return
        reg = self.var_regs.get(name)
        if reg:
            self._try_release_reg_aliases_if_dead(reg)

    def _emit_compare(self, rd: str, op: str, rl: str, rr: str, out):
        ltrue = self.gen_label("CMP_TRUE")
        lend = self.gen_label("CMP_END")
        if op == "eq":
            out.write(f"  BEQ {rl}, {rr}, {ltrue}\n")
        elif op == "neq":
            out.write(f"  BNE {rl}, {rr}, {ltrue}\n")
        elif op == "lt":
            out.write(f"  BLT {rl}, {rr}, {ltrue}\n")
        elif op == "lte":
            out.write(f"  BGE {rr}, {rl}, {ltrue}\n")
        elif op == "gt":
            out.write(f"  BLT {rr}, {rl}, {ltrue}\n")
        elif op == "gte":
            out.write(f"  BGE {rl}, {rr}, {ltrue}\n")
        out.write(f"  LLI {rd}, 0    // compare false path\n")
        out.write(f"  JMP {lend}\n")
        out.write(f"{ltrue}:\n")
        out.write(f"  LLI {rd}, 1\n")
        out.write(f"{lend}:\n")

    def enter_var_scope(self):
        self._var_scope_stack.append({})

    def note_var_declaration(self, name: Optional[str]):
        if not isinstance(name, str):
            return
        if not self._var_scope_stack:
            return

        scope = self._var_scope_stack[-1]
        if name in scope:
            return

        had_prev = name in self.var_regs
        scope[name] = {
            "had_prev": had_prev,
            "prev_reg": self.var_regs.get(name),
            "prev_type": self.var_types.get(name),
        }

    def exit_var_scope(self):
        if not self._var_scope_stack:
            return

        scope = self._var_scope_stack.pop()
        for name, info in reversed(list(scope.items())):
            reg = self.var_regs.get(name)
            if (
                reg
                and reg in abi.TEMP_REGS
                and self._spill_depth.get(reg, 0) == 0
                and self._borrowed_temp_depth.get(reg, 0) == 0
            ):
                del self.var_regs[name]
                self.free_reg(reg)
            else:
                self.var_regs.pop(name, None)

            if info.get("had_prev"):
                prev_reg = info.get("prev_reg")
                if prev_reg:
                    self.var_regs[name] = prev_reg
                prev_type = info.get("prev_type")
                if prev_type is not None:
                    self.var_types[name] = prev_type
                else:
                    self.var_types.pop(name, None)
            elif name in self.var_types:
                self.var_types.pop(name, None)

    def _intrinsic_lb(self, args, out, return_reg=None):
        intrinsic_lb(self, args, out, return_reg=return_reg)

    def _intrinsic_sb(self, args, out, return_reg=None):
        intrinsic_sb(self, args, out, return_reg=return_reg)

    def _intrinsic_break(self, args, out, return_reg=None):
        intrinsic_break(self, args, out, return_reg=return_reg)

    def emit_translation_unit(self, ast: Dict[str, Any], out_path: str):
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as f:
            # Wrap file handle with TrackedWriter for source tracking
            self.tracked_writer = TrackedWriter(f, self.source_file or str(out_file))
            out = self.tracked_writer

            # Header and globals collection
            # the file header should be labeled as coming from the main function
            main_fn = next(
                (fn for fn in ast.get("functions", []) if fn.get("name") == "main"),
                None,
            )
            assert (
                main_fn
            ), "Translation unit must have a main function for source tracking context"
            print("mainfn:", main_fn)
            print()
            self._set_source_context(main_fn, out)
            self._write_file_header(out)
            self._collect_global_types(ast)
            out.write(".DATA 0x00000000\n\n")
            out.write(".SEG 0x00000000\n\n")
            out.write(f"  JMP main\n\n")
            # Functions are independent, so render them in parallel and splice
            # the resulting chunks back into the file in source order.
            function_results = _emit_functions_parallel(self, ast.get("functions", []))
            base_mappings = list(out.get_mappings())
            merged_mappings = list(base_mappings)
            for result in function_results:
                line_offset = out.get_current_output_line() - 1
                for mapping in result["mappings"]:
                    merged_mappings.append(
                        {
                            **mapping,
                            "output_line": mapping["output_line"] + line_offset,
                        }
                    )
                for allocation in result["allocations"]:
                    self.register_allocator.allocations.append(
                        RegAllocation(
                            output_line=allocation["output_line"] + line_offset,
                            register=allocation["register"],
                            variable_name=allocation["variable_name"],
                            variable_type=allocation["variable_type"],
                            var_kind=allocation["var_kind"],
                            origin=allocation.get("origin"),
                            action=allocation.get("action", "allocate"),
                        )
                    )
                for space in result["global_spaces"]:
                    self.global_spaces.append(space)
                f.write(result["text"])
                out.current_output_line += result["line_count"]
            out.write("\n// Globals\n\n")
            # Globals (very small handling)
            for g in ast.get("globals", []):
                self.emit_global_declaration(g, out)
            # Emit any lifted large buffers (as .SPACE labels)
            out.set_source_context(None)  # No source for lifted buffers
            for sp in self.global_spaces:
                lbl = sp.get("name")
                size = int(sp.get("size", 0))
                out.write(f"{lbl}:\n")
                out.write(f"  .SPACE {size} // lifted buffer\n\n")
            out.write("\n")
            out.flush()
            merged_mappings.extend(out.get_mappings()[len(base_mappings) :])
            merged_mappings.sort(key=lambda item: item["output_line"])
            out.mappings = merged_mappings
            # Export register allocations for debug info
            self.export_register_allocations(out_path)

    def export_register_allocations(self, out_path: str):
        """Export register allocations to a sidecar .rosc.regalloc file."""
        out_file = Path(out_path)
        regalloc_path = out_file.with_suffix(".rosc.regalloc")
        self.register_allocator.write_to_file(str(regalloc_path))
        return str(regalloc_path)

    def emit_global_declaration(self, g: Dict[str, Any], out):
        # Skip inline constants - they are substituted at compile time
        if g.get("kind") == "inline_const":
            name = g.get("name")
            value = g.get("value")
            out.write(
                f"// Inline constant '{name}' = {value} (substituted at compile time)\n"
            )
            return

        # Starter supports simple string/global labels
        if g.get("kind") == "string":
            lbl = g.get("name") or self.gen_label("str")
            s = _escape_ros_string(str(g.get("value", "")))
            out.write(f"{lbl}:\n")
            out.write(f'  .STR "{s}"\n\n')
        elif g.get("kind") == "blob":
            lbl = g.get("name") or self.gen_label("blob")
            raw = g.get("value", b"")
            if isinstance(raw, str):
                blob_bytes = raw.encode("latin1")
            else:
                blob_bytes = bytes(raw)

            out.write(f"{lbl}:\n")
            if not blob_bytes:
                out.write("  .SPACE 0\n\n")
                return

            for word in range(0, len(blob_bytes), 4):
                byte = blob_bytes[word : word + 4]
                out.write(f"  .DATA 0x{int.from_bytes(byte, 'little'):08X}\n")
            out.write("\n")
        else:
            # unknown global; emit a commented placeholder
            out.write(f"// global: {g!r}\n")

    def emit_function_def(self, fn: Dict[str, Any], out):
        name = fn.get("name", "fn")

        # Skip inline functions - they will be inlined at call sites
        if fn.get("inline"):
            out.write(
                f"// Inline function definition '{name}' skipped (will be inlined at call sites)\n\n"
            )
            return

        # Set source context for function definition
        self._set_source_context(fn, out)

        out.write(f".FUNC {name}:\n")
        # Save link register so nested calls won't clobber return address
        out.write(f"  PUSH {abi.LINK_REG}\n")
        # Reset allocator state per function
        self.current_context_origin = f"_{name}"
        self.reg_free = list(abi.TEMP_REGS)
        self.var_regs = {}
        self._spill_depth = {}
        self._borrowed_temp_depth = {}
        self._spilled_var_aliases = {}
        self._spill_stack = []
        self._pinned_regs = {}
        self._stmt_live_after = {}
        self._statement_stack = []
        self._control_flow_depth = 0
        self._protected_var_depth = {}
        self._var_scope_stack = []
        # start var_types with globals available
        self.var_types = dict(self.global_types)
        # Handle parameters: map param names to argument registers (r1..r4)
        params = fn.get("params", []) or []
        reg_param_count = len(abi.ARG_REGS)
        for i, p in enumerate(params[:reg_param_count]):
            self.var_regs[p] = abi.ARG_REGS[i]
            try:
                self.reg_free.remove(abi.ARG_REGS[i])  # mark arg registers as used
            except ValueError:
                print(f"Warning: arg register {abi.ARG_REGS[i]} not in free list")
            # Track parameter allocation for debug info
            param_type = (fn.get("param_types", {}) or {}).get(p, "int")
            if hasattr(out, "get_current_output_line"):
                self.register_allocator.set_output_line(out.get_current_output_line())
                self.register_allocator.allocate(
                    register=abi.ARG_REGS[i],
                    variable_name=p,
                    variable_type=param_type,
                    var_kind="param",
                    origin=f"_{name}_entry",
                )

        # Load overflow parameters from caller stack slots.
        # Stack layout on entry after PUSH r14:
        #   [sp+0]  = saved r14
        #   [sp+4]  = arg5
        #   [sp+8]  = arg6
        #   ...
        for i, p in enumerate(params[reg_param_count:], start=reg_param_count):
            r = self.alloc_reg(track_as_temp=False)
            self.var_regs[p] = r
            param_type = (fn.get("param_types", {}) or {}).get(p, "int")
            self.var_types[p] = param_type
            if hasattr(out, "get_current_output_line"):
                self.register_allocator.set_output_line(out.get_current_output_line())
                self.register_allocator.allocate(
                    register=r,
                    variable_name=p,
                    variable_type=param_type,
                    var_kind="param",
                    origin=f"_{name}_entry",
                )

            stack_slot = (i - reg_param_count) + 1
            stack_offset = stack_slot * 4
            out.write(
                f"  LW {r}, {abi.SP_REG}, {stack_offset}    // load stack arg {p}\n"
            )

        # import any parameter type hints (e.g., pointer params)
        for pname, ptype in (fn.get("param_types", {}) or {}).items():
            self.var_types[pname] = ptype

        # per-function flag: whether a return was emitted inside body
        self.had_return = False
        self.prepare_function_liveness(fn)

        # Emit body
        self.enter_var_scope()
        try:
            for stmt in fn.get("body", []):
                self.emit_statement(stmt, out)
        finally:
            self.exit_var_scope()
        if name == "main":
            out.write(f"  BREAK")
        # If no return was emitted in the body, emit epilogue and return 0
        if not self.had_return:
            # Clear source context for epilogue
            if hasattr(out, "set_source_context"):
                out.set_source_context(None)
            out.write(f"  // epilogue and return\n")
            out.write(
                f"  ADDI {abi.RETURN_REG}, {abi.SPECIAL_REGS['zero']}, 0  // ensure r1=0\n"
            )
            out.write(f"  POP {abi.LINK_REG}\n")
            out.write(f"  RET\n\n")
        else:
            # already emitted return(s); do not append another epilogue/RET
            out.write("\n")

    def emit_statement(self, stmt: Dict[str, Any], out):
        self._push_statement_frame(stmt)
        try:
            emit_statement_impl(self, stmt, out)
            self.reclaim_dead_var_regs()
        finally:
            self._pop_statement_frame()

    def emit_expr(self, expr: Optional[Dict[str, Any]], out) -> str:
        return emit_expression(self, expr, out)

    def _emit_call(self, call_expr: Dict[str, Any], return_reg: Optional[str], out):
        emit_call(self, call_expr, return_reg, out)


def emit_translation_unit(
    ast: Any,
    out_path: str,
    source_file: Optional[str] = None,
    source_lines: Optional[list] = None,
):
    """Accept either a `translation_unit` dict or a raw/AST input and emit .ros.

    If `ast` is not already a translation_unit dict, attempt to convert it
    using `transform_to_translation_unit` (if available) or fall back to
    calling `frontend.code_to_translation_unit`.

    Args:
        ast: The AST or translation unit to emit
        out_path: Path to write the .ros file
        source_file: Optional path to source file for debug tracking
        source_lines: Optional list of source lines for debug tracking

    Returns:
        List of source-to-output mappings if tracking is enabled
    """
    tu = ast
    # if not isinstance(ast, dict) or (
    #     isinstance(ast, dict) and "functions" not in ast and "globals" not in ast
    # ):
    #     if transform_to_translation_unit is not None:
    #         tu = transform_to_translation_unit(ast)

    e = Emitter(source_file=source_file, source_lines=source_lines)
    e.emit_translation_unit(tu, out_path)

    # Return mappings if tracking was enabled
    if e.tracked_writer:
        return e.tracked_writer.get_mappings()
    return []


def _sanitize_label_namespace(name: Optional[str], index: int) -> str:
    raw = str(name or "fn")
    safe = re.sub(r"[^0-9A-Za-z_]+", "_", raw).strip("_") or "fn"
    return f"{safe}_{index}_"


def _snapshot_emitter_state(template: Emitter) -> Dict[str, Any]:
    return {
        "source_file": template.source_file,
        "source_lines": list(template.source_lines),
        "global_types": dict(template.global_types),
        "global_value_inits": dict(template.global_value_inits),
        "func_return_types": dict(template.func_return_types),
        "struct_types": dict(template.struct_types),
        "inline_functions": dict(template.inline_functions),
        "inline_constants": dict(template.inline_constants),
        "global_spaces": list(template.global_spaces),
    }


def _clone_emitter_for_function(template_state: Dict[str, Any], label_namespace: str) -> Emitter:
    clone = Emitter(
        source_file=template_state.get("source_file"),
        source_lines=list(template_state.get("source_lines", [])),
        label_namespace=label_namespace,
    )
    clone.global_types = dict(template_state.get("global_types", {}))
    clone.global_value_inits = dict(template_state.get("global_value_inits", {}))
    clone.func_return_types = dict(template_state.get("func_return_types", {}))
    clone.struct_types = dict(template_state.get("struct_types", {}))
    clone.inline_functions = dict(template_state.get("inline_functions", {}))
    clone.inline_constants = dict(template_state.get("inline_constants", {}))
    clone.global_spaces = list(template_state.get("global_spaces", []))
    return clone


def _emit_single_function_chunk(payload: Dict[str, Any]) -> Dict[str, Any]:
    emitter = _clone_emitter_for_function(
        payload["template"], payload["label_namespace"]
    )
    function = payload["function"]
    buffer = io.StringIO()
    writer = TrackedWriter(buffer, emitter.source_file or "<memory>")
    emitter.tracked_writer = writer
    emitter.emit_function_def(function, writer)
    writer.flush()
    mappings = writer.get_mappings()
    return {
        "index": payload["index"],
        "text": buffer.getvalue(),
        "line_count": len(mappings),
        "mappings": mappings,
        "allocations": emitter.register_allocator.export_allocations(),
        "global_spaces": list(emitter.global_spaces),
    }


def _emit_functions_parallel(template: Emitter, functions: list[Dict[str, Any]]):
    ordered_functions = list(functions)
    if not ordered_functions:
        return []

    template_state = _snapshot_emitter_state(template)
    job_payloads = []
    for index, function in enumerate(ordered_functions):
        job_payloads.append(
            {
                "index": index,
                "function": function,
                "label_namespace": _sanitize_label_namespace(
                    function.get("name"), index
                ),
                "template": template_state,
            }
        )

    # Process startup/serialization overhead can dominate small translation units.
    # Keep parallel emission for larger function counts only.
    min_parallel_funcs = 8
    try:
        min_parallel_funcs = max(
            2, int(os.getenv("ROSPOCC_PARALLEL_MIN_FUNCS", "8"))
        )
    except (TypeError, ValueError):
        min_parallel_funcs = 8

    use_parallel = (
        len(job_payloads) >= min_parallel_funcs and (os.cpu_count() or 1) > 1
    )
    if not use_parallel:
        results = [_emit_single_function_chunk(payload) for payload in job_payloads]
    else:
        try:
            with ProcessPoolExecutor(
                max_workers=min(len(job_payloads), os.cpu_count() or 1)
            ) as executor:
                results = list(executor.map(_emit_single_function_chunk, job_payloads))
        except Exception:
            # Fallback to the serial path if a worker environment is unavailable.
            results = [_emit_single_function_chunk(payload) for payload in job_payloads]

    results.sort(key=lambda item: item["index"])
    return results
