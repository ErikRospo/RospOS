"""Simple .ros emitter for C AST (starter implementation).

This module provides a minimal emitter scaffold described in
rospocc/ros_from_CAST.prompt.md. It emits readable .ros text for
very small AST shapes to allow iterative testing with the existing
`rospoas` assembler.

The AST expected by this starter is minimal and dictionary-based:

translation_unit = {
    'globals': [ ... ],
    'functions': [ {'name': 'main', 'body': [ stmt, ... ] }, ... ]
}

Supported statement forms in this starter:
- {'type': 'return', 'value': expr}

Supported expr forms:
- {'type': 'const', 'value': int}

This is intentionally small; the emitter will be extended later.
"""
from pathlib import Path
from typing import Dict, Any
import os
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

    def gen_label(self, prefix="L") -> str:
        self.label_counter += 1
        return f"{prefix}{self.label_counter}"

    def alloc_reg(self) -> str:
        if not self.reg_free:
            # Very simple fallback: use r13 (caller-saved stack pointer temp)
            return "r13"
        return self.reg_free.pop(0)

    def free_reg(self, reg: str):
        if reg and reg.startswith('r') and reg not in self.reg_free and reg in abi.TEMP_REGS:
            self.reg_free.insert(0, reg)

    def emit_translation_unit(self, ast: Dict[str, Any], out_path: str):
        out_file = Path(out_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with out_file.open('w') as f:
            f.write("// Generated .ros by rospocc.emitter (starter)\n")
            f.write("// Functions\n")
            f.write('.SEG 0xFFFF_FFFC\n')
            funcs = ast.get('functions', [])
            # collect globals types (strings etc.)
            for g in ast.get('globals', []):
                if g.get('kind') == 'string':
                    # mark global label as char pointer
                    self.global_types[g.get('name')] = 'char_ptr'
            main_label = None
            if funcs:
                for fn in funcs:
                    if fn.get('name') == 'main':
                        main_label = 'main'
                        break
                if main_label is None and funcs:
                    # pick first function as entry
                    main_label = funcs[0].get('name') or 'main'
            f.write(".DATA 0x00000000\n\n")
            if main_label:
                f.write('.SEG 0x00000000\n\n')
                # Place a small bootstrap that jumps to main as the first code
                f.write(f'  JMP {main_label}\n\n')
            else:
                # No functions found; emit a generic segment header
                f.write('.SEG 0x00000000\n\n')
            # Functions
            for fn in ast.get('functions', []):
                self.emit_function_def(fn, f)
            f.write("\n// Globals\n\n")
            # Globals (very small handling)
            for g in ast.get('globals', []):
                self.emit_global_declaration(g, f)
            f.write("\n")

    def emit_global_declaration(self, g: Dict[str, Any], out):
        # Starter supports simple string/global labels
        if g.get('kind') == 'string':
            lbl = g.get('name') or self.gen_label('str')
            s = g.get('value', '')
            out.write(f"{lbl}:\n")
            out.write(f"  .STR \"{s}\"\n\n")
        else:
            # unknown global; emit a commented placeholder
            out.write(f"// global: {g!r}\n")

    def emit_function_def(self, fn: Dict[str, Any], out):
        name = fn.get('name', 'fn')
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
        params = fn.get('params', []) or []
        for i, p in enumerate(params[: len(abi.ARG_REGS)]):
            self.var_regs[p] = abi.ARG_REGS[i]
        # import any parameter type hints (e.g., pointer params)
        for pname, ptype in (fn.get('param_types', {}) or {}).items():
            self.var_types[pname] = ptype

        # per-function flag: whether a return was emitted inside body
        self.had_return = False

        # Emit body
        for stmt in fn.get('body', []):
            self.emit_statement(stmt, out)

        # If no return was emitted in the body, emit epilogue and return 0
        if not getattr(self, 'had_return', False):
            out.write(f"  // epilogue and return\n")
            out.write(f"  ADDI {abi.RETURN_REG}, {abi.SPECIAL_REGS['zero']}, 0  // ensure r1=0\n")
            out.write(f"  POP {abi.LINK_REG}\n")
            out.write(f"  RET\n\n")
        else:
            # already emitted return(s); do not append another epilogue/RET
            out.write("\n")

    def emit_statement(self, stmt: Dict[str, Any], out):
        t = stmt.get('type')
        if t == 'return':
            val = stmt.get('value')
            reg = self.emit_expr(val, out)
            if reg:
                # if the value is already in RETURN_REG, avoid redundant move
                if reg != abi.RETURN_REG:
                    out.write(f"  ADD {abi.RETURN_REG}, {reg}, {abi.SPECIAL_REGS['zero']}\n")
                if reg in abi.TEMP_REGS:
                    self.free_reg(reg)
            # restore link register before returning
            out.write(f"  POP {abi.LINK_REG}\n")
            out.write("  RET\n")
            # mark that this function emitted a return so we don't append another
            self.had_return = True
        elif t == 'decl':
            name = stmt.get('name')
            init = stmt.get('init')
            if init:
                if init.get('type') == 'const':
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    # simple hint: integer local
                    self.var_types[name] = 'int'
                    out.write(f"  LLI {r}, {int(init.get('value'))}    // init {name}\n")
                elif init.get('type') == 'call':
                    # emit call and move return value to var
                    self._emit_call(init, out)
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    # if calling malloc, assume pointer to int returned
                    if isinstance(init.get('name'), str) and init.get('name') == 'malloc':
                        self.var_types[name] = 'int_ptr'
                    else:
                        # default guess: integer value
                        self.var_types[name] = 'int'
                    out.write(f"  ADDI {r}, {abi.RETURN_REG}, 0\n")
                elif init.get('type') == 'string_addr':
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    self.var_types[name] = 'char_ptr'
                    out.write(f"  LLI {r}, {init.get('label')}    // init {name} (string addr)\n")
                else:
                    out.write(f"  // decl {name} with unsupported init {init!r}\n")
            else:
                # default initialize to 0
                r = self.alloc_reg()
                self.var_regs[name] = r
                self.var_types[name] = 'int'
                out.write(f"  LLI {r}, 0    // zero init {name}\n")
        elif t == 'assign':
            target = stmt.get('target')
            val = stmt.get('value')
            # assignment to a deref target: store to memory
            if isinstance(target, dict) and target.get('type') == 'deref':
                addr_expr = target.get('expr')
                # compute target address
                raddr = self.emit_expr(addr_expr, out)
                # compute value to store
                if val.get('type') == 'call':
                    self._emit_call(val, out)
                    rval = abi.RETURN_REG
                else:
                    rval = self.emit_expr(val, out)

                # heuristic: if address expr refers to a known char pointer, store byte
                store_instr = 'SW'
                if isinstance(addr_expr, dict) and addr_expr.get('type') == 'var':
                    vname = addr_expr.get('name')
                    if self.var_types.get(vname) == 'char_ptr':
                        store_instr = 'SB'
                # default: if value looks like a char const, prefer SB
                if val.get('type') == 'const':
                    try:
                        vv = int(val.get('value'), 0)
                        if 0 <= vv <= 0xFF:
                            store_instr = 'SB'
                    except Exception:
                        pass

                out.write(f"  {store_instr} {rval}, {raddr}, 0\n")
                if raddr in abi.TEMP_REGS:
                    self.free_reg(raddr)
                if rval in abi.TEMP_REGS:
                    self.free_reg(rval)
            else:
                # regular var-to-var assignment
                if val.get('type') == 'call':
                    self._emit_call(val, out)
                    # ensure target has a register
                    if target not in self.var_regs:
                        self.var_regs[target] = self.alloc_reg()
                    r = self.var_regs[target]
                    out.write(f"  ADDI {r}, {abi.RETURN_REG}, 0\n")
                else:
                    rsrc = self.emit_expr(val, out)
                    if target not in self.var_regs:
                        self.var_regs[target] = self.alloc_reg()
                    rdst = self.var_regs[target]
                    out.write(f"  ADDI {rdst}, {rsrc}, 0\n")
                    if rsrc in abi.TEMP_REGS:
                        self.free_reg(rsrc)
        elif t == 'call_stmt':
            # call with no use of return
            name = stmt.get('name')
            args = stmt.get('args', [])
            call_expr = {'type': 'call', 'name': name, 'args': args}
            self._emit_call(call_expr, out)
        elif t == 'while':
            # emit simple while loop: evaluate cond, branch to end if zero
            lbl_start = self.gen_label('WHILE_START')
            lbl_end = self.gen_label('WHILE_END')
            out.write(f"{lbl_start}:\n")
            cond = stmt.get('cond')
            # if condition is a pointer variable (e.g., str) treat while(ptr) as while(*ptr)
            if isinstance(cond, dict) and cond.get('type') == 'var' and self.var_types.get(cond.get('name')) == 'char_ptr':
                cond_expr = {'type': 'deref', 'expr': {'type': 'var', 'name': cond.get('name')}}
                rcond = self.emit_expr(cond_expr, out)
            else:
                rcond = self.emit_expr(cond, out)
            # pick a register to test (use r0 if no cond produced)
            rcond_reg = rcond if rcond else abi.SPECIAL_REGS['zero']
            # if cond == 0 jump to end
            out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_end}\n")
            # emit body
            for s in stmt.get('body', []):
                self.emit_statement(s, out)
            out.write(f"  JMP {lbl_start}\n")
            out.write(f"{lbl_end}:\n")
            if rcond and rcond in abi.TEMP_REGS:
                self.free_reg(rcond)
        elif t == 'if':
            cond = stmt.get('cond')
            then_stmts = stmt.get('then', []) or stmt.get('body', [])
            else_stmts = stmt.get('else', [])
            lbl_else = self.gen_label('IF_ELSE')
            lbl_end = self.gen_label('IF_END')
            # support pointer-as-condition heuristics
            if isinstance(cond, dict) and cond.get('type') == 'var' and self.var_types.get(cond.get('name')) == 'char_ptr':
                cond_expr = {'type': 'deref', 'expr': {'type': 'var', 'name': cond.get('name')}}
                rcond = self.emit_expr(cond_expr, out)
            else:
                rcond = self.emit_expr(cond, out)
            rcond_reg = rcond if rcond else abi.SPECIAL_REGS['zero']
            out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_else}\n")
            if rcond and rcond in abi.TEMP_REGS:
                self.free_reg(rcond)

            # then block
            for s in then_stmts:
                self.emit_statement(s, out)
            out.write(f"  JMP {lbl_end}\n")

            # else block
            out.write(f"{lbl_else}:\n")
            if else_stmts:
                for s in else_stmts:
                    self.emit_statement(s, out)

            out.write(f"{lbl_end}:\n")
        else:
            out.write(f"  // unsupported-stmt {stmt!r}\n")

    def emit_expr(self, expr: Dict[str, Any], out) -> str:
        if expr is None:
            return ''
        t = expr.get('type')
        if t == 'const':
            v = int(expr.get('value', 0))
            # Try to use an immediate add into a register
            r = self.alloc_reg()
            # Use LLI pseudo for generic immediates (assembler can lower it)
            out.write(f"  LLI {r}, {v}    // load immediate {v}\n")
            return r
        if t == 'var':
            name = expr.get('name')
            r = self.var_regs.get(name)
            if r:
                return r
            # unknown var — allocate and zero-initialize
            r = self.alloc_reg()
            self.var_regs[name] = r
            out.write(f"  LLI {r}, 0    // implicit init {name}\n")
            return r
        if t == 'deref':
            # load byte from address expr
            inner = expr.get('expr')
            raddr = self.emit_expr(inner, out)
            rd = self.alloc_reg()
            # choose load width heuristically: if inner is a known char pointer -> LB, else LW
            load_instr = 'LW'
            if isinstance(inner, dict) and inner.get('type') == 'var':
                v = inner.get('name')
                if self.var_types.get(v) == 'char_ptr':
                    load_instr = 'LB'
            out.write(f"  {load_instr} {rd}, {raddr}, 0    // deref\n")
            if raddr in abi.TEMP_REGS:
                self.free_reg(raddr)
            return rd
        if t == 'call':
            # emit call (may be intrinsic)
            self._emit_call(expr, out)
            # return value is in RETURN_REG
            return abi.RETURN_REG
        if t == 'binop':
            op = expr.get('op')
            left = expr.get('left')
            right = expr.get('right')
            rl = self.emit_expr(left, out)
            rr = self.emit_expr(right, out)
            rd = self.alloc_reg()

            # arithmetic and bitwise ops
            if op == '+':
                out.write(f"  ADD {rd}, {rl}, {rr}    // binop +\n")
            elif op == '-':
                out.write(f"  SUB {rd}, {rl}, {rr}    // binop -\n")
            elif op == '*':
                out.write(f"  MUL {rd}, {rl}, {rr}    // binop *\n")
            elif op == '/':
                out.write(f"  DIV {rd}, {rl}, {rr}    // binop /\n")
            elif op == '%':
                out.write(f"  REM {rd}, {rl}, {rr}    // binop %\n")
            elif op == '&':
                out.write(f"  AND {rd}, {rl}, {rr}    // binop &\n")
            elif op == '|':
                out.write(f"  OR {rd}, {rl}, {rr}    // binop |\n")
            elif op == '^':
                out.write(f"  XOR {rd}, {rl}, {rr}    // binop ^\n")
            elif op == '<<':
                out.write(f"  SHL {rd}, {rl}, {rr}    // binop <<\n")
            elif op == '>>':
                out.write(f"  SHR {rd}, {rl}, {rr}    // binop >>\n")

            # comparisons: produce 0/1 in rd
            elif op in ('==', '!=', '<', '<=', '>', '>='):
                # default rd = 0
                out.write(f"  LLI {rd}, 0    // compare init 0\n")
                ltrue = self.gen_label('CMP_TRUE')
                lend = self.gen_label('CMP_END')
                if op == '==':
                    out.write(f"  BEQ {rl}, {rr}, {ltrue}\n")
                elif op == '!=':
                    out.write(f"  BNE {rl}, {rr}, {ltrue}\n")
                elif op == '<':
                    out.write(f"  BLT {rl}, {rr}, {ltrue}\n")
                elif op == '<=':
                    out.write(f"  BGE {rr}, {rl}, {ltrue}\n")
                elif op == '>':
                    out.write(f"  BLT {rr}, {rl}, {ltrue}\n")
                elif op == '>=':
                    out.write(f"  BGE {rl}, {rr}, {ltrue}\n")
                out.write(f"  JMP {lend}\n")
                out.write(f"{ltrue}:\n")
                out.write(f"  LLI {rd}, 1\n")
                out.write(f"{lend}:\n")
                # Note: do not free rd here; caller uses it
            else:
                out.write(f"  // unsupported binop {op}\n")

            if rl in abi.TEMP_REGS:
                self.free_reg(rl)
            if rr in abi.TEMP_REGS:
                self.free_reg(rr)
            return rd
        elif t == 'string_addr':
            lbl = expr.get('label')
            r = self.alloc_reg()
            out.write(f"  LLI {r}, {lbl}    // load address of string {lbl}\n")
            return r
        else:
            out.write(f"  // unsupported-expr {expr!r}\n")
            return ''

    def _emit_call(self, call_expr: Dict[str, Any], out):
        name = call_expr.get('name')
        args = call_expr.get('args', [])

        # Intrinsic handling for names starting with __
        if isinstance(name, str) and name.startswith('__'):
            # support __lb(addr) -> LB RETURN_REG, addr_reg, 0
            if name == '__lb':
                # single arg: address
                a = args[0] if args else None
                if a is None:
                    out.write("  // __lb missing arg\n")
                    return
                # ensure address in a register
                if a.get('type') == 'const':
                    raddr = self.alloc_reg()
                    out.write(f"  LLI {raddr}, {int(a.get('value'))}    // addr const for __lb\n")
                elif a.get('type') == 'var':
                    raddr = self.var_regs.get(a.get('name'))
                    if not raddr:
                        raddr = self.alloc_reg()
                        self.var_regs[a.get('name')] = raddr
                        out.write(f"  LLI {raddr}, 0    // implicit init {a.get('name')}\n")
                else:
                    # expression
                    raddr = self.emit_expr(a, out)

                out.write(f"  LB {abi.RETURN_REG}, {raddr}, 0    // intrinsic __lb -> return\n")
                if raddr in abi.TEMP_REGS:
                    self.free_reg(raddr)
                return

            if name == '__sb':
                # args: addr, value  OR value, addr? In source uses __sb(tty_addr, *str)
                # We'll support (addr, value)
                if len(args) < 2:
                    out.write("  // __sb missing args\n")
                    return
                a_addr = args[0]
                a_val = args[1]
                # prepare regs
                if a_addr.get('type') == 'const':
                    raddr = self.alloc_reg()
                    out.write(f"  LLI {raddr}, {int(a_addr.get('value'))}    // addr const for __sb\n")
                elif a_addr.get('type') == 'var':
                    raddr = self.var_regs.get(a_addr.get('name'))
                    if not raddr:
                        raddr = self.alloc_reg()
                        self.var_regs[a_addr.get('name')] = raddr
                        out.write(f"  LLI {raddr}, 0    // implicit init {a_addr.get('name')}\n")
                else:
                    raddr = self.emit_expr(a_addr, out)

                if a_val.get('type') == 'const':
                    rval = self.alloc_reg()
                    out.write(f"  LLI {rval}, {int(a_val.get('value'))}    // val const for __sb\n")
                elif a_val.get('type') == 'var':
                    vname = a_val.get('name')
                    # if the var is a char pointer, load the byte it points to
                    if self.var_types.get(vname) == 'char_ptr':
                        # ensure we have the pointer register
                        rptr = self.var_regs.get(vname)
                        if not rptr:
                            rptr = self.alloc_reg()
                            self.var_regs[vname] = rptr
                            out.write(f"  LLI {rptr}, 0    // implicit init {vname}\n")
                        rval = self.alloc_reg()
                        out.write(f"  LB {rval}, {rptr}, 0    // load *{vname} for __sb\n")
                    else:
                        rval = self.var_regs.get(vname)
                        if not rval:
                            rval = self.alloc_reg()
                            self.var_regs[vname] = rval
                            out.write(f"  LLI {rval}, 0    // implicit init {vname}\n")
                else:
                    rval = self.emit_expr(a_val, out)

                out.write(f"  SB {rval}, {raddr}, 0    // intrinsic __sb\n")
                if raddr in abi.TEMP_REGS:
                    self.free_reg(raddr)
                if rval in abi.TEMP_REGS:
                    self.free_reg(rval)
                return

            # other intrinsics can be lowered similarly

        # Default: regular function call -> place up to 4 args into ARG_REGS then CALL
        for i, a in enumerate(args[: len(abi.ARG_REGS)]):
            dest = abi.ARG_REGS[i]
            if a.get('type') == 'const':
                out.write(f"  LLI {dest}, {int(a.get('value'))}    // arg {i}\n")
            elif a.get('type') == 'string_addr':
                out.write(f"  LLI {dest}, {a.get('label')}    // arg {i} string addr\n")
            elif a.get('type') == 'var':
                r = self.var_regs.get(a.get('name'))
                if r:
                    out.write(f"  ADDI {dest}, {r}, 0    // move arg {i}\n")
                else:
                    out.write(f"  LLI {dest}, 0    // arg {i} unknown var -> 0\n")
            else:
                out.write(f"  // unsupported arg type {a!r}\n")

        out.write(f"  CALL {call_expr.get('name')}\n")


def emit_translation_unit(ast: Dict[str, Any], out_path: str):
    e = Emitter()
    e.emit_translation_unit(ast, out_path)
