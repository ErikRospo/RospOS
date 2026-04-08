import abi


def _borrow_scratch_reg(emitter, out, avoid=None):
    """
    Borrow a temporary register for short intrinsic code sequences.

    Prefer a currently-free temp register. If none are free, spill one live temp
    with PUSH/POP so we never alias multiple temporaries to the same fallback
    register under pressure.

    Returns:
        (reg_name, spilled_live_reg)
    """
    avoid_set = set(avoid or [])

    for reg in list(emitter.reg_free):
        if reg in avoid_set:
            continue
        emitter.reg_free.remove(reg)
        return reg, False

    for reg in abi.TEMP_REGS:
        if reg in avoid_set:
            continue
        out.write(f"  PUSH {reg}    // spill live temp for intrinsic scratch\n")
        return reg, True

    # Should not be reachable with current ABI, but keep a safe fallback.
    print(
        "Warning: no temp registers available to borrow for intrinsic; using r13 as fallback"
    )
    return "r13", False


def _release_scratch_reg(emitter, out, reg: str, spilled: bool):
    if spilled:
        out.write(f"  POP {reg}    // restore spilled temp\n")
    else:
        emitter.free_reg(reg)


def intrinsic_break(emitter, args, out, return_reg=None):
    out.write("  BREAK    // intrinsic __break\n")


def intrinsic_lb(emitter, args, out, return_reg=None):
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
        vname = a.get("name")
        raddr = emitter.var_regs.get(vname)
        if not raddr:
            if vname in getattr(emitter, "_var_spill_labels", {}):
                raddr = emitter._restore_spilled_var_reg(vname, out)
            if not raddr:
                raddr = emitter._ensure_var_reg(vname, out)
    else:
        raddr = emitter.emit_expr(a, out)

    assert raddr is not None, "Failed to prepare address for __lb"
    target = return_reg if return_reg else abi.RETURN_REG
    out.write(f"  LB {target}, {raddr}, 0    // intrinsic __lb -> return\n")
    emitter.release_expr_reg(raddr)


def intrinsic_sb(emitter, args, out, return_reg=None):
    if len(args) < 2:
        out.write("  // __sb missing args\n")
        return

    a_addr = args[0]
    a_val = args[1]

    borrowed_addr = None
    borrowed_val = None
    release_addr_expr = False
    release_val_expr = False

    if a_addr.get("type") == "const":
        raddr, spilled = _borrow_scratch_reg(emitter, out)
        borrowed_addr = (raddr, spilled)
        out.write(
            f"  LLI {raddr}, {int(a_addr.get('value'))}    // addr const for __sb\n"
        )
    elif a_addr.get("type") == "var":
        vname = a_addr.get("name")
        raddr = emitter.var_regs.get(vname)
        if not raddr:
            if vname in getattr(emitter, "_var_spill_labels", {}):
                raddr = emitter._restore_spilled_var_reg(vname, out)
            if not raddr:
                raddr = emitter._ensure_var_reg(vname, out)
    else:
        raddr = emitter.emit_expr(a_addr, out)
        release_addr_expr = True

    emitter.pin_reg(raddr)

    if a_val.get("type") == "const":
        r_avoid = [raddr] if raddr else []
        rval, spilled = _borrow_scratch_reg(emitter, out, avoid=r_avoid)
        borrowed_val = (rval, spilled)
        out.write(f"  LLI {rval}, {int(a_val.get('value'))}    // val const for __sb\n")
    elif a_val.get("type") == "var":
        vname = a_val.get("name")
        if emitter.var_types.get(vname) == "char_ptr":
            rptr = emitter.var_regs.get(vname)
            if not rptr:
                if vname in getattr(emitter, "_var_spill_labels", {}):
                    rptr = emitter._restore_spilled_var_reg(vname, out)
                if not rptr:
                    rptr = emitter._ensure_var_reg(vname, out)
            r_avoid = [raddr] if raddr else []
            rval, spilled = _borrow_scratch_reg(emitter, out, avoid=r_avoid)
            borrowed_val = (rval, spilled)
            out.write(f"  LB {rval}, {rptr}, 0    // load *{vname} for __sb\n")
        else:
            rval = emitter.var_regs.get(vname)
            if not rval:
                if vname in getattr(emitter, "_var_spill_labels", {}):
                    rval = emitter._restore_spilled_var_reg(vname, out)
                if not rval:
                    rval = emitter._ensure_var_reg(vname, out)
    else:
        rval = emitter.emit_expr(a_val, out)
        release_val_expr = True

    emitter.unpin_reg(raddr)

    out.write(f"  SB {rval}, {raddr}, 0    // intrinsic __sb\n")

    if release_val_expr:
        emitter.release_expr_reg(rval)
    if borrowed_val is not None:
        _release_scratch_reg(emitter, out, borrowed_val[0], borrowed_val[1])

    if release_addr_expr:
        emitter.release_expr_reg(raddr)
    if borrowed_addr is not None:
        _release_scratch_reg(emitter, out, borrowed_addr[0], borrowed_addr[1])
