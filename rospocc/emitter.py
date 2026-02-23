

from pathlib import Path
from typing import Any, Dict

import abi


class Emitter:
    def __init__(self):
        self.label_counter = 0
        self.reg_free = list(abi.TEMP_REGS)
        self.var_regs = {}
        # track simple type hints: var name -> 'char_ptr' | 'int_ptr' | 'int' | 'char'
        self.var_types = {}
        # globals type hints collected from translation unit
        self.global_types = {}
        # collected global space directives for lifted large buffers
        self.global_spaces = []
        # intrinsic handlers: name -> callable(args, out)
        self.intrinsics = {
            "__lb": self._intrinsic_lb,
            "__sb": self._intrinsic_sb,
        }

    # helper: write an immediate into a register
    def _load_imm(self, reg: str, value, out):
        out.write(f"  LLI {reg}, {value}    // load immediate {value}\n")

    # helper: allocate a register for a variable and optionally initialize it
    def _alloc_var_reg(
        self, name: str, out, init_value=None, typ="int", is_label=False, comment=None
    ):
        r = self.alloc_reg()
        self.var_regs[name] = r
        self.var_types[name] = typ
        if init_value is None:
            out.write(f"  LLI {r}, 0    // zero init {name}\n")
        else:
            if is_label:
                out.write(
                    f"  LLI {r}, {init_value}    // init {name} ({comment or 'addr'})\n"
                )
            else:
                out.write(f"  LLI {r}, {int(init_value)}    // init {name}\n")
        return r

    def _collect_global_types(self, ast: Dict[str, Any]):
        for g in ast.get("globals", []):
            if g.get("kind") == "string":
                self.global_types[g.get("name")] = "char_ptr"

    def _choose_entry_label(self, funcs):
        if not funcs:
            return None
        for fn in funcs:
            if fn.get("name") == "main":
                return "main"
        # fallback to first function
        return funcs[0].get("name") or "main"

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
        r = self.var_regs.get(name)
        if r:
            return r
        r = self.alloc_reg()
        self.var_regs[name] = r
        out.write(f"  LLI {r}, 0    // implicit init {name}\n")
        return r

    def _emit_compare(self, rd: str, op: str, rl: str, rr: str, out):
        out.write(f"  LLI {rd}, 0    // compare init 0\n")
        ltrue = self.gen_label("CMP_TRUE")
        lend = self.gen_label("CMP_END")
        if op == "==":
            out.write(f"  BEQ {rl}, {rr}, {ltrue}\n")
        elif op == "!=":
            out.write(f"  BNE {rl}, {rr}, {ltrue}\n")
        elif op == "<":
            out.write(f"  BLT {rl}, {rr}, {ltrue}\n")
        elif op == "<=":
            out.write(f"  BGE {rr}, {rl}, {ltrue}\n")
        elif op == ">":
            out.write(f"  BLT {rr}, {rl}, {ltrue}\n")
        elif op == ">=":
            out.write(f"  BGE {rl}, {rr}, {ltrue}\n")
        out.write(f"  JMP {lend}\n")
        out.write(f"{ltrue}:\n")
        out.write(f"  LLI {rd}, 1\n")
        out.write(f"{lend}:\n")

    def _intrinsic_lb(self, args, out):
        a = args[0] if args else None
        raddr = None
        if a is None:
            out.write("  // __lb missing arg\n")
            return
        # explicit array declarators are represented by frontend as type 'array'
        if a.get("type") == "array":
            size = int(a.get("size", 0))
            name = a.get("name", f"arr{self.label_counter}")
            lbl = self.gen_label(f"{name}_buf")
            self.global_spaces.append({"name": lbl, "size": size})
            r = self.alloc_reg()
            self.var_regs[name] = r
            self.var_types[name] = "char_ptr"
            out.write(f"  LLI {r}, {lbl}    // init {name} (buffer addr)\n")
            raddr = r
        elif a.get("type") == "const":
            val = int(a.get("value"))
            name = a.get("name", f"const{self.label_counter}")
            # scalar constant initializer -> treat as int value
            r = self.alloc_reg()
            self.var_regs[name] = r
            self.var_types[name] = "int"
            out.write(f"  LLI {r}, {val}    // init {name}\n")
            raddr = r
        elif a.get("type") == "var":
            raddr = self.var_regs.get(a.get("name"))
            if not raddr:
                raddr = self._ensure_var_reg(a.get("name"), out)
        else:
            raddr = self.emit_expr(a, out)

        assert raddr is not None, "Failed to prepare address for __lb"
        out.write(f"  LB {abi.RETURN_REG}, {raddr}, 0    // intrinsic __lb -> return\n")
        if raddr in abi.TEMP_REGS:
            self.free_reg(raddr)

    def _intrinsic_sb(self, args, out):
        if len(args) < 2:
            out.write("  // __sb missing args\n")
            return
        a_addr = args[0]
        a_val = args[1]

        if a_addr.get("type") == "const":
            raddr = self.alloc_reg()
            out.write(
                f"  LLI {raddr}, {int(a_addr.get('value'))}    // addr const for __sb\n"
            )
        elif a_addr.get("type") == "var":
            raddr = self.var_regs.get(a_addr.get("name"))
            if not raddr:
                raddr = self._ensure_var_reg(a_addr.get("name"), out)
        else:
            raddr = self.emit_expr(a_addr, out)

        if a_val.get("type") == "const":
            rval = self.alloc_reg()
            out.write(
                f"  LLI {rval}, {int(a_val.get('value'))}    // val const for __sb\n"
            )
        elif a_val.get("type") == "var":
            vname = a_val.get("name")
            if self.var_types.get(vname) == "char_ptr":
                rptr = self.var_regs.get(vname)
                if not rptr:
                    rptr = self._ensure_var_reg(vname, out)
                rval = self.alloc_reg()
                out.write(f"  LB {rval}, {rptr}, 0    // load *{vname} for __sb\n")
            else:
                rval = self.var_regs.get(vname)
                if not rval:
                    rval = self._ensure_var_reg(vname, out)
        else:
            rval = self.emit_expr(a_val, out)

        out.write(f"  SB {rval}, {raddr}, 0    // intrinsic __sb\n")
        if raddr in abi.TEMP_REGS:
            self.free_reg(raddr)
        if rval in abi.TEMP_REGS:
            self.free_reg(rval)

    def emit_translation_unit(self, ast: Dict[str, Any], out_path: str):
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open("w") as f:
            # Header and globals collection
            self._write_file_header(f)
            funcs = ast.get("functions", [])
            self._collect_global_types(ast)
            main_label = self._choose_entry_label(funcs)
            f.write(".DATA 0x00000000\n\n")
            f.write(".SEG 0x00000000\n\n")
            if main_label:
                # Place a small bootstrap that jumps to main as the first code
                f.write(f"  JMP {main_label}\n\n")
            # Functions
            for fn in ast.get("functions", []):
                self.emit_function_def(fn, f)
            f.write("\n// Globals\n\n")
            # Globals (very small handling)
            for g in ast.get("globals", []):
                self.emit_global_declaration(g, f)
            # Emit any lifted large buffers (as .SPACE labels)
            for sp in self.global_spaces:
                lbl = sp.get("name")
                size = int(sp.get("size", 0))
                f.write(f"{lbl}:\n")
                f.write(f"  .SPACE {size} // lifted buffer\n\n")
            f.write("\n")

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
        out.write(f".FUNC {name}:\n")
        # Minimal prologue comment
        out.write(f"  // prologue (minimal)\n")
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
        # import any parameter type hints (e.g., pointer params)
        for pname, ptype in (fn.get("param_types", {}) or {}).items():
            self.var_types[pname] = ptype

        # per-function flag: whether a return was emitted inside body
        self.had_return = False

        # Emit body
        for stmt in fn.get("body", []):
            self.emit_statement(stmt, out)

        # If no return was emitted in the body, emit epilogue and return 0
        assert (
            self.had_return != None
        ), "had_return flag should be set by body statements, or at least not be unset from initial False"
        if not self.had_return:
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
            init = stmt.get("init")
            if init:
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
                    self._emit_call(init, out)
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    if (
                        isinstance(init.get("name"), str)
                        and init.get("name") == "malloc"
                    ):
                        self.var_types[name] = "int_ptr"
                    else:
                        self.var_types[name] = "int"
                    out.write(f"  ADDI {r}, {abi.RETURN_REG}, 0\n")
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

            if isinstance(target, dict) and target.get("type") == "deref":
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
            # handle intrinsics via existing helper
            if isinstance(call_expr.get("name"), str) and call_expr.get(
                "name"
            ).startswith("__"):
                # reuse _emit_call which already handles intrinsics
                self._emit_call(
                    {"name": call_expr.get("name"), "args": call_expr.get("args")}, out
                )
            else:
                # prepare arguments and emit call
                self._emit_call(
                    {"name": call_expr.get("name"), "args": call_expr.get("args")}, out
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

    def emit_expr(self, expr: Dict[str, Any], out) -> str:
        if expr is None:
            return ""
        t = expr.get("type")
        if t == "const":
            v = int(expr.get("value", 0))
            # Try to use an immediate add into a register
            r = self.alloc_reg()
            # Use helper to load immediate
            self._load_imm(r, v, out)
            return r
        if t == "var":
            name = expr.get("name")
            r = self.var_regs.get(name)
            if r:
                return r
            # unknown var — allocate and zero-initialize
            r = self._alloc_var_reg(name, out, init_value=None, typ="int")
            return r
        if t == "deref":
            # load byte from address expr
            inner = expr.get("expr")
            raddr = self.emit_expr(inner, out)
            rd = self.alloc_reg()
            # choose load width heuristically: if inner is a known char pointer -> LB, else LW
            load_instr = "LW"
            if isinstance(inner, dict) and inner.get("type") == "var":
                v = inner.get("name")
                if self.var_types.get(v) == "char_ptr":
                    load_instr = "LB"
            out.write(f"  {load_instr} {rd}, {raddr}, 0    // deref\n")
            if raddr in abi.TEMP_REGS:
                self.free_reg(raddr)
            return rd
        if t == "call":
            # emit call (may be intrinsic)
            self._emit_call(expr, out)
            # return value is in RETURN_REG
            return abi.RETURN_REG
        if t == "binop":
            op = expr.get("op")
            left = expr.get("left")
            right = expr.get("right")
            rl = self.emit_expr(left, out)
            rr = self.emit_expr(right, out)
            rd = self.alloc_reg()

            # arithmetic and bitwise ops
            if op == "+":
                out.write(f"  ADD {rd}, {rl}, {rr}    // binop +\n")
            elif op == "-":
                out.write(f"  SUB {rd}, {rl}, {rr}    // binop -\n")
            elif op == "*":
                out.write(f"  MUL {rd}, {rl}, {rr}    // binop *\n")
            elif op == "/":
                out.write(f"  DIV {rd}, {rl}, {rr}    // binop /\n")
            elif op == "%":
                out.write(f"  REM {rd}, {rl}, {rr}    // binop %\n")
            elif op == "&":
                out.write(f"  AND {rd}, {rl}, {rr}    // binop &\n")
            elif op == "|":
                out.write(f"  OR {rd}, {rl}, {rr}    // binop |\n")
            elif op == "^":
                out.write(f"  XOR {rd}, {rl}, {rr}    // binop ^\n")
            elif op == "<<":
                out.write(f"  SHL {rd}, {rl}, {rr}    // binop <<\n")
            elif op == ">>":
                out.write(f"  SHR {rd}, {rl}, {rr}    // binop >>\n")

            # comparisons: produce 0/1 in rd
            elif op in ("==", "!=", "<", "<=", ">", ">="):
                # comparisons: produce 0/1 in rd (delegated to helper)
                self._emit_compare(rd, op, rl, rr, out)
            else:
                out.write(f"  // unsupported binop {op}\n")

            if rl in abi.TEMP_REGS:
                self.free_reg(rl)
            if rr in abi.TEMP_REGS:
                self.free_reg(rr)
            return rd
        elif t == "string_addr":
            lbl = expr.get("label")
            r = self.alloc_reg()
            self._load_imm(r, lbl, out)
            return r
        else:
            out.write(f"  // unsupported-expr {expr!r}\n")
            return ""

    def _emit_call(self, call_expr: Dict[str, Any], out):
        name = call_expr.get("name")
        args = call_expr.get("args", [])

        # Intrinsic handling for names starting with __ -> dispatch via registry
        if isinstance(name, str) and name.startswith("__"):
            handler = self.intrinsics.get(name)
            if handler:
                handler(args, out)
                return
            print(f"Warning: no handler for intrinsic {name!r}")
            # fall back to emitting as a regular call (which may fail if it's truly unsupported)
        # Default: regular function call -> place up to 4 args into ARG_REGS then CALL
        for i, a in enumerate(args[: len(abi.ARG_REGS)]):
            dest = abi.ARG_REGS[i]
            if a.get("type") == "const":
                self._load_imm(dest, int(a.get("value")), out)
            elif a.get("type") == "string_addr":
                self._load_imm(dest, a.get("label"), out)
            elif a.get("type") == "var":
                r = self.var_regs.get(a.get("name"))
                if r:
                    out.write(f"  ADDI {dest}, {r}, 0    // move arg {i}\n")
                else:
                    self._load_imm(dest, 0, out)
            else:
                out.write(f"  // unsupported arg type {a!r}\n")

        out.write(f"  CALL {call_expr.get('name')}\n")


def emit_translation_unit(ast: Any, out_path: str):
    """Accept either a `translation_unit` dict or a raw/AST input and emit .ros.

    If `ast` is not already a translation_unit dict, attempt to convert it
    using `transform_to_translation_unit` (if available) or fall back to
    calling `frontend.code_to_translation_unit`.
    """
    tu = ast
    # if not isinstance(ast, dict) or (
    #     isinstance(ast, dict) and "functions" not in ast and "globals" not in ast
    # ):
    #     if transform_to_translation_unit is not None:
    #         tu = transform_to_translation_unit(ast)

    e = Emitter()
    e.emit_translation_unit(tu, out_path)
