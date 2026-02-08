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
            f.write("; Generated .ros by rospocc.emitter (starter)\n")
            f.write(".SEG 0x00DEADBE\n\n")

            # Globals (very small handling)
            for g in ast.get('globals', []):
                self.emit_global_declaration(g, f)

            # Functions
            for fn in ast.get('functions', []):
                self.emit_function_def(fn, f)

    def emit_global_declaration(self, g: Dict[str, Any], out):
        # Starter supports simple string/global labels
        if g.get('kind') == 'string':
            lbl = g.get('name') or self.gen_label('str')
            s = g.get('value', '')
            out.write(f"{lbl}:\n")
            out.write(f"  .STR \"{s}\"\n\n")
        else:
            # unknown global; emit a commented placeholder
            out.write(f"; global: {g!r}\n")

    def emit_function_def(self, fn: Dict[str, Any], out):
        name = fn.get('name', 'fn')
        out.write(f".FUNC {name}:\n")
        # Minimal prologue comment
        out.write(f"  ; prologue (minimal)\n")
        # Reset allocator state per function
        self.reg_free = list(abi.TEMP_REGS)
        self.var_regs = {}

        # Handle parameters: map param names to argument registers (r1..r4)
        params = fn.get('params', []) or []
        for i, p in enumerate(params[: len(abi.ARG_REGS)]):
            self.var_regs[p] = abi.ARG_REGS[i]

        # Emit body
        for stmt in fn.get('body', []):
            self.emit_statement(stmt, out)

        # Ensure function returns; if no return emitted, return 0
        out.write(f"  ; epilogue and return\n")
        out.write(f"  ADDI {abi.RETURN_REG}, {abi.SPECIAL_REGS['zero']}, 0  ; ensure r1=0\n")
        out.write(f"  RET\n\n")

    def emit_statement(self, stmt: Dict[str, Any], out):
        t = stmt.get('type')
        if t == 'return':
            val = stmt.get('value')
            reg = self.emit_expr(val, out)
            if reg:
                out.write(f"  ADD {abi.RETURN_REG}, {reg}, {abi.SPECIAL_REGS['zero']}\n")
                # don't free if it's a parameter register
                if reg in abi.TEMP_REGS:
                    self.free_reg(reg)
            out.write("  RET\n")
        elif t == 'decl':
            name = stmt.get('name')
            init = stmt.get('init')
            if init:
                if init.get('type') == 'const':
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    out.write(f"  LLI {r}, {int(init.get('value'))}    ; init {name}\n")
                elif init.get('type') == 'call':
                    # emit call and move return value to var
                    self._emit_call(init, out)
                    r = self.alloc_reg()
                    self.var_regs[name] = r
                    out.write(f"  ADDI {r}, {abi.RETURN_REG}, 0\n")
                else:
                    out.write(f"  ; decl {name} with unsupported init {init!r}\n")
            else:
                # default initialize to 0
                r = self.alloc_reg()
                self.var_regs[name] = r
                out.write(f"  LLI {r}, 0    ; zero init {name}\n")
        elif t == 'assign':
            target = stmt.get('target')
            val = stmt.get('value')
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
            rcond = self.emit_expr(cond, out)
            # if cond == 0 jump to end
            out.write(f"  BEQ {rcond}, {abi.SPECIAL_REGS['zero']}, {lbl_end}\n")
            # emit body
            for s in stmt.get('body', []):
                self.emit_statement(s, out)
            out.write(f"  JMP {lbl_start}\n")
            out.write(f"{lbl_end}:\n")
            if rcond in abi.TEMP_REGS:
                self.free_reg(rcond)
        else:
            out.write(f"  ; unsupported-stmt {stmt!r}\n")

    def emit_expr(self, expr: Dict[str, Any], out) -> str:
        if expr is None:
            return ''
        t = expr.get('type')
        if t == 'const':
            v = int(expr.get('value', 0))
            # Try to use an immediate add into a register
            r = self.alloc_reg()
            # Use LLI pseudo for generic immediates (assembler can lower it)
            out.write(f"  LLI {r}, {v}    ; load immediate {v}\n")
            return r
        if t == 'var':
            name = expr.get('name')
            r = self.var_regs.get(name)
            if r:
                return r
            # unknown var — allocate and zero-initialize
            r = self.alloc_reg()
            self.var_regs[name] = r
            out.write(f"  LLI {r}, 0    ; implicit init {name}\n")
            return r
        if t == 'deref':
            # load byte from address expr
            inner = expr.get('expr')
            raddr = self.emit_expr(inner, out)
            rd = self.alloc_reg()
            out.write(f"  LB {rd}, {raddr}, 0    ; deref\n")
            if raddr in abi.TEMP_REGS:
                self.free_reg(raddr)
            return rd
        if t == 'call':
            # emit call (may be intrinsic)
            self._emit_call(expr, out)
            # return value is in RETURN_REG
            return abi.RETURN_REG
        if t == 'var':
            name = expr.get('name')
            r = self.var_regs.get(name)
            if r:
                return r
            # unknown var — allocate and zero-initialize
            r = self.alloc_reg()
            self.var_regs[name] = r
            out.write(f"  LLI {r}, 0    ; implicit init {name}\n")
            return r
        if t == 'binop':
            op = expr.get('op')
            left = expr.get('left')
            right = expr.get('right')
            rl = self.emit_expr(left, out)
            rr = self.emit_expr(right, out)
            rd = self.alloc_reg()
            if op == '+':
                out.write(f"  ADD {rd}, {rl}, {rr}    ; binop +\n")
            elif op == '-':
                out.write(f"  SUB {rd}, {rl}, {rr}    ; binop -\n")
            else:
                out.write(f"  ; unsupported binop {op}\n")
            if rl in abi.TEMP_REGS:
                self.free_reg(rl)
            if rr in abi.TEMP_REGS:
                self.free_reg(rr)
            return rd
        elif t == 'string_addr':
            lbl = expr.get('label')
            r = self.alloc_reg()
            out.write(f"  LDI {r}, {lbl}    ; load address of string {lbl}\n")
            return r
        else:
            out.write(f"  ; unsupported-expr {expr!r}\n")
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
                    out.write("  ; __lb missing arg\n")
                    return
                # ensure address in a register
                if a.get('type') == 'const':
                    raddr = self.alloc_reg()
                    out.write(f"  LLI {raddr}, {int(a.get('value'))}    ; addr const for __lb\n")
                elif a.get('type') == 'var':
                    raddr = self.var_regs.get(a.get('name'))
                    if not raddr:
                        raddr = self.alloc_reg()
                        self.var_regs[a.get('name')] = raddr
                        out.write(f"  LLI {raddr}, 0    ; implicit init {a.get('name')}\n")
                else:
                    # expression
                    raddr = self.emit_expr(a, out)

                out.write(f"  LB {abi.RETURN_REG}, {raddr}, 0    ; intrinsic __lb -> return\n")
                if raddr in abi.TEMP_REGS:
                    self.free_reg(raddr)
                return

            if name == '__sb':
                # args: addr, value  OR value, addr? In source uses __sb(tty_addr, *str)
                # We'll support (addr, value)
                if len(args) < 2:
                    out.write("  ; __sb missing args\n")
                    return
                a_addr = args[0]
                a_val = args[1]
                # prepare regs
                if a_addr.get('type') == 'const':
                    raddr = self.alloc_reg()
                    out.write(f"  LLI {raddr}, {int(a_addr.get('value'))}    ; addr const for __sb\n")
                elif a_addr.get('type') == 'var':
                    raddr = self.var_regs.get(a_addr.get('name'))
                    if not raddr:
                        raddr = self.alloc_reg()
                        self.var_regs[a_addr.get('name')] = raddr
                        out.write(f"  LLI {raddr}, 0    ; implicit init {a_addr.get('name')}\n")
                else:
                    raddr = self.emit_expr(a_addr, out)

                if a_val.get('type') == 'const':
                    rval = self.alloc_reg()
                    out.write(f"  LLI {rval}, {int(a_val.get('value'))}    ; val const for __sb\n")
                elif a_val.get('type') == 'var':
                    rval = self.var_regs.get(a_val.get('name'))
                    if not rval:
                        rval = self.alloc_reg()
                        self.var_regs[a_val.get('name')] = rval
                        out.write(f"  LLI {rval}, 0    ; implicit init {a_val.get('name')}\n")
                else:
                    rval = self.emit_expr(a_val, out)

                out.write(f"  SB {rval}, {raddr}, 0    ; intrinsic __sb\n")
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
                out.write(f"  LLI {dest}, {int(a.get('value'))}    ; arg {i}\n")
            elif a.get('type') == 'string_addr':
                out.write(f"  LDI {dest}, {a.get('label')}    ; arg {i} string addr\n")
            elif a.get('type') == 'var':
                r = self.var_regs.get(a.get('name'))
                if r:
                    out.write(f"  ADDI {dest}, {r}, 0    ; move arg {i}\n")
                else:
                    out.write(f"  LLI {dest}, 0    ; arg {i} unknown var -> 0\n")
            else:
                out.write(f"  ; unsupported arg type {a!r}\n")

        out.write(f"  CALL {call_expr.get('name')}\n")


def emit_translation_unit(ast: Dict[str, Any], out_path: str):
    e = Emitter()
    e.emit_translation_unit(ast, out_path)


if __name__ == '__main__':
    # Quick smoke example: emit a main returning 42
    example_ast = {
        'globals': [],
        'functions': [
            {
                'name': 'main',
                'body': [
                    {'type': 'return', 'value': {'type': 'const', 'value': 42}}
                ]
            }
        ]
    }
    out = os.path.join(os.path.dirname(__file__), 'out', 'generated.ros')
    emit_translation_unit(example_ast, out)
    print('Wrote', out)
