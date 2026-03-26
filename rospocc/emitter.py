from pathlib import Path
from typing import Any, Dict, Optional

import abi
from emitter_calls import emit_call
from emitter_expr import emit_expr as emit_expression
from emitter_intrinsics import intrinsic_break, intrinsic_lb, intrinsic_sb
from emitter_registers import alloc_var_reg, ensure_var_reg, load_imm
from emitter_stmt import emit_statement as emit_statement_impl
from register_allocator import RegisterAllocator
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
        self, source_file: Optional[str] = None, source_lines: Optional[list] = None
    ):
        self.label_counter = 0
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
        # Pinned regs are protected from spill while their current value is needed.
        self._pinned_regs = {}
        # Per-function look-ahead: variable -> remaining read count.
        self._remaining_var_reads = {}
        # Control-flow aware liveness guards.
        self._control_flow_depth = 0
        self._protected_var_depth = {}

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
        for fn in ast.get("functions", []):
            name = fn.get("name")
            return_type = fn.get("return_type")
            if name and return_type:
                self.func_return_types[name] = return_type
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
        return f"{prefix}{self.label_counter}"

    def alloc_reg(self, track_as_temp: bool = True) -> str:
        borrowed_spill = False
        if not self.reg_free:
            self.reclaim_dead_var_regs()

        if not self.reg_free:
            reg = None
            if track_as_temp:
                for candidate in abi.TEMP_REGS:
                    if candidate in self.reg_free:
                        continue
                    if self.is_var_reg(candidate):
                        continue
                    if self._pinned_regs.get(candidate, 0) > 0:
                        continue
                    if self._spill_depth.get(candidate, 0) > 0:
                        continue
                    reg = candidate
                    break

            print(f"Register pressure: no free registers, spilling {reg} for temp allocation")
            if reg is not None and self.tracked_writer is not None:
                self.tracked_writer.write(
                    f"  PUSH {reg}    // spill live temp for reg pressure\n"
                )
                self._spill_depth[reg] = self._spill_depth.get(reg, 0) + 1
                borrowed_spill = True
            else:
                # Fallback for non-temp allocations or if no spill-safe candidate exists.
                print(
                    "Warning: register pressure fallback to r13; consider freeing unused vars earlier"
                )
                print(f"Register picture at spill point: free={self.reg_free}, var_regs={self.var_regs}, pinned={self._pinned_regs}, spill_depth={self._spill_depth}")
                reg = "r13"
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
        spill_depth = self._spill_depth.get(reg, 0)
        if spill_depth > 0:
            if self.tracked_writer is not None:
                self.tracked_writer.write(f"  POP {reg}    // restore spilled temp\n")
            spill_depth -= 1
            if spill_depth > 0:
                self._spill_depth[reg] = spill_depth
            else:
                del self._spill_depth[reg]
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
        if reg and reg in abi.TEMP_REGS and not self.is_var_reg(reg):
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

    def _count_expr_var_reads(self, expr: Optional[Dict[str, Any]], counts: Dict[str, int]):
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

    def _count_stmt_var_reads(self, stmt: Optional[Dict[str, Any]], counts: Dict[str, int]):
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
        counts: Dict[str, int] = {}
        for stmt in fn.get("body", []) or []:
            self._count_stmt_var_reads(stmt, counts)
        self._remaining_var_reads = counts

    def _try_release_reg_aliases_if_dead(self, reg: str):
        if self._pinned_regs.get(reg, 0) > 0:
            return
        if self._spill_depth.get(reg, 0) > 0:
            return
        if self._control_flow_depth > 0:
            return

        aliases = [name for name, mapped_reg in self.var_regs.items() if mapped_reg == reg]
        if not aliases:
            return

        for name in aliases:
            if self._remaining_var_reads.get(name, 0) > 0:
                return
            if self._protected_var_depth.get(name, 0) > 0:
                return

        for name in aliases:
            del self.var_regs[name]
        self.free_reg(reg)

    def reclaim_dead_var_regs(self):
        for reg in list(dict.fromkeys(self.var_regs.values())):
            self._try_release_reg_aliases_if_dead(reg)

    def consume_var_read(self, name: Optional[str]):
        if not isinstance(name, str):
            return
        if name not in self._remaining_var_reads:
            return
        remaining = self._remaining_var_reads.get(name, 0)
        if remaining > 0:
            self._remaining_var_reads[name] = remaining - 1
        if self._control_flow_depth > 0:
            return
        if self._protected_var_depth.get(name, 0) > 0:
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
            # Functions
            for fn in ast.get("functions", []):
                self.emit_function_def(fn, out)
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
            # Export register allocations for debug info
            self.export_register_allocations(out_path)

    def export_register_allocations(self, out_path: str):
        """Export register allocations to a sidecar .rosc.regalloc file."""
        out_file = Path(out_path)
        regalloc_path = out_file.with_suffix(".rosc.regalloc")
        self.register_allocator.write_to_file(str(regalloc_path))
        return str(regalloc_path)

    def emit_global_declaration(self, g: Dict[str, Any], out):
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
                byte = blob_bytes[word:word+4]
                out.write(f"  .DATA 0x{int.from_bytes(byte, 'little'):08X}\n")
            out.write("\n")
        else:
            # unknown global; emit a commented placeholder
            out.write(f"// global: {g!r}\n")

    def emit_function_def(self, fn: Dict[str, Any], out):
        name = fn.get("name", "fn")

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
        self._pinned_regs = {}
        self._control_flow_depth = 0
        self._protected_var_depth = {}
        # start var_types with globals available
        self.var_types = dict(self.global_types)
        # Handle parameters: map param names to argument registers (r1..r4)
        params = fn.get("params", []) or []
        for i, p in enumerate(params[: len(abi.ARG_REGS)]):
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

        # import any parameter type hints (e.g., pointer params)
        for pname, ptype in (fn.get("param_types", {}) or {}).items():
            self.var_types[pname] = ptype

        # per-function flag: whether a return was emitted inside body
        self.had_return = False
        self.prepare_function_liveness(fn)

        # Emit body
        for stmt in fn.get("body", []):
            self.emit_statement(stmt, out)

        # If no return was emitted in the body, emit epilogue and return 0
        if not self.had_return:
            # Clear source context for epilogue
            if hasattr(out, "set_source_context"):
                out.set_source_context(None)
            out.write(f"  // epilogue and return\n")
            out.write(
                f"  ADDI {abi.RETURN_REG}, {abi.SPECIAL_REGS['zero']}, 0  // ensure r1=0\n"
            )
            # Use BREAK for main function, RET for others
            if name == "main":
                out.write(f"  BREAK    // exit from main\n\n")
            else:
                out.write(f"  POP {abi.LINK_REG}\n")
                out.write(f"  RET\n\n")
        else:
            # already emitted return(s); do not append another epilogue/RET
            out.write("\n")

    def emit_statement(self, stmt: Dict[str, Any], out):
        emit_statement_impl(self, stmt, out)

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
