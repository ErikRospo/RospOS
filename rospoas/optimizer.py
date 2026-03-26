from ir import ImmLabel, ImmValue, Instruction, LabelDecl


def optimize(ast):
    opts = [_push_pop_optimization, _remove_unneeded_jumps, _nop_removal, _remove_unused_labels, _thread_jump_chains, _remove_unreachable_after_jmp]
    logs = []
    for opt in opts:
        ast = opt(ast, logs)
    return ast, logs

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
        if isinstance(instr, Instruction) and instr.type and instr.name == "jmp":
            imm = instr.imm
            target = imm.name if isinstance(imm, ImmLabel) else None

            if target is not None:
                j = i + 1
                while j < len(ast) and isinstance(ast[j], LabelDecl):
                    if ast[j].name == target:
                        logs.append(
                            f"Removed unneeded jmp pseudo before label '{target}' at index {i}"
                        )
                        i += 1
                        break
                    j += 1
                else:
                    optimized_ast.append(instr)
                    i += 1
                    continue

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
def _nop_removal(ast, logs):
    # E.g. ADDI r5, r5, 0
    optimized_ast = []
    for instr in ast:
        if (
            isinstance(instr, Instruction)
            and instr.name in {"addi", "ori", "subi"}
            and instr.type == "i"
        ):
            rd = instr.rd
            rs = instr.rs1
            imm = instr.imm
            if rd == rs and _reg_from_imm(imm) == 0:
                logs.append(
                    f"Removed effective NOP instruction '{instr}' at index {len(optimized_ast)}"
                )
                continue
        optimized_ast.append(instr)
    return optimized_ast
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
def _is_jmp_to_label(instr):
    return (
        isinstance(instr, Instruction)
        and instr.name == "jmp"
        and isinstance(getattr(instr, "imm", None), ImmLabel)
    )
def _next_non_label_index(ast, idx):
    while idx < len(ast) and isinstance(ast[idx], LabelDecl):
        idx += 1
    return idx
def _thread_jump_chains(ast, logs):
    # If jmp A and A immediately jumps to B, rewrite to jmp B
    label_to_index = {}
    for idx, node in enumerate(ast):
        if isinstance(node, LabelDecl):
            label_to_index[node.name] = idx

    optimized_ast = []
    for idx, instr in enumerate(ast):
        if not _is_jmp_to_label(instr):
            optimized_ast.append(instr)
            continue

        original = instr.imm.name
        target = original
        visited = set()

        while target in label_to_index and target not in visited:
            visited.add(target)
            k = _next_non_label_index(ast, label_to_index[target] + 1)
            if k < len(ast) and _is_jmp_to_label(ast[k]):
                target = ast[k].imm.name
            else:
                break

        if target != original:
            logs.append(f"Threaded jump at index {idx}: '{original}' -> '{target}'")
            optimized_ast.append(
                instr.copy_with(imm=ImmLabel(target), is_optimized=True)
            )
        else:
            optimized_ast.append(instr)

    return optimized_ast
def _remove_unreachable_after_jmp(ast, logs):
    # Remove straight-line code after an unconditional jmp until next label
    optimized_ast = []
    i = 0
    while i < len(ast):
        node = ast[i]
        optimized_ast.append(node)
        i += 1

        if _is_jmp_to_label(node):
            while i < len(ast) and not isinstance(ast[i], LabelDecl):
                logs.append(
                    f"Removed unreachable instruction '{ast[i]}' after jmp at index {i-1}"
                )
                i += 1

    return optimized_ast
def _find_used_labels(ast):
    used_labels = set()
    for instr in ast:
        if isinstance(instr, Instruction) and hasattr(instr, "imm"):
            imm = instr.imm
            if isinstance(imm, ImmLabel):
                used_labels.add(imm.name)
    return used_labels
def _find_defined_labels(ast):
    defined_labels = set()
    for instr in ast:
        if isinstance(instr, LabelDecl):
            defined_labels.add(instr.name)
    return defined_labels
def _remove_unused_labels(ast, logs):
    used_labels = _find_used_labels(ast)
    defined_labels = _find_defined_labels(ast)
    unused_labels = defined_labels - used_labels

    optimized_ast = []
    for instr in ast:
        if isinstance(instr, LabelDecl) and instr.name in unused_labels:
            logs.append(f"Removed unused label '{instr.name}' at index {len(optimized_ast)}")
            continue
        optimized_ast.append(instr)

    return optimized_ast