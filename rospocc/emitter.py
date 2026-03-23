from pathlib import Path
from typing import Any, Dict, Optional

import abi
from emitter_calls import emit_call
from emitter_expr import emit_expr as emit_expression
from emitter_intrinsics import intrinsic_lb, intrinsic_sb
from emitter_registers import alloc_var_reg, ensure_var_reg, load_imm
from tracked_writer import TrackedWriter


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
        }
        # Source tracking for debug info
        self.source_file = source_file
        self.source_lines = source_lines or []
        self.tracked_writer = None

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

    def alloc_reg(self) -> str:
        if not self.reg_free:
            # Very simple fallback: use r13 (caller-saved temp)
            return "r13"
        return self.reg_free.pop(0)

    def free_reg(self, reg: str):
        if (
            reg
            and reg.startswith("r")
            and reg not in self.reg_free
            and reg in abi.TEMP_REGS
        ):
            self.reg_free.append(reg)

    # Helper: ensure a var has a register (allocate+zero-init if not)
    def _ensure_var_reg(self, name: str, out) -> str:
        return ensure_var_reg(self, name, out)

    def _emit_compare(self, rd: str, op: str, rl: str, rr: str, out):
        out.write(f"  LLI {rd}, 0    // compare init 0\n")
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
        out.write(f"  JMP {lend}\n")
        out.write(f"{ltrue}:\n")
        out.write(f"  LLI {rd}, 1\n")
        out.write(f"{lend}:\n")

    def _intrinsic_lb(self, args, out):
        intrinsic_lb(self, args, out)

    def _intrinsic_sb(self, args, out):
        intrinsic_sb(self, args, out)

    def emit_translation_unit(self, ast: Dict[str, Any], out_path: str):
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as f:
            # Wrap file handle with TrackedWriter for source tracking
            self.tracked_writer = TrackedWriter(f, self.source_file or str(out_file))
            out = self.tracked_writer

            # Header and globals collection
            out.set_source_context(None)  # No source for header
            self._write_file_header(out)
            funcs = ast.get("functions", [])
            self._collect_global_types(ast)
            main_label = "main"
            assert main_label in [
                fn.get("name") for fn in funcs
            ], "Expected a main function as entry point"
            out.write(".DATA 0x00000000\n\n")
            out.write(".SEG 0x00000000\n\n")
            if main_label:
                # Place a small bootstrap that jumps to main as the first code
                out.write(f"  JMP {main_label}\n\n")
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

    def emit_global_declaration(self, g: Dict[str, Any], out):
        # Starter supports simple string/global labels
        if g.get("kind") == "string":
            lbl = g.get("name") or self.gen_label("str")
            s = g.get("value", "")
            out.write(f"{lbl}:\n")
            out.write(f'  .STR "{s}"\n\n')
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
        self.reg_free = list(abi.TEMP_REGS)
        self.var_regs = {}
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

        # import any parameter type hints (e.g., pointer params)
        for pname, ptype in (fn.get("param_types", {}) or {}).items():
            self.var_types[pname] = ptype

        # per-function flag: whether a return was emitted inside body
        self.had_return = False

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
        # Set source context for this statement
        self._set_source_context(stmt, out)

        t = stmt.get("type")
        if t == "return":
            val = stmt.get("value")
            reg = self.emit_expr(val, out)
            if reg:
                if reg != abi.RETURN_REG:
                    out.write(
                        f"  ADD {abi.RETURN_REG}, {reg}, {abi.SPECIAL_REGS['zero']}\n"
                    )
                if reg in abi.TEMP_REGS:
                    self.free_reg(reg)
            out.write(f"  POP {abi.LINK_REG}\n")
            out.write("  RET\n")
            self.had_return = True
        elif t == "decl":
            name = stmt.get("name")
            assert isinstance(name, str), "Expected variable name as string in decl"
            decl_type = stmt.get("decl_type")  # Get declared type (e.g., struct name)
            init = stmt.get("init")

            # Check if this is a struct type declaration
            if decl_type and decl_type in self.struct_types:
                # Allocate space for struct instance
                struct_def = self.struct_types[decl_type]
                struct_size = struct_def.get("size", 0)

                # Lift struct to global space (similar to arrays)
                lbl = self.gen_label(f"{name}_struct")
                self.global_spaces.append({"name": lbl, "size": struct_size})

                # Store struct base address in register
                r = self._alloc_var_reg(
                    name,
                    out,
                    init_value=lbl,
                    typ=decl_type,  # Store struct type name
                    is_label=True,
                    comment=f"struct {decl_type} addr",
                )
            elif init:
                if init.get("type") == "const":
                    val = int(init.get("value"))
                    assert isinstance(val, int), "Expected integer constant initializer"
                    assert isinstance(name, str), "Expected variable name as string"
                    r = self._alloc_var_reg(name, out, init_value=val, typ="int")
                elif init.get("type") == "array":
                    # Local array declaration (e.g. char buf[12]) -> lift to .SPACE
                    size = int(init.get("size", 0))
                    lbl = self.gen_label(f"{name}_buf")
                    self.global_spaces.append({"name": lbl, "size": size})
                    r = self._alloc_var_reg(
                        name,
                        out,
                        init_value=lbl,
                        typ="char_ptr",
                        is_label=True,
                        comment="buffer addr",
                    )
                elif init.get("type") == "call":
                    r = self._alloc_var_reg(
                        name, out, init_value=None, typ="int"
                    )  # allocate reg for var before call
                    self._emit_call(init, r, out)
                    self.var_regs[name] = r
                    if (
                        isinstance(init.get("name"), str)
                        and init.get("name") == "malloc"
                    ):
                        self.var_types[name] = "int_ptr"
                    else:
                        self.var_types[name] = "int"
                elif init.get("type") == "string_addr":
                    r = self._alloc_var_reg(
                        name,
                        out,
                        init_value=init.get("label"),
                        typ="char_ptr",
                        is_label=True,
                        comment="string addr",
                    )
                else:
                    out.write(f"  // decl {name} with unsupported init {init!r}\n")
            else:
                r = self._alloc_var_reg(name, out, init_value=None, typ="int")
        elif t == "assign":
            target = stmt.get("target")
            val = stmt.get("value")
            rval = self.emit_expr(val, out)

            if isinstance(target, dict) and target.get("type") == "member_access":
                # Assignment to struct member (e.g., p.x = 5 or ptr->x = 5)
                op = target.get("op")
                base = target.get("base")
                member_name = target.get("member")

                if not base or not member_name:
                    out.write(
                        f"  // ERROR: missing base or member in member_access assignment\n"
                    )
                else:
                    # Calculate member address
                    if op == ".":
                        # Direct member access
                        if base.get("type") == "var":
                            base_name = base.get("name")
                            base_type = self.var_types.get(base_name)
                            struct_def = self.struct_types.get(base_type)
                            member_offset = (
                                None  # Initialize before checking struct_def
                            )

                            if not struct_def:
                                out.write(
                                    f"  // ERROR: unknown struct type for {base_name}\n"
                                )
                            else:
                                # Find member offset
                                for m in struct_def.get("members", []):
                                    if m.get("name") == member_name:
                                        member_offset = m.get("offset", 0)
                                        break

                            if member_offset is None:
                                out.write(
                                    f"  // ERROR: member {member_name} not found\n"
                                )
                            else:
                                base_reg = self.var_regs.get(base_name)
                                if (
                                    member_offset < 2**16
                                ):  # This should be 100% of the time, but just in case, check if offset fits in immediate field
                                    out.write(
                                        f"  SW {rval}, {base_reg}, {member_offset}    // store {base_name}.{member_name}\n"
                                    )
                                else:  # otherwise, need to load offset into register and add it. Just in case you have a struct over 64KB in size, which would be wild but let's be safe.
                                    offset_reg = self.alloc_reg()
                                    self._load_imm(offset_reg, member_offset, out)
                                    addr_reg = self.alloc_reg()
                                    out.write(
                                        f"  ADD {addr_reg}, {base_reg}, {offset_reg}    // calculate member addr\n"
                                    )
                                    out.write(
                                        f"  SW {rval}, {addr_reg}, 0    // store {base_name}.{member_name}\n"
                                    )
                                    if offset_reg in abi.TEMP_REGS:
                                        self.free_reg(offset_reg)
                                    if addr_reg in abi.TEMP_REGS:
                                        self.free_reg(addr_reg)
                    elif op == "->":
                        # Pointer member access
                        base_expr = self.emit_expr(base, out)

                        # Determine struct type
                        struct_type_name = None
                        if base.get("type") == "var":
                            base_type = self.var_types.get(base.get("name"))
                            if base_type and "_ptr" in base_type:
                                struct_type_name = base_type.replace("_ptr", "")
                            else:
                                struct_type_name = base_type

                        struct_def = self.struct_types.get(struct_type_name)
                        if not struct_def:
                            out.write(
                                f"  // ERROR: unknown struct type for -> access\n"
                            )
                        else:
                            # Find member offset
                            member_offset = None
                            for m in struct_def.get("members", []):
                                if m.get("name") == member_name:
                                    member_offset = m.get("offset", 0)
                                    break

                            if member_offset is None:
                                out.write(
                                    f"  // ERROR: member {member_name} not found\n"
                                )
                            else:
                                if (
                                    member_offset < 2**16
                                ):  # If offset fits in immediate field, use it directly
                                    out.write(
                                        f"  SW {rval}, {base_expr}, {member_offset}    // store ptr->{member_name}\n"
                                    )
                                else:  # Same logic as above for large offsets, just in case
                                    offset_reg = self.alloc_reg()
                                    self._load_imm(offset_reg, member_offset, out)
                                    addr_reg = self.alloc_reg()
                                    out.write(
                                        f"  ADD {addr_reg}, {base_expr}, {offset_reg}    // calculate member addr\n"
                                    )
                                    out.write(
                                        f"  SW {rval}, {addr_reg}, 0    // store ptr->{member_name}\n"
                                    )
                                    if offset_reg in abi.TEMP_REGS:
                                        self.free_reg(offset_reg)
                                    if addr_reg in abi.TEMP_REGS:
                                        self.free_reg(addr_reg)

                        if base_expr in abi.TEMP_REGS:
                            self.free_reg(base_expr)

            elif isinstance(target, dict) and target.get("type") == "deref":
                addr_expr = target.get("expr")
                raddr = self.emit_expr(addr_expr, out)
                store_instr = "SW"
                if isinstance(addr_expr, dict) and addr_expr.get("type") == "var":
                    if self.var_types.get(addr_expr.get("name")) == "char_ptr":
                        store_instr = "SB"
                out.write(f"  {store_instr} {rval}, {raddr}, 0    // store \n")
                if raddr in abi.TEMP_REGS:
                    self.free_reg(raddr)
            elif isinstance(target, dict) and target.get("type") == "var":
                name = target.get("name")
                dest = self.var_regs.get(name)
                if dest:
                    out.write(f"  ADDI {dest}, {rval}, 0    // assign {name}\n")
                else:
                    # take ownership of rval register for the variable
                    self.var_regs[name] = rval
                    if name not in self.var_types:
                        self.var_types[name] = "int"
                    # don't free rval here because it's now the variable's register
                    rval = None
            elif isinstance(target, str):
                dest = self.var_regs.get(target)
                if dest:
                    out.write(f"  ADDI {dest}, {rval}, 0    // assign {target}\n")
                else:
                    # take ownership of rval register for the variable
                    self.var_regs[target] = rval
                    if target not in self.var_types:
                        self.var_types[target] = "int"
                    # don't free rval here because it's now the variable's register
                    rval = None
            else:
                out.write(f"  // assign to unsupported target {target!r}\n")

            if rval and rval in abi.TEMP_REGS:
                self.free_reg(rval)

        elif t == "if":
            cond = stmt.get("cond")
            then_stmts = stmt.get("then", []) or []
            else_stmts = stmt.get("else", []) or []
            lbl_else = self.gen_label("ELSE")
            lbl_end = self.gen_label("IF_END")
            # if condition is a char pointer variable used as a boolean, dereference it
            if isinstance(cond, dict) and cond.get("type") == "var":
                vname = cond.get("name")
                if self.var_types.get(vname) == "char_ptr":
                    cond = {"type": "deref", "expr": cond}
            rcond = self.emit_expr(cond, out)
            rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
            out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_else}\n")
            if rcond and rcond in abi.TEMP_REGS:
                self.free_reg(rcond)
            for s in then_stmts:
                self.emit_statement(s, out)
            out.write(f"  JMP {lbl_end}\n")
            out.write(f"{lbl_else}:\n")
            for (
                s
            ) in (
                else_stmts
            ):  # If there's an else block, emit it; otherwise this is a no-op
                self.emit_statement(s, out)
            out.write(f"{lbl_end}:\n")

        elif t == "call_stmt":
            # call as a statement: either intrinsic or regular call
            # normalize to call expression shape expected by _emit_call
            call_expr = {
                "type": "call",
                "name": stmt.get("name") or stmt.get("call", {}).get("name"),
                "args": stmt.get("args", []) or stmt.get("call", {}).get("args", []),
            }

            # prepare arguments and emit call
            self._emit_call(
                {"name": call_expr.get("name"), "args": call_expr.get("args")},
                None,
                out,
            )

        elif t == "while":
            # while loop: evaluate cond, branch to end if zero, loop body, repeat
            cond = stmt.get("cond")
            body = stmt.get("body", []) or []
            lbl_start = self.gen_label("WHILE")
            lbl_end = self.gen_label("WHILE_END")
            out.write(f"{lbl_start}:\n")
            # normalize condition: treat `var` that is a `char_ptr` as `deref`
            if isinstance(cond, dict) and cond.get("type") == "var":
                vname = cond.get("name")
                if self.var_types.get(vname) == "char_ptr":
                    cond = {"type": "deref", "expr": cond}
            rcond = self.emit_expr(cond, out)
            rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
            out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_end}\n")
            if rcond and rcond in abi.TEMP_REGS:
                self.free_reg(rcond)
            for s in body:
                self.emit_statement(s, out)
            out.write(f"  JMP {lbl_start}\n")
            out.write(f"{lbl_end}:\n")
        else:
            out.write(f"  // unsupported-stmt {stmt!r}\n")

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
