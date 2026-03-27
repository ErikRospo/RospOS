from typing import Any, Dict, Optional

import abi


def _is_char_ptr_expr(emitter, expr: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(expr, dict):
        return False

    et = expr.get("type")
    if et == "var":
        return emitter.var_types.get(expr.get("name")) == "char_ptr"

    if et == "binop" and expr.get("op") in ("plus", "minus"):
        left = expr.get("left")
        right = expr.get("right")
        return _is_char_ptr_expr(emitter, left) or _is_char_ptr_expr(emitter, right)

    return False


def _emit_const(emitter, expr: Dict[str, Any], out) -> str:
    v = int(expr.get("value", 0))
    r = emitter.alloc_reg()
    emitter._load_imm(r, v, out)
    return r


def _emit_var(emitter, expr: Dict[str, Any], out) -> str:
    name = expr.get("name")
    r = emitter.var_regs.get(name)
    if r:
        emitter.consume_var_read(name)
        return r
    if name in emitter.global_value_inits:
        reg = emitter._alloc_var_reg(
            name,
            out,
            init_value=emitter.global_value_inits[name],
            typ=emitter.global_types.get(name, "int"),
            is_label=True,
            comment="global symbol addr",
        )
        emitter.consume_var_read(name)
        return reg
    reg = emitter._alloc_var_reg(name, out, init_value=None, typ="int")
    emitter.consume_var_read(name)
    return reg


def _emit_deref(emitter, expr: Dict[str, Any], out) -> str:
    inner = expr.get("expr")
    raddr = emitter.emit_expr(inner, out)
    rd = raddr if (raddr and not emitter.is_var_reg(raddr)) else emitter.alloc_reg()
    load_instr = "LB" if _is_char_ptr_expr(emitter, inner) else "LW"
    out.write(f"  {load_instr} {rd}, {raddr}, 0    // deref\n")
    if rd != raddr:
        emitter.release_expr_reg(raddr)
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

        emitter.release_expr_reg(base_expr)
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

    # Protect variable registers used by the opposite operand while evaluating
    # each side. This prevents spill fallback from clobbering not-yet-evaluated
    # operand values under heavy register pressure.
    right_vars = emitter.get_expr_read_vars(right)
    pinned_for_left = []
    for vname in right_vars:
        pinned_reg = emitter.var_regs.get(vname)
        if pinned_reg:
            emitter.pin_reg(pinned_reg)
            pinned_for_left.append(pinned_reg)

    rl = emitter.emit_expr(left, out)

    for pinned_reg in reversed(pinned_for_left):
        emitter.unpin_reg(pinned_reg)

    emitter.pin_reg(rl)

    left_vars = emitter.get_expr_read_vars(left)
    pinned_for_right = []
    for vname in left_vars:
        pinned_reg = emitter.var_regs.get(vname)
        if pinned_reg and pinned_reg != rl:
            emitter.pin_reg(pinned_reg)
            pinned_for_right.append(pinned_reg)

    rr = emitter.emit_expr(right, out)

    for pinned_reg in reversed(pinned_for_right):
        emitter.unpin_reg(pinned_reg)

    emitter.unpin_reg(rl)

    if not rl or not rr:
        out.write(f"  // ERROR: failed to emit operands for binop {op}\n")
        if rl:
            emitter.release_expr_reg(rl)
        if rr:
            emitter.release_expr_reg(rr)
        return ""

    def _pick_dest_reg() -> str:
        if rl and rl in abi.TEMP_REGS and not emitter.is_var_reg(rl):
            return rl
        if rr and rr in abi.TEMP_REGS and not emitter.is_var_reg(rr):
            return rr
        return emitter.alloc_reg()

    rd = _pick_dest_reg()

    def _release_operands_for_result():
        if rd == rl and rd == rr:
            return
        if rd == rl:
            emitter.release_expr_reg(rr)
            return
        if rd == rr:
            emitter.release_expr_reg(rl)
            return
        emitter.release_expr_reg(rl)
        emitter.release_expr_reg(rr)

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
    elif op == "land":
        out.write(f"  AND {rd}, {rl}, {rr}    // logic && fold\n")
        emitter._emit_compare(rd, "neq", rd, abi.SPECIAL_REGS["zero"], out)
    elif op == "lor":
        out.write(f"  OR {rd}, {rl}, {rr}    // logic || fold\n")
        emitter._emit_compare(rd, "neq", rd, abi.SPECIAL_REGS["zero"], out)
    elif op == "lshift":
        out.write(f"  SHL {rd}, {rl}, {rr}    // binop <<\n")
    elif op == "rshift":
        out.write(f"  SHR {rd}, {rl}, {rr}    // binop >>\n")
    elif op in ("lt", "lte", "gt", "gte", "eq", "neq"):
        emitter._emit_compare(rd, op, rl, rr, out)
    else:
        out.write(f"  // unsupported binop {op}\n")

    _release_operands_for_result()
    return rd


def _emit_unop(emitter, expr: Dict[str, Any], out) -> str:
    print(f"unop expr: {expr!r}")
    op = expr.get("op")
    if op == "not":
        operand = expr.get("operand")
        assert operand is not None, "unop 'not' missing operand"
        r_operand = emitter.emit_expr(operand, out)
        rd = (
            r_operand
            if r_operand and r_operand in abi.TEMP_REGS and not emitter.is_var_reg(r_operand)
            else emitter.alloc_reg()
        )
        nt_label = emitter.gen_label("UNOP_NOT_TRUE")
        ne_label = emitter.gen_label("UNOP_NOT_END")
        out.write(f"  BEQ {r_operand}, {abi.SPECIAL_REGS['zero']}, {nt_label}\n")
        out.write(f"  LLI {rd}, 0    // operand is nonzero -> false\n")
        out.write(f"  JMP {ne_label}\n")
        out.write(f"{nt_label}:\n")
        out.write(f"  LLI {rd}, 1    // operand is zero -> true\n")
        out.write(f"{ne_label}:\n")
        if rd != r_operand:
            emitter.release_expr_reg(r_operand)
        return rd
    return ""


def _emit_string_addr(emitter, expr: Dict[str, Any], out) -> str:
    lbl = expr.get("label")
    r = emitter.alloc_reg()
    emitter._load_imm(r, lbl, out)
    return r


def _emit_assign_expr(emitter, expr: Dict[str, Any], out) -> str:
    target = expr.get("target")
    value_expr = expr.get("value")
    rval = emitter.emit_expr(value_expr, out)
    if not rval:
        out.write("  // ERROR: assign-expr has no rhs register\n")
        return ""

    result = rval

    if isinstance(target, dict) and target.get("type") == "deref":
        addr_expr = target.get("expr")
        emitter.pin_reg(rval)
        raddr = emitter.emit_expr(addr_expr, out)
        emitter.unpin_reg(rval)
        if raddr:
            store_instr = "SB" if _is_char_ptr_expr(emitter, addr_expr) else "SW"
            out.write(f"  {store_instr} {rval}, {raddr}, 0    // store (assign-expr)\n")
            emitter.release_expr_reg(raddr)
        else:
            out.write("  // ERROR: assign-expr deref target has no address register\n")
    elif isinstance(target, dict) and target.get("type") == "var":
        name = target.get("name")
        dest = emitter.var_regs.get(name)
        if dest:
            out.write(f"  ADDI {dest}, {rval}, 0    // assign-expr {name}\n")
            result = dest
        else:
            emitter.var_regs[name] = rval
            if name not in emitter.var_types:
                emitter.var_types[name] = "int"
            result = rval
    elif isinstance(target, str):
        dest = emitter.var_regs.get(target)
        if dest:
            out.write(f"  ADDI {dest}, {rval}, 0    // assign-expr {target}\n")
            result = dest
        else:
            emitter.var_regs[target] = rval
            if target not in emitter.var_types:
                emitter.var_types[target] = "int"
            result = rval
    else:
        out.write(f"  // assign-expr to unsupported target {target!r}\n")

    if rval != result:
        emitter.release_expr_reg(rval)

    return result


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
    "assign": _emit_assign_expr,
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
