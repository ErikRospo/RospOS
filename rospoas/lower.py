"""Lowering stage: expand pseudo-instructions and lifted constants
into concrete `Instruction` sequences using the typed IR.

This module is intentionally conservative: it does not perform layout
or relocations, it only expands pseudos and normalizes immediates
into `ImmValue`/`ImmLabel`/`ImmLabelPart`/`ImmLifted` forms already
defined in `rospoas.ir`.
"""

from typing import List

from errors import TransformError, fmt_node
from ir import (Directive, ImmLabel, ImmLabelPart, ImmLifted, ImmValue,
                Instruction, LabelDecl)
from maps import i_to_r_map, register_map

TEMP_REG = register_map["r13"]
SP_REG = register_map["sp"]


def _emit_immediate_loading_for_value(
    value: int, rd: int, src: dict = None
) -> List[Instruction]:
    instrs: List[Instruction] = []
    high = (value >> 16) & 0xFFFF
    low = value & 0xFFFF
    if high != 0:
        instrs.append(
            Instruction(
                type="i", name="addi", rd=rd, rs1=0, imm=ImmValue(high), src=src
            )
        )
        instrs.append(
            Instruction(type="i", name="shli", rd=rd, rs1=rd, imm=ImmValue(16), src=src)
        )
        if low != 0:
            instrs.append(
                Instruction(
                    type="i", name="ori", rd=rd, rs1=rd, imm=ImmValue(low), src=src
                )
            )
    else:
        instrs.append(
            Instruction(type="i", name="addi", rd=rd, rs1=0, imm=ImmValue(low), src=src)
        )
    return instrs


def _emit_immediate_loading_for_label(
    label_name: str, rd: int, src: dict = None
) -> List[Instruction]:
    return [
        Instruction(
            type="i",
            name="addi",
            rd=rd,
            rs1=0,
            imm=ImmLabelPart(label=label_name, part="high"),
            src=src,
        ),
        Instruction(type="i", name="shli", rd=rd, rs1=rd, imm=ImmValue(16), src=src),
        Instruction(
            type="i",
            name="ori",
            rd=rd,
            rs1=rd,
            imm=ImmLabelPart(label=label_name, part="low"),
            src=src,
        ),
    ]


def _emit_stack_push(reg: int, src: dict = None) -> List[Instruction]:
    return [
        Instruction(
            type="i", name="addi", rd=SP_REG, rs1=SP_REG, imm=ImmValue(-4), src=src
        ),
        Instruction(type="l", name="sw", rd=reg, rs1=SP_REG, imm=ImmValue(0), src=src),
    ]


def _emit_stack_pop(reg: int, src: dict = None) -> List[Instruction]:
    return [
        Instruction(type="l", name="lw", rd=reg, rs1=SP_REG, imm=ImmValue(0), src=src),
        Instruction(
            type="i", name="addi", rd=SP_REG, rs1=SP_REG, imm=ImmValue(4), src=src
        ),
    ]


def lower_ir(ir_list: List) -> List:
    """Return a new IR list with pseudos expanded.

    Input list may contain `Instruction`, `LabelDecl`, and `Directive`.
    """
    out: List = []
    for node in ir_list:
        # keep labels and directives as-is
        if isinstance(node, LabelDecl) or isinstance(node, Directive):
            out.append(node)
            continue

        if not isinstance(node, Instruction):
            out.append(node)
            continue

        # Handle pseudo-instructions (type 'p')
        if node.type == "p":
            name = node.name
            if name == "push":
                # node.imm contains register number
                out.extend(_emit_stack_push(node.imm, src=node.src))
                continue
            if name == "pop":
                out.extend(_emit_stack_pop(node.imm, src=node.src))
                continue
            if name == "lli":
                rd = node.rd
                imm = node.imm
                if isinstance(imm, ImmLifted):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), rd, src=node.src
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(imm.name, rd, src=node.src)
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), rd, src=node.src
                        )
                    )
                else:
                    # unknown immediate form; keep as-is
                    out.append(node)
                continue
            if name == "jmp":
                rd = node.rd if node.rd is not None else 0
                imm = node.imm
                if isinstance(imm, ImmLifted):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=node.src
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(
                            imm.name, TEMP_REG, src=node.src
                        )
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=node.src
                        )
                    )
                else:
                    raise TransformError(
                        f"Unhandled immediate in jmp pseudo: {fmt_node(imm)}; node={fmt_node(node)}"
                    )
                out.append(
                    Instruction(
                        type="j",
                        name="jalr",
                        rd=rd,
                        rs1=TEMP_REG,
                        imm=ImmValue(0),
                        src=node.src,
                    )
                )
                continue

            # SUBI, MULI, DIVI, REMI pseudo-instructions: lower to R-type with immediate loaded in TEMP_REG
            if name in ("subi", "muli", "divi", "remi"):
                rd = node.rd
                rs1 = node.rs1
                imm = node.imm
                # Determine the R-type instruction name
                r_map = {"subi": "sub", "muli": "mul", "divi": "div", "remi": "rem"}
                rname = r_map[name]
                # Load immediate into TEMP_REG
                if isinstance(imm, ImmLifted):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=node.src
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(
                            imm.name, TEMP_REG, src=node.src
                        )
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=node.src
                        )
                    )
                else:
                    # unknown immediate form; keep as-is
                    out.append(node)
                    continue
                # Emit the R-type instruction
                out.append(
                    Instruction(
                        type="r",
                        name=rname,
                        rd=rd,
                        rs1=rs1,
                        rs2=TEMP_REG,
                        src=node.src,
                    )
                )
                continue

        # For normal instructions, handle lifted `li` immediates.
        if node.type in ["i", "l"] and isinstance(node.imm, ImmLifted):
            li = node.imm
            const_val = li.value
            # Use TEMP_REG to hold the constant.
            out.extend(_emit_stack_push(TEMP_REG, src=node.src))
            out.extend(
                _emit_immediate_loading_for_value(
                    int(const_val), TEMP_REG, src=node.src
                )
            )

            if node.type == "i":
                # Convert I-type to R-type using i_to_r_map
                rname = i_to_r_map.get(node.name)
                if rname is None:
                    raise TransformError(
                        f"Cannot convert I-op {node.name} to R-op for lifted constant handling; node={fmt_node(node)}"
                    )
                out.append(
                    Instruction(
                        type="r",
                        name=rname,
                        rd=node.rd,
                        rs1=node.rs1,
                        rs2=TEMP_REG,
                        src=node.src,
                    )
                )
            elif node.type == "l":
                # For load with large constant offset: compute address in TEMP_REG,
                # then LW from 0(TEMP_REG)
                if node.rs1 == 0:
                    out.append(
                        Instruction(
                            type="l",
                            name="lw",
                            rd=node.rd,
                            rs1=TEMP_REG,
                            imm=ImmValue(0),
                            src=node.src,
                        )
                    )
                else:
                    out.append(
                        Instruction(
                            type="r",
                            name="add",
                            rd=TEMP_REG,
                            rs1=TEMP_REG,
                            rs2=node.rs1,
                            src=node.src,
                        )
                    )
                    out.append(
                        Instruction(
                            type="l",
                            name="lw",
                            rd=node.rd,
                            rs1=TEMP_REG,
                            imm=ImmValue(0),
                            src=node.src,
                        )
                    )

            out.extend(_emit_stack_pop(TEMP_REG))
            continue

        # Otherwise, keep instruction unchanged
        out.append(node)

    return out
