from typing import Optional


def load_imm(out, reg: str, value):
    out.write(f"  LLI {reg}, {value}    // load immediate {value}\n")


def alloc_var_reg(
    emitter,
    name: str,
    out,
    init_value=None,
    typ: str = "int",
    is_label: bool = False,
    comment: Optional[str] = None,
):
    r = emitter.alloc_reg(track_as_temp=False)
    emitter.var_regs[name] = r
    emitter.var_types[name] = typ
    # Track allocation for debug info
    var_kind = "label" if is_label else "local"
    if hasattr(out, "get_current_output_line"):
        output_line = out.get_current_output_line()
        emitter.register_allocator.set_output_line(output_line)
        emitter.register_allocator.allocate(
            register=r,
            variable_name=name,
            variable_type=typ,
            var_kind=var_kind,
            origin=emitter.current_context_origin,
        )
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


def ensure_var_reg(emitter, name: str, out) -> str:
    r = emitter.var_regs.get(name)
    if r:
        return r
    r = emitter.alloc_reg(track_as_temp=False)
    emitter.var_regs[name] = r
    out.write(f"  LLI {r}, 0    // implicit init {name}\n")
    return r
