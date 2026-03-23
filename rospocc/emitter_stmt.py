from typing import Any, Dict

import abi


def _emit_return(emitter, stmt: Dict[str, Any], out):
    val = stmt.get("value")
    reg = emitter.emit_expr(val, out)
    if reg:
        if reg != abi.RETURN_REG:
            out.write(f"  ADD {abi.RETURN_REG}, {reg}, {abi.SPECIAL_REGS['zero']}\n")
        if reg in abi.TEMP_REGS:
            emitter.free_reg(reg)
    out.write(f"  POP {abi.LINK_REG}\n")
    out.write("  RET\n")
    emitter.had_return = True


def _emit_decl(emitter, stmt: Dict[str, Any], out):
    name = stmt.get("name")
    assert isinstance(name, str), "Expected variable name as string in decl"
    decl_type = stmt.get("decl_type")
    init = stmt.get("init")

    if decl_type and decl_type in emitter.struct_types:
        struct_def = emitter.struct_types[decl_type]
        struct_size = struct_def.get("size", 0)
        lbl = emitter.gen_label(f"{name}_struct")
        emitter.global_spaces.append({"name": lbl, "size": struct_size})
        emitter._alloc_var_reg(
            name,
            out,
            init_value=lbl,
            typ=decl_type,
            is_label=True,
            comment=f"struct {decl_type} addr",
        )
        return

    if init:
        if init.get("type") == "const":
            val = int(init.get("value"))
            assert isinstance(val, int), "Expected integer constant initializer"
            emitter._alloc_var_reg(name, out, init_value=val, typ="int")
        elif init.get("type") == "array":
            size = int(init.get("size", 0))
            lbl = emitter.gen_label(f"{name}_buf")
            emitter.global_spaces.append({"name": lbl, "size": size})
            emitter._alloc_var_reg(
                name,
                out,
                init_value=lbl,
                typ="char_ptr",
                is_label=True,
                comment="buffer addr",
            )
        elif init.get("type") == "call":
            r = emitter._alloc_var_reg(name, out, init_value=None, typ="int")
            emitter._emit_call(init, r, out)
            emitter.var_regs[name] = r
            if isinstance(init.get("name"), str) and init.get("name") == "malloc":
                emitter.var_types[name] = "int_ptr"
            else:
                emitter.var_types[name] = "int"
        elif init.get("type") == "string_addr":
            emitter._alloc_var_reg(
                name,
                out,
                init_value=init.get("label"),
                typ="char_ptr",
                is_label=True,
                comment="string addr",
            )
        else:
            out.write(f"  // decl {name} with unsupported init {init!r}\n")
        return

    emitter._alloc_var_reg(name, out, init_value=None, typ="int")


def _emit_assign_member_access(emitter, target: Dict[str, Any], rval: str, out):
    op = target.get("op")
    base = target.get("base")
    member_name = target.get("member")

    if not base or not member_name:
        out.write("  // ERROR: missing base or member in member_access assignment\n")
        return

    if op == ".":
        if base.get("type") == "var":
            base_name = base.get("name")
            base_type = emitter.var_types.get(base_name)
            struct_def = emitter.struct_types.get(base_type)
            member_offset = None

            if not struct_def:
                out.write(f"  // ERROR: unknown struct type for {base_name}\n")
            else:
                for m in struct_def.get("members", []):
                    if m.get("name") == member_name:
                        member_offset = m.get("offset", 0)
                        break

            if member_offset is None:
                out.write(f"  // ERROR: member {member_name} not found\n")
            else:
                base_reg = emitter.var_regs.get(base_name)
                if member_offset < 2**16:
                    out.write(
                        f"  SW {rval}, {base_reg}, {member_offset}    // store {base_name}.{member_name}\n"
                    )
                else:
                    offset_reg = emitter.alloc_reg()
                    emitter._load_imm(offset_reg, member_offset, out)
                    addr_reg = emitter.alloc_reg()
                    out.write(
                        f"  ADD {addr_reg}, {base_reg}, {offset_reg}    // calculate member addr\n"
                    )
                    out.write(
                        f"  SW {rval}, {addr_reg}, 0    // store {base_name}.{member_name}\n"
                    )
                    if offset_reg in abi.TEMP_REGS:
                        emitter.free_reg(offset_reg)
                    if addr_reg in abi.TEMP_REGS:
                        emitter.free_reg(addr_reg)
        return

    if op == "->":
        base_expr = emitter.emit_expr(base, out)

        struct_type_name = None
        if base.get("type") == "var":
            base_type = emitter.var_types.get(base.get("name"))
            if base_type and "_ptr" in base_type:
                struct_type_name = base_type.replace("_ptr", "")
            else:
                struct_type_name = base_type

        struct_def = emitter.struct_types.get(struct_type_name)
        if not struct_def:
            out.write("  // ERROR: unknown struct type for -> access\n")
        else:
            member_offset = None
            for m in struct_def.get("members", []):
                if m.get("name") == member_name:
                    member_offset = m.get("offset", 0)
                    break

            if member_offset is None:
                out.write(f"  // ERROR: member {member_name} not found\n")
            else:
                if member_offset < 2**16:
                    out.write(
                        f"  SW {rval}, {base_expr}, {member_offset}    // store ptr->{member_name}\n"
                    )
                else:
                    offset_reg = emitter.alloc_reg()
                    emitter._load_imm(offset_reg, member_offset, out)
                    addr_reg = emitter.alloc_reg()
                    out.write(
                        f"  ADD {addr_reg}, {base_expr}, {offset_reg}    // calculate member addr\n"
                    )
                    out.write(
                        f"  SW {rval}, {addr_reg}, 0    // store ptr->{member_name}\n"
                    )
                    if offset_reg in abi.TEMP_REGS:
                        emitter.free_reg(offset_reg)
                    if addr_reg in abi.TEMP_REGS:
                        emitter.free_reg(addr_reg)

        if base_expr in abi.TEMP_REGS:
            emitter.free_reg(base_expr)


def _emit_assign(emitter, stmt: Dict[str, Any], out):
    target = stmt.get("target")
    val = stmt.get("value")
    rval = emitter.emit_expr(val, out)

    if isinstance(target, dict) and target.get("type") == "member_access":
        _emit_assign_member_access(emitter, target, rval, out)
    elif isinstance(target, dict) and target.get("type") == "deref":
        addr_expr = target.get("expr")
        raddr = emitter.emit_expr(addr_expr, out)
        store_instr = "SW"
        if isinstance(addr_expr, dict) and addr_expr.get("type") == "var":
            if emitter.var_types.get(addr_expr.get("name")) == "char_ptr":
                store_instr = "SB"
        out.write(f"  {store_instr} {rval}, {raddr}, 0    // store \n")
        if raddr in abi.TEMP_REGS:
            emitter.free_reg(raddr)
    elif isinstance(target, dict) and target.get("type") == "var":
        name = target.get("name")
        dest = emitter.var_regs.get(name)
        if dest:
            out.write(f"  ADDI {dest}, {rval}, 0    // assign {name}\n")
        else:
            emitter.var_regs[name] = rval
            if name not in emitter.var_types:
                emitter.var_types[name] = "int"
            rval = None
    elif isinstance(target, str):
        dest = emitter.var_regs.get(target)
        if dest:
            out.write(f"  ADDI {dest}, {rval}, 0    // assign {target}\n")
        else:
            emitter.var_regs[target] = rval
            if target not in emitter.var_types:
                emitter.var_types[target] = "int"
            rval = None
    else:
        out.write(f"  // assign to unsupported target {target!r}\n")

    if rval and rval in abi.TEMP_REGS:
        emitter.free_reg(rval)


def _emit_if(emitter, stmt: Dict[str, Any], out):
    cond = stmt.get("cond")
    then_stmts = stmt.get("then", []) or []
    else_stmts = stmt.get("else", []) or []
    lbl_else = emitter.gen_label("ELSE")
    lbl_end = emitter.gen_label("IF_END")
    if isinstance(cond, dict) and cond.get("type") == "var":
        vname = cond.get("name")
        if emitter.var_types.get(vname) == "char_ptr":
            cond = {"type": "deref", "expr": cond}
    rcond = emitter.emit_expr(cond, out)
    rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
    out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_else}\n")
    if rcond and rcond in abi.TEMP_REGS:
        emitter.free_reg(rcond)
    for s in then_stmts:
        emitter.emit_statement(s, out)
    out.write(f"  JMP {lbl_end}\n")
    out.write(f"{lbl_else}:\n")
    for s in else_stmts:
        emitter.emit_statement(s, out)
    out.write(f"{lbl_end}:\n")


def _emit_call_stmt(emitter, stmt: Dict[str, Any], out):
    call_expr = {
        "type": "call",
        "name": stmt.get("name") or stmt.get("call", {}).get("name"),
        "args": stmt.get("args", []) or stmt.get("call", {}).get("args", []),
    }

    emitter._emit_call(
        {"name": call_expr.get("name"), "args": call_expr.get("args")},
        None,
        out,
    )


def _emit_while(emitter, stmt: Dict[str, Any], out):
    cond = stmt.get("cond")
    body = stmt.get("body", []) or []
    lbl_start = emitter.gen_label("WHILE")
    lbl_end = emitter.gen_label("WHILE_END")
    out.write(f"{lbl_start}:\n")
    if isinstance(cond, dict) and cond.get("type") == "var":
        vname = cond.get("name")
        if emitter.var_types.get(vname) == "char_ptr":
            cond = {"type": "deref", "expr": cond}
    rcond = emitter.emit_expr(cond, out)
    rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
    out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_end}\n")
    if rcond and rcond in abi.TEMP_REGS:
        emitter.free_reg(rcond)
    for s in body:
        emitter.emit_statement(s, out)
    out.write(f"  JMP {lbl_start}\n")
    out.write(f"{lbl_end}:\n")


def _emit_unsupported(emitter, stmt: Dict[str, Any], out):
    out.write(f"  // unsupported-stmt {stmt!r}\n")


STMT_DISPATCH = {
    "return": _emit_return,
    "decl": _emit_decl,
    "assign": _emit_assign,
    "if": _emit_if,
    "call_stmt": _emit_call_stmt,
    "while": _emit_while,
}


def emit_statement(emitter, stmt: Dict[str, Any], out):
    emitter._set_source_context(stmt, out)
    t = stmt.get("type")
    if not isinstance(t, str):
        _emit_unsupported(emitter, stmt, out)
        return

    handler = STMT_DISPATCH.get(t, _emit_unsupported)
    handler(emitter, stmt, out)
