from pathlib import Path

from ir import ImmLabel, ImmValue, Instruction, LabelDecl


def optimize(ast, outloc: Path):
    # Placeholder for optimization logic. For now, just return the AST as-is.
    # In a real implementation, this function would perform various optimizations
    # on the IR, such as constant folding, dead code elimination, peephole optimizations, etc.
    with open(outloc / "debug_before_opt.txt", "w") as f:
        for instr in ast:
            f.write(str(instr) + "\n")
    opts = [_push_pop_optimization, _remove_unneeded_jumps]
    logs = []
    for opt in opts:
        ast = opt(ast, logs)

    with open(outloc / "debug_after_opt.txt", "w") as f:
        for instr in ast:
            f.write(str(instr) + "\n")

    with open(outloc / "debug_opt_log.txt", "w") as f:
        if logs:
            for line in logs:
                f.write(line + "\n")
        else:
            f.write("No optimization transforms applied.\n")
    return ast


def _mark_optimized(node):
    if isinstance(node, Instruction):
        return node.copy_with(is_optimized=True)
    return node


def _remove_unneeded_jumps(ast, logs):
    # Remove jumps that are immediately followed by their target label
    optimized_ast = []
    i = 0
    while i < len(ast):
        instr = ast[i]
        if isinstance(instr, Instruction) and instr.type == "p" and instr.name == "jmp":
            if i + 1 < len(ast) and isinstance(ast[i + 1], LabelDecl):
                imm = instr.imm
                target = imm.name if isinstance(imm, ImmLabel) else None
                if target is not None and ast[i + 1].name == target:
                    logs.append(
                        f"Removed unneeded jmp pseudo before label '{target}' at index {i}"
                    )
                    i += 1
                    continue
        optimized_ast.append(instr)
        i += 1
    return optimized_ast


def _reg_from_imm(imm):
    if isinstance(imm, ImmValue):
        return int(imm.value)
    try:
        return int(imm)
    except Exception:
        return None


def _push_pop_optimization(ast, logs):
    # find sequences of push and pop instructions that cancel each other out and eliminate them
    # e.g.
    # PUSH r1
    # PUSH r2
    # PUSH r3
    # POP r3
    # POP r2
    # POP r1
    # While this technically does write r1, r2, r3 to the stack (and therefore, this does change the program's behavior), you shouldn't really try reading from the stack directly anyways, and even if you do, this *shouldn't* cause any issues.

    # This is commonly generated from two successive calls, where the first call pushes arguments onto the stack, then calls a function which pops those arguments, and then the second call pushes new arguments onto the stack. In this case, we can safely eliminate the middle pushes and pops, as they shouldn't have any effect on the program's behavior. This is a common pattern that we can optimize away.
    optimized_ast = []
    i = 0
    while i < len(ast):
        instr = ast[i]

        # Check if current instruction is a pop
        if isinstance(instr, Instruction) and instr.name == "pop" and instr.type == "p":
            pop_sequence = [instr]
            j = i + 1

            # Collect consecutive pops
            while (
                j < len(ast)
                and isinstance(ast[j], Instruction)
                and ast[j].name == "pop"
                and ast[j].type == "p"
            ):
                pop_sequence.append(ast[j])
                j += 1

            # Check if followed by push sequence
            push_sequence = []
            while (
                j < len(ast)
                and isinstance(ast[j], Instruction)
                and ast[j].name == "push"
                and ast[j].type == "p"
            ):
                push_sequence.append(ast[j])
                j += 1

            # If we have both pops and pushes, try to match them
            if pop_sequence and push_sequence:
                # Create lists of immediate values
                pop_values = [_reg_from_imm(p.imm) for p in pop_sequence]
                push_values = [_reg_from_imm(p.imm) for p in push_sequence]

                # Check if push values are reverse of pop values (stack property)
                if push_values == list(reversed(pop_values)):
                    # Perfect match - eliminate both sequences
                    logs.append(
                        f"Removed POP/PUSH cancellation block at indices {i}-{j-1} (len={len(pop_sequence) + len(push_sequence)})"
                    )
                    if j < len(ast):
                        optimized_ast.append(_mark_optimized(ast[j]))
                        i = j + 1
                        continue
                    i = j
                    continue

            # No match, keep the pop instruction
            optimized_ast.append(instr)
            i += 1
        else:
            # Not a pop, keep instruction as-is
            optimized_ast.append(instr)
            i += 1

    return optimized_ast
