from typing import Dict, Optional

import abi


def _materialize_call_arg(emitter, arg, out):
    """Materialize a call argument to a register.

    Returns:
        (reg_name, should_release)
    """
    if arg.get("type") == "const":
        reg = emitter.alloc_reg()
        emitter._load_imm(reg, int(arg.get("value")), out)
        return reg, True

    if arg.get("type") == "string_addr":
        reg = emitter.alloc_reg()
        emitter._load_imm(reg, arg.get("label"), out)
        return reg, True

    if arg.get("type") == "var":
        var_name = arg.get("name")
        reg = emitter.var_regs.get(var_name)
        if reg:
            emitter.consume_var_read(var_name)
            return reg, False
        if var_name in getattr(emitter, "_var_spill_labels", {}):
            reg = emitter._restore_spilled_var_reg(var_name, out)
            if reg:
                emitter.consume_var_read(var_name)
                return reg, False
        reg = emitter.alloc_reg()
        emitter._load_imm(reg, 0, out)
        return reg, True

    reg = emitter.emit_expr(arg, out)
    if reg:
        return reg, True

    reg = emitter.alloc_reg()
    emitter._load_imm(reg, 0, out)
    return reg, True


def emit_call(emitter, call_expr: Dict, return_reg: Optional[str], out):
    name = call_expr.get("name")
    args = call_expr.get("args", [])

    if isinstance(name, str) and name.startswith("__"):
        handler = emitter.intrinsics.get(name)
        if handler:
            handler(args, out, return_reg=return_reg)
            return
        print(f"Warning: no handler for intrinsic {name!r}")

    # Check if this is an inline function call
    if isinstance(name, str) and name in emitter.inline_functions:
        out.write(f"  // inline call to {name} with args {args}\n")
        _emit_inline_call(emitter, name, args, return_reg, out)
        return

    out.write(f"  // emit call to {name} with args {args}\n")
    return_type = emitter.func_return_types.get(name)
    is_void = return_type == "void"

    live_regs = [r for r in abi.TEMP_REGS if r not in emitter.reg_free]
    if live_regs:
        for r in live_regs:
            out.write(f"  PUSH {r}    // save caller temp\n")

    if is_void:
        return_reg = None

    if return_reg is None:
        out.write(
            "  PUSH r1    // If we don't care about the return value, we still need to ensure r1 doesn't get clobbered\n"
        )

    reg_arg_count = len(abi.ARG_REGS)
    reg_args = args[:reg_arg_count]
    stack_args = args[reg_arg_count:]

    # Pass overflow args on stack right-to-left, so arg5 is at the lowest callee offset.
    stack_arg_count = 0
    for a in reversed(stack_args):
        reg, should_release = _materialize_call_arg(emitter, a, out)
        out.write(f"  PUSH {reg}    // pass overflow arg on stack\n")
        stack_arg_count += 1
        if should_release:
            emitter.release_expr_reg(reg)

    # Stage register-passed args first to avoid clobbering when a later arg
    # lives in an ABI arg register overwritten by an earlier arg assignment.
    for i, a in enumerate(reg_args):
        reg, should_release = _materialize_call_arg(emitter, a, out)
        out.write(f"  PUSH {reg}    // stage reg arg {i}\n")
        if should_release:
            emitter.release_expr_reg(reg)

    for i in range(len(reg_args) - 1, -1, -1):
        dest = abi.ARG_REGS[i]
        out.write(f"  POP {dest}    // load reg arg {i}\n")

    out.write(f"  CALL {call_expr.get('name')}\n")
    out.write(f"  // call return value in {abi.RETURN_REG}\n")

    if stack_arg_count:
        out.write(
            f"  ADDI {abi.SP_REG}, {abi.SP_REG}, {stack_arg_count * 4}    // discard overflow arg slots\n"
        )

    if return_reg is None:
        out.write("  POP r1  \n")

    if live_regs:
        for r in reversed(live_regs):
            out.write(f"  POP {r}    // restore caller temp\n")

    if return_reg and return_reg != abi.RETURN_REG and not is_void:
        out.write(f"  ADDI {return_reg}, {abi.RETURN_REG}, 0    // move return value\n")


def _emit_inline_call(emitter, func_name: str, args, return_reg: Optional[str], out):
    """Inline a function call by emitting the function body with inlined arguments."""
    inline_fn = emitter.inline_functions.get(func_name)
    if not inline_fn:
        out.write(f"  // ERROR: inline function '{func_name}' not found\n")
        return

    # Save the current variable state
    saved_var_regs = dict(emitter.var_regs)
    saved_var_types = dict(emitter.var_types)
    saved_stmt_live_after = dict(getattr(emitter, "_stmt_live_after", {}))
    saved_statement_stack = list(getattr(emitter, "_statement_stack", []))
    saved_control_flow_depth = getattr(emitter, "_control_flow_depth", 0)
    saved_protected_var_depth = dict(getattr(emitter, "_protected_var_depth", {}))

    # Create a scope for inline variables
    emitter.enter_var_scope()
    emitter.prepare_function_liveness(inline_fn)
    try:
        # Map parameters to their argument values
        params = inline_fn.get("params", []) or []
        param_types = inline_fn.get("param_types", {}) or {}

        out.write(f"  // begin inline expansion of {func_name}\n")

        # Handle parameter argument mapping
        for i, param_name in enumerate(params):
            if i < len(args):
                arg = args[i]
                arg_type = arg.get("type")

                # Allocate a register for this parameter
                if arg_type == "const":
                    param_reg = emitter.alloc_reg()
                    emitter._load_imm(param_reg, int(arg.get("value")), out)
                    emitter.var_regs[param_name] = param_reg
                elif arg_type == "string_addr":
                    param_reg = emitter.alloc_reg()
                    emitter._load_imm(param_reg, arg.get("label"), out)
                    emitter.var_regs[param_name] = param_reg
                elif arg_type == "var":
                    var_name = arg.get("name")
                    if var_name in emitter.var_regs:
                        # Reuse the existing register for this variable
                        emitter.var_regs[param_name] = emitter.var_regs[var_name]
                    elif var_name in getattr(emitter, "_var_spill_labels", {}):
                        restored_reg = emitter._restore_spilled_var_reg(var_name, out)
                        if restored_reg:
                            emitter.var_regs[param_name] = restored_reg
                        else:
                            param_reg = emitter.alloc_reg()
                            emitter._load_imm(param_reg, 0, out)
                            emitter.var_regs[param_name] = param_reg
                    else:
                        param_reg = emitter.alloc_reg()
                        emitter._load_imm(param_reg, 0, out)
                        emitter.var_regs[param_name] = param_reg
                else:
                    # For complex expressions, evaluate and load into register
                    param_reg = emitter.emit_expr(arg, out)
                    if not param_reg:
                        param_reg = emitter.alloc_reg()
                        emitter._load_imm(param_reg, 0, out)
                    emitter.var_regs[param_name] = param_reg

                # Set parameter type hints
                if param_name in param_types:
                    emitter.var_types[param_name] = param_types[param_name]
                else:
                    emitter.var_types[param_name] = "int"

        # Track the return value in a local variable
        return_value_reg = return_reg if return_reg else abi.RETURN_REG
        emitter.had_return = False
        emitter._in_inline_context = True

        # Emit the function body
        for stmt in inline_fn.get("body", []):
            emitter.emit_statement(stmt, out)

        # Restore return state
        if not emitter.had_return and not (inline_fn.get("return_type") == "void"):
            # No explicit return, ensure return register has a value
            if return_value_reg != abi.RETURN_REG:
                out.write(
                    f"  ADDI {return_value_reg}, {abi.RETURN_REG}, 0    // implicit return\n"
                )
        elif return_value_reg != abi.RETURN_REG and emitter.had_return:
            # Move return value to target register if needed
            out.write(
                f"  ADDI {return_value_reg}, {abi.RETURN_REG}, 0    // move inline return value\n"
            )

        emitter.had_return = True  # Sure, outer context, we definitely had a return.
        out.write(f"  // end inline expansion of {func_name}\n")
    finally:
        # Exit scope and restore variable/state analysis context.
        emitter.exit_var_scope()
        emitter.var_regs = saved_var_regs
        emitter.var_types = saved_var_types
        emitter._stmt_live_after = saved_stmt_live_after
        emitter._statement_stack = saved_statement_stack
        emitter._control_flow_depth = saved_control_flow_depth
        emitter._protected_var_depth = saved_protected_var_depth
        emitter._in_inline_context = False
