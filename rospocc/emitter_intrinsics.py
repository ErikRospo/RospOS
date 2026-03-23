import abi


def intrinsic_lb(emitter, args, out):
    a = args[0] if args else None
    raddr = None
    if a is None:
        out.write("  // __lb missing arg\n")
        return

    if a.get("type") == "array":
        size = int(a.get("size", 0))
        name = a.get("name", f"arr{emitter.label_counter}")
        lbl = emitter.gen_label(f"{name}_buf")
        emitter.global_spaces.append({"name": lbl, "size": size})
        r = emitter.alloc_reg()
        emitter.var_regs[name] = r
        emitter.var_types[name] = "char_ptr"
        out.write(f"  LLI {r}, {lbl}    // init {name} (buffer addr)\n")
        raddr = r
    elif a.get("type") == "const":
        val = int(a.get("value"))
        name = a.get("name", f"const{emitter.label_counter}")
        r = emitter.alloc_reg()
        emitter.var_regs[name] = r
        emitter.var_types[name] = "int"
        out.write(f"  LLI {r}, {val}    // init {name}\n")
        raddr = r
    elif a.get("type") == "var":
        raddr = emitter.var_regs.get(a.get("name"))
        if not raddr:
            raddr = emitter._ensure_var_reg(a.get("name"), out)
    else:
        raddr = emitter.emit_expr(a, out)

    assert raddr is not None, "Failed to prepare address for __lb"
    out.write(f"  LB {abi.RETURN_REG}, {raddr}, 0    // intrinsic __lb -> return\n")
    if raddr in abi.TEMP_REGS:
        emitter.free_reg(raddr)


def intrinsic_sb(emitter, args, out):
    if len(args) < 2:
        out.write("  // __sb missing args\n")
        return

    a_addr = args[0]
    a_val = args[1]

    if a_addr.get("type") == "const":
        raddr = emitter.alloc_reg()
        out.write(
            f"  LLI {raddr}, {int(a_addr.get('value'))}    // addr const for __sb\n"
        )
    elif a_addr.get("type") == "var":
        raddr = emitter.var_regs.get(a_addr.get("name"))
        if not raddr:
            raddr = emitter._ensure_var_reg(a_addr.get("name"), out)
    else:
        raddr = emitter.emit_expr(a_addr, out)

    if a_val.get("type") == "const":
        rval = emitter.alloc_reg()
        out.write(
            f"  LLI {rval}, {int(a_val.get('value'))}    // val const for __sb\n"
        )
    elif a_val.get("type") == "var":
        vname = a_val.get("name")
        if emitter.var_types.get(vname) == "char_ptr":
            rptr = emitter.var_regs.get(vname)
            if not rptr:
                rptr = emitter._ensure_var_reg(vname, out)
            rval = emitter.alloc_reg()
            out.write(f"  LB {rval}, {rptr}, 0    // load *{vname} for __sb\n")
        else:
            rval = emitter.var_regs.get(vname)
            if not rval:
                rval = emitter._ensure_var_reg(vname, out)
    else:
        rval = emitter.emit_expr(a_val, out)

    out.write(f"  SB {rval}, {raddr}, 0    // intrinsic __sb\n")
    if raddr in abi.TEMP_REGS:
        emitter.free_reg(raddr)
    if rval in abi.TEMP_REGS:
        emitter.free_reg(rval)
