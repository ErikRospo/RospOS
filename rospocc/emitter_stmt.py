from typing import Any, Dict

import abi


def _is_char_ptr_expr(emitter, expr):
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


def _emit_return(emitter, stmt: Dict[str, Any], out):
    val = stmt.get("value")
    reg = emitter.emit_expr(val, out)
    if reg:
        if reg != abi.RETURN_REG:
            out.write(f"  ADD {abi.RETURN_REG}, {reg}, {abi.SPECIAL_REGS['zero']}\n")
        emitter.release_expr_reg(reg)
    
    # If we're inside an inline function context, don't emit RET
    # Just set the return value and continue
    if emitter._in_inline_context:
        out.write(f"  // inline function return (no RET emitted)\n")
    else:
        out.write(f"  POP {abi.LINK_REG}\n")
        out.write("  RET\n")
    emitter.had_return = True


def _emit_decl(emitter, stmt: Dict[str, Any], out):
    name = stmt.get("name")
    assert isinstance(name, str), "Expected variable name as string in decl"
    emitter.note_var_declaration(name)
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
        elif init.get("type") == "array_init_string":
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

            # Initialize the lifted buffer bytes from the string literal.
            # Include a trailing NUL like C string initialization.
            init_bytes = (str(init.get("value", "")).encode("latin1", "replace") + b"\x00")[:size]
            base_reg = emitter.var_regs.get(name)
            if base_reg:
                for idx, byte_val in enumerate(init_bytes):
                    rval = emitter.alloc_reg()
                    emitter._load_imm(rval, int(byte_val), out)

                    off_reg = emitter.alloc_reg()
                    emitter._load_imm(off_reg, idx, out)

                    addr_reg = emitter.alloc_reg()
                    out.write(f"  ADD {addr_reg}, {base_reg}, {off_reg}    // {name}[{idx}] addr\n")
                    out.write(f"  SB {rval}, {addr_reg}, 0    // init {name}[{idx}]\n")

                    emitter.release_expr_reg(addr_reg)
                    emitter.release_expr_reg(off_reg)
                    emitter.release_expr_reg(rval)
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
            rinit = emitter.emit_expr(init, out)
            if rinit:
                # Prefer reusing initializer temp as the variable register to
                # avoid allocating one extra register under pressure.
                if rinit in abi.TEMP_REGS and not emitter.is_var_reg(rinit):
                    emitter.var_regs[name] = rinit
                    emitter.var_types[name] = "int"
                    if hasattr(emitter, "register_allocator") and hasattr(out, "get_current_output_line"):
                        emitter.register_allocator.set_output_line(out.get_current_output_line())
                        emitter.register_allocator.allocate(
                            register=rinit,
                            variable_name=name,
                            variable_type="int",
                            var_kind="local",
                            origin=emitter.current_context_origin,
                        )
                else:
                    dest = emitter._alloc_var_reg(name, out, init_value=None, typ="int")
                    out.write(f"  ADDI {dest}, {rinit}, 0    // init {name} from expr\n")
                    emitter.release_expr_reg(rinit)
        # Reclaim any variables that are now dead (all reads consumed)
        emitter.reclaim_dead_var_regs()
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

        emitter.release_expr_reg(base_expr)


def _emit_assign(emitter, stmt: Dict[str, Any], out):
    target = stmt.get("target")
    val = stmt.get("value")

    # Evaluate RHS first, and if assigning to a variable that is also used in the RHS,
    # force the result into a temp register to avoid clobbering.
    target_name = None
    if isinstance(target, dict) and target.get("type") == "var":
        target_name = target.get("name")
    elif isinstance(target, str):
        target_name = target

    # Fast path: x = x +/- const  ->  ADDI x, x, +/-const
    if (
        isinstance(val, dict)
        and val.get("type") == "binop"
        and target_name is not None
    ):
        op = val.get("op")
        left = val.get("left")
        right = val.get("right")

        def _var_name(node):
            if isinstance(node, dict) and node.get("type") == "var":
                return node.get("name")
            return None

        def _const_val(node):
            if isinstance(node, dict) and node.get("type") == "const":
                return int(node.get("value", 0))
            return None

        imm = None
        if op == "plus":
            if _var_name(left) == target_name and _const_val(right) is not None:
                imm = _const_val(right)
            elif _const_val(left) is not None and _var_name(right) == target_name:
                imm = _const_val(left)
        elif op == "minus":
            if _var_name(left) == target_name and _const_val(right) is not None:
                imm = -_const_val(right)

        if imm is not None:
            dest = emitter.var_regs.get(target_name)
            if dest:
                emitter.consume_var_read(target_name)
                out.write(f"  ADDI {dest}, {dest}, {imm}    // assign {target_name} (addi fast path)\n")
                emitter.reclaim_dead_var_regs()
                return

    # If the RHS is a binop and both operands are the same as the target, force temp
    force_temp = False
    if (
        isinstance(val, dict)
        and val.get("type") == "binop"
        and target_name is not None
    ):
        left = val.get("left")
        right = val.get("right")
        if (
            isinstance(left, dict)
            and left.get("type") == "var"
            and left.get("name") == target_name
        ) or (
            isinstance(right, dict)
            and right.get("type") == "var"
            and right.get("name") == target_name
        ):
            force_temp = True

    if force_temp:
        # Keep target mapped but pin its register so temporary allocation and
        # spill heuristics cannot repurpose it while computing the RHS.
        orig_reg = emitter.var_regs.get(target_name)
        if orig_reg:
            emitter.pin_reg(orig_reg)
        try:
            rval = emitter.emit_expr(val, out)
        finally:
            if orig_reg:
                emitter.unpin_reg(orig_reg)
    else:
        rval = emitter.emit_expr(val, out)

    if isinstance(target, dict) and target.get("type") == "member_access":
        _emit_assign_member_access(emitter, target, rval, out)
    elif isinstance(target, dict) and target.get("type") == "deref":
        addr_expr = target.get("expr")
        emitter.pin_reg(rval)
        raddr = emitter.emit_expr(addr_expr, out)
        emitter.unpin_reg(rval)
        store_instr = "SB" if _is_char_ptr_expr(emitter, addr_expr) else "SW"
        out.write(f"  {store_instr} {rval}, {raddr}, 0    // store \n")
        emitter.release_expr_reg(raddr)
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

    if rval:
        emitter.release_expr_reg(rval)
    # Reclaim any variables that are now dead after this assignment
    emitter.reclaim_dead_var_regs()


def _emit_if(emitter, stmt: Dict[str, Any], out):
    cond = stmt.get("cond")
    then_stmts = stmt.get("then", []) or []
    else_stmts = stmt.get("else", []) or []
    protected_vars = emitter.get_stmt_read_vars(stmt)
    emitter.enter_control_context(protected_vars)
    lbl_else = emitter.gen_label("ELSE")
    lbl_end = emitter.gen_label("IF_END")
    try:
        if isinstance(cond, dict) and cond.get("type") == "var":
            vname = cond.get("name")
            if emitter.var_types.get(vname) == "char_ptr":
                cond = {"type": "deref", "expr": cond}
        rcond = emitter.emit_expr(cond, out)
        rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
        out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_else}\n")
        if rcond:
            emitter.release_expr_reg(rcond)
        emitter.enter_var_scope()
        for s in then_stmts:
            emitter.emit_statement(s, out)
        emitter.exit_var_scope()
        out.write(f"  JMP {lbl_end}\n")
        out.write(f"{lbl_else}:\n")
        emitter.enter_var_scope()
        for s in else_stmts:
            emitter.emit_statement(s, out)
        emitter.exit_var_scope()
        out.write(f"{lbl_end}:\n")
    finally:
        emitter.exit_control_context(protected_vars)


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
    protected_vars = emitter.get_stmt_read_vars(stmt)
    emitter.enter_control_context(protected_vars)
    lbl_start = emitter.gen_label("WHILE")
    lbl_end = emitter.gen_label("WHILE_END")
    try:
        out.write(f"{lbl_start}:\n")
        if isinstance(cond, dict) and cond.get("type") == "var":
            vname = cond.get("name")
            if emitter.var_types.get(vname) == "char_ptr":
                cond = {"type": "deref", "expr": cond}
        rcond = emitter.emit_expr(cond, out)
        rcond_reg = rcond if rcond else abi.SPECIAL_REGS["zero"]
        out.write(f"  BEQ {rcond_reg}, {abi.SPECIAL_REGS['zero']}, {lbl_end}\n")
        if rcond:
            emitter.release_expr_reg(rcond)
        emitter.enter_var_scope()
        for s in body:
            emitter.emit_statement(s, out)
        emitter.exit_var_scope()
        out.write(f"  JMP {lbl_start}\n")
        out.write(f"{lbl_end}:\n")
    finally:
        emitter.exit_control_context(protected_vars)


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
