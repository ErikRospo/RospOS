from maps import i_to_r_map, register_map

TEMP_REG = register_map["r13"]  # Temporary register for constant loading
SP_REG = register_map["sp"]


def _emit_immediate_loading_for_value(value, rd):
    instrs = []
    high = (value >> 16) & 0xFFFF
    low = value & 0xFFFF
    if high != 0:
        instrs.append({"type": "i", "name": "addi", "rd": rd, "rs1": 0, "imm": high})
        instrs.append({"type": "i", "name": "shli", "rd": rd, "rs1": rd, "imm": 16})
        if low != 0:
            instrs.append({"type": "i", "name": "ori", "rd": rd, "rs1": rd, "imm": low})
    else:
        instrs.append({"type": "i", "name": "addi", "rd": rd, "rs1": 0, "imm": low})
    return instrs


def _emit_immediate_loading_for_label(label_name, rd):
    # Always emit the maximal 3-instruction sequence using label parts.
    return [
        {
            "type": "i",
            "name": "addi",
            "rd": rd,
            "rs1": 0,
            "imm": {"label": label_name, "part": "high"},
        },
        {"type": "i", "name": "shli", "rd": rd, "rs1": rd, "imm": 16},
        {
            "type": "i",
            "name": "ori",
            "rd": rd,
            "rs1": rd,
            "imm": {"label": label_name, "part": "low"},
        },
    ]


def _emit_stack_push(reg):
    # SW reg, -4(sp); ADDI sp, sp, -4
    return [
        {"type": "l", "name": "sw", "rd": reg, "rs1": SP_REG, "imm": -4},
        {"type": "i", "name": "addi", "rd": SP_REG, "rs1": SP_REG, "imm": -4},
    ]


def _emit_stack_pop(reg):
    # ADDI sp, sp, 4; LW reg, 0(sp)
    return [
        {"type": "i", "name": "addi", "rd": SP_REG, "rs1": SP_REG, "imm": 4},
        {"type": "l", "name": "lw", "rd": reg, "rs1": SP_REG, "imm": 0},
    ]


def preprocess_ast(ast, lifted_constants):
    out = []
    for instr in ast:
        # Keep labels and directives as-is
        if instr["type"] == "a" or (instr["type"] == "d"):
            out.append(instr)
            continue

        # Expand pseudo-instructions
        if instr["type"] == "p":
            name = instr["name"]
            if name == "push":
                out.extend(_emit_stack_push(instr["imm"]))
                continue
            if name == "pop":
                out.extend(_emit_stack_pop(instr["imm"]))
                continue
            if name == "lli":
                rd = instr.get("reg")
                imm = instr.get("imm")
                if isinstance(imm, dict):
                    # Lifted constants from transformer are dicts with type=='li' and a 'value'.
                    if imm.get("type") == "li":
                        out.extend(
                            _emit_immediate_loading_for_value(int(imm["value"]), rd)
                        )
                    elif "name" in imm:
                        out.extend(_emit_immediate_loading_for_label(imm["name"], rd))
                    else:
                        raise ValueError(f"Unhandled immediate dict in lli: {imm}")
                else:
                    out.extend(_emit_immediate_loading_for_value(int(imm), rd))
                continue
            if name == "jmp":
                rd = instr.get("rd", 0)
                imm = instr.get("imm")
                # Emit maximal absolute jump sequence using TEMP_REG
                out.extend(_emit_stack_push(TEMP_REG))
                if isinstance(imm, dict):
                    if imm.get("type") == "li":
                        out.extend(
                            _emit_immediate_loading_for_value(
                                int(imm["value"]), TEMP_REG
                            )
                        )
                    elif "name" in imm:
                        out.extend(
                            _emit_immediate_loading_for_label(imm["name"], TEMP_REG)
                        )
                    else:
                        raise ValueError(f"Unhandled immediate dict in jmp: {imm}")
                else:
                    out.extend(_emit_immediate_loading_for_value(int(imm), TEMP_REG))
                # JALR rd, TEMP_REG, 0
                out.append(
                    {"type": "j", "name": "jalr", "rd": rd, "rs1": TEMP_REG, "imm": 0}
                )
                out.extend(_emit_stack_pop(TEMP_REG))
                continue

        # For normal instructions, handle lifted `li` immediates.
        # If an immediate is a lifted constant dict (type=="li"),
        # rewrite the operation to use a temp register that is loaded
        # with the constant, then use the corresponding R-type op (for I-type ops).
        if (
            instr["type"] in ["i", "l"]
            and isinstance(instr.get("imm"), dict)
            and instr["imm"].get("type") == "li"
        ):
            li = instr["imm"]
            const_val = li.get("value")
            # Use TEMP_REG to hold the constant.
            out.extend(_emit_stack_push(TEMP_REG))
            out.extend(_emit_immediate_loading_for_value(int(const_val), TEMP_REG))

            if instr["type"] == "i":
                # Convert I-type to R-type using i_to_r_map
                rname = i_to_r_map.get(instr["name"], None)
                if rname is None:
                    raise AssertionError(
                        f"Cannot convert I-op {instr['name']} to R-op for lifted constant handling"
                    )
                out.append(
                    {
                        "type": "r",
                        "name": rname,
                        "rd": instr["rd"],
                        "rs1": instr["rs1"],
                        "rs2": TEMP_REG,
                    }
                )
            elif instr["type"] == "l":
                # For load with large constant offset: compute address in TEMP_REG,
                # then LW from 0(TEMP_REG)
                if instr["rs1"] == 0:
                    # Absolute load: load address into TEMP_REG then lw rd, 0(TEMP_REG)
                    out.append(
                        {
                            "type": "l",
                            "name": "lw",
                            "rd": instr["rd"],
                            "rs1": TEMP_REG,
                            "imm": 0,
                        }
                    )
                else:
                    # Base + offset: compute TEMP_REG = TEMP_REG + rs1; then lw
                    out.append(
                        {
                            "type": "r",
                            "name": "add",
                            "rd": TEMP_REG,
                            "rs1": TEMP_REG,
                            "rs2": instr["rs1"],
                        }
                    )
                    out.append(
                        {
                            "type": "l",
                            "name": "lw",
                            "rd": instr["rd"],
                            "rs1": TEMP_REG,
                            "imm": 0,
                        }
                    )

            out.extend(_emit_stack_pop(TEMP_REG))
            continue

        # Otherwise, keep instruction unchanged
        out.append(instr)

    return out
