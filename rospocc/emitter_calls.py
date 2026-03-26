from typing import Dict, Optional

import abi


def emit_call(emitter, call_expr: Dict, return_reg: Optional[str], out):
    name = call_expr.get("name")
    args = call_expr.get("args", [])

    if isinstance(name, str) and name.startswith("__"):
        handler = emitter.intrinsics.get(name)
        if handler:
            handler(args, out, return_reg=return_reg)
            return
        print(f"Warning: no handler for intrinsic {name!r}")

    out.write(f"  // emit call to {name} with args {args}\n")
    return_type = emitter.func_return_types.get(name)
    is_void = return_type == "void"

    live_regs = [r for r in abi.TEMP_REGS if r not in emitter.reg_free]
    if live_regs:
        for r in live_regs:
            out.write(f"  PUSH {r}    // save caller temp\n")

    if return_reg == abi.RETURN_REG or is_void:
        return_reg = None

    if return_reg is None:
        out.write(
            "  PUSH r1    // If we don't care about the return value, we still need to ensure r1 doesn't get clobbered\n"
        )

    for i, a in enumerate(args[: len(abi.ARG_REGS)]):
        dest = abi.ARG_REGS[i]
        if a.get("type") == "const":
            emitter._load_imm(dest, int(a.get("value")), out)
        elif a.get("type") == "string_addr":
            emitter._load_imm(dest, a.get("label"), out)
        elif a.get("type") == "var":
            var_name = a.get("name")
            r = emitter.var_regs.get(var_name)
            if r:
                out.write(f"  ADDI {dest}, {r}, 0    // move arg {i}\n")
                emitter.consume_var_read(var_name)
            else:
                emitter._load_imm(dest, 0, out)
        elif a.get("type") == "deref":
            r = emitter.emit_expr(a, out)
            if r:
                out.write(f"  ADDI {dest}, {r}, 0    // move arg {i} from deref\n")
                emitter.release_expr_reg(r)
            else:
                emitter._load_imm(dest, 0, out)
        else:
            r = emitter.emit_expr(a, out)
            if r:
                out.write(f"  ADDI {dest}, {r}, 0    // move arg {i} from expr\n")
                emitter.release_expr_reg(r)
            else:
                out.write(f"  // unsupported arg type {a!r}\n")

    out.write(f"  CALL {call_expr.get('name')}\n")
    out.write(f"  // call return value in {abi.RETURN_REG}\n")

    if return_reg is None:
        out.write("  POP r1  \n")

    if live_regs:
        for r in reversed(live_regs):
            out.write(f"  POP {r}    // restore caller temp\n")

    if return_reg and return_reg != abi.RETURN_REG and not is_void:
        out.write(f"  ADDI {return_reg}, {abi.RETURN_REG}, 0    // move return value\n")
