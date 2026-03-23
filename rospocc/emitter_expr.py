from typing import Any, Dict, Optional

import abi


def _emit_const(emitter, expr: Dict[str, Any], out) -> str:
    v = int(expr.get("value", 0))
    r = emitter.alloc_reg()
    emitter._load_imm(r, v, out)
    return r


def _emit_var(emitter, expr: Dict[str, Any], out) -> str:
    name = expr.get("name")
    r = emitter.var_regs.get(name)
    if r:
        return r
    return emitter._alloc_var_reg(name, out, init_value=None, typ="int")


def _emit_deref(emitter, expr: Dict[str, Any], out) -> str:
    inner = expr.get("expr")
    raddr = emitter.emit_expr(inner, out)
    rd = emitter.alloc_reg()
    load_instr = "LW"
    if isinstance(inner, dict) and inner.get("type") == "var":
        v = inner.get("name")
        if emitter.var_types.get(v) == "char_ptr":
            load_instr = "LB"
    out.write(f"  {load_instr} {rd}, {raddr}, 0    // deref\n")
    if raddr in abi.TEMP_REGS:
        emitter.free_reg(raddr)
    return rd


def _emit_member_access(emitter, expr: Dict[str, Any], out) -> str:
    op = expr.get("op")
    base = expr.get("base")
    member_name = expr.get("member")

    if not base or not member_name:
        out.write("  // ERROR: missing base or member in member_access\n")
        return ""

    if op == ".":
        if base.get("type") == "var":
            base_name = base.get("name")
            base_type = emitter.var_types.get(base_name)

            struct_def = emitter.struct_types.get(base_type)
            if not struct_def:
                out.write(
                    f"  // ERROR: unknown struct type {base_type} for {base_name}\n"
                )
                return ""

            member_offset = None
            for m in struct_def.get("members", []):
                if m.get("name") == member_name:
                    member_offset = m.get("offset", 0)
                    break

            if member_offset is None:
                out.write(
                    f"  // ERROR: member {member_name} not found in {base_type}\n"
                )
                return ""

            base_reg = emitter.var_regs.get(base_name)
            if not base_reg:
                out.write(f"  // ERROR: variable {base_name} not in register\n")
                return ""

            rd = emitter.alloc_reg()
            if member_offset < 2**16:
                out.write(
                    f"  LW {rd}, {base_reg}, {member_offset}    // load {base_name}.{member_name}\n"
                )
            else:
                offset_reg = emitter.alloc_reg()
                emitter._load_imm(offset_reg, member_offset, out)
                addr_reg = emitter.alloc_reg()
                out.write(
                    f"  ADD {addr_reg}, {base_reg}, {offset_reg}    // {base_name} + offset\n"
                )
                out.write(
                    f"  LW {rd}, {addr_reg}, 0    // load {base_name}.{member_name}\n"
                )
                if offset_reg in abi.TEMP_REGS:
                    emitter.free_reg(offset_reg)
                if addr_reg in abi.TEMP_REGS:
                    emitter.free_reg(addr_reg)
            return rd

        out.write(f"  // ERROR: unsupported base for . operator: {base}\n")
        return ""

    if op == "->":
        base_expr = emitter.emit_expr(base, out)
        if not base_expr:
            out.write("  // ERROR: failed to emit base expr for ->\n")
            return ""

        struct_type_name = None
        if base.get("type") == "var":
            base_type = emitter.var_types.get(base.get("name"))
            if base_type and "_ptr" in base_type:
                struct_type_name = base_type.replace("_ptr", "")
            else:
                struct_type_name = base_type

        if not struct_type_name or struct_type_name not in emitter.struct_types:
            out.write("  // ERROR: cannot determine struct type for -> access\n")
            return ""

        struct_def = emitter.struct_types.get(struct_type_name)

        member_offset = None
        for m in struct_def.get("members", []):
            if m.get("name") == member_name:
                member_offset = m.get("offset", 0)
                break

        if member_offset is None:
            out.write(
                f"  // ERROR: member {member_name} not found in {struct_type_name}\n"
            )
            return ""

        rd = emitter.alloc_reg()
        if member_offset < 2**16:
            out.write(
                f"  LW {rd}, {base_expr}, {member_offset}    // load ptr->{member_name}\n"
            )
        else:
            offset_reg = emitter.alloc_reg()
            emitter._load_imm(offset_reg, member_offset, out)
            addr_reg = emitter.alloc_reg()
            out.write(
                f"  ADD {addr_reg}, {base_expr}, {offset_reg}    // ptr + offset\n"
            )
            out.write(f"  LW {rd}, {addr_reg}, 0    // load ptr->{member_name}\n")
            if offset_reg in abi.TEMP_REGS:
                emitter.free_reg(offset_reg)
            if addr_reg in abi.TEMP_REGS:
                emitter.free_reg(addr_reg)

        if base_expr in abi.TEMP_REGS:
            emitter.free_reg(base_expr)
        return rd

    out.write(f"  // ERROR: unsupported member access op {op}\n")
    return ""


def _emit_call(emitter, expr: Dict[str, Any], out) -> str:
    emitter._emit_call(expr, "r1", out)
    out.write(f"  // call expr {expr.get('name')} -> return in {abi.RETURN_REG}\n")
    return abi.RETURN_REG


def _emit_binop(emitter, expr: Dict[str, Any], out) -> str:
    op = expr.get("op")
    left = expr.get("left")
    right = expr.get("right")
    rl = emitter.emit_expr(left, out)
    rr = emitter.emit_expr(right, out)
    rd = emitter.alloc_reg()

    if op == "plus":
        out.write(f"  ADD {rd}, {rl}, {rr}    // binop +\n")
    elif op == "minus":
        out.write(f"  SUB {rd}, {rl}, {rr}    // binop -\n")
    elif op == "mult":
        out.write(f"  MUL {rd}, {rl}, {rr}    // binop *\n")
    elif op == "div":
        out.write(f"  DIV {rd}, {rl}, {rr}    // binop /\n")
    elif op == "mod":
        out.write(f"  REM {rd}, {rl}, {rr}    // binop %\n")
    elif op == "and":
        out.write(f"  AND {rd}, {rl}, {rr}    // binop &\n")
    elif op == "or":
        out.write(f"  OR {rd}, {rl}, {rr}    // binop |\n")
    elif op == "xor":
        out.write(f"  XOR {rd}, {rl}, {rr}    // binop ^\n")
    elif op == "lshift":
        out.write(f"  SHL {rd}, {rl}, {rr}    // binop <<\n")
    elif op == "rshift":
        out.write(f"  SHR {rd}, {rl}, {rr}    // binop >>\n")
    elif op in ("lt", "lte", "gt", "gte", "eq", "neq"):
        emitter._emit_compare(rd, op, rl, rr, out)
    else:
        out.write(f"  // unsupported binop {op}\n")

    if rl in abi.TEMP_REGS:
        emitter.free_reg(rl)
    if rr in abi.TEMP_REGS:
        emitter.free_reg(rr)
    return rd


def _emit_unop(emitter, expr: Dict[str, Any], out) -> str:
    print(f"unop expr: {expr!r}")
    op = expr.get("op")
    if op == "not":
        operand = expr.get("operand")
        assert operand is not None, "unop 'not' missing operand"
        r_operand = emitter.emit_expr(operand, out)
        rd = emitter.alloc_reg()
        nt_label = emitter.gen_label("UNOP_NOT_TRUE")
        ne_label = emitter.gen_label("UNOP_NOT_END")
        out.write(f"  BEQ {r_operand}, {abi.SPECIAL_REGS['zero']}, {nt_label}\n")
        out.write(f"  LLI {rd}, 0    // operand is nonzero -> false\n")
        out.write(f"  JMP {ne_label}\n")
        out.write(f"{nt_label}:\n")
        out.write(f"  LLI {rd}, 1    // operand is zero -> true\n")
        out.write(f"{ne_label}:\n")
    return ""


def _emit_string_addr(emitter, expr: Dict[str, Any], out) -> str:
    lbl = expr.get("label")
    r = emitter.alloc_reg()
    emitter._load_imm(r, lbl, out)
    return r


def _emit_unsupported(emitter, expr: Dict[str, Any], out) -> str:
    out.write(f"  // unsupported-expr {expr!r}\n")
    return ""


EXPR_DISPATCH = {
    "const": _emit_const,
    "var": _emit_var,
    "deref": _emit_deref,
    "member_access": _emit_member_access,
    "call": _emit_call,
    "binop": _emit_binop,
    "unop": _emit_unop,
    "string_addr": _emit_string_addr,
}


def emit_expr(emitter, expr: Optional[Dict[str, Any]], out) -> str:
    if expr is None:
        return ""

    t = expr.get("type")
    if not isinstance(t, str):
        return _emit_unsupported(emitter, expr, out)

    handler = EXPR_DISPATCH.get(t, _emit_unsupported)
    return handler(emitter, expr, out)
