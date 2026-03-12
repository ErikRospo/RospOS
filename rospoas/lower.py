"""Lowering stage: expand pseudo-instructions and lifted constants
into concrete `Instruction` sequences using the typed IR.

This module is intentionally conservative: it does not perform layout
or relocations, it only expands pseudos and normalizes immediates
into `ImmValue`/`ImmLabel`/`ImmLabelPart`/`ImmLifted` forms already
defined in `rospoas.ir`.
"""

from typing import List

from errors import TransformError, fmt_node
from ir import (
    Directive,
    ImmLabel,
    ImmLabelPart,
    ImmLifted,
    ImmValue,
    Instruction,
    LabelDecl,
)
from maps import i_to_r_map, register_map

TEMP_REG = register_map["r13"]
SP_REG = register_map["sp"]


def _clone_src(src):
    if not isinstance(src, dict):
        return src
    out = dict(src)
    chain = out.get("include_chain")
    if isinstance(chain, list):
        out["include_chain"] = list(chain)
    return out


def _node_flags(node, pseudo_expansion=False):
    base_depth = int(getattr(node, "expansion_depth", 0) or 0)
    return {
        "is_pseudo_expanded": bool(
            pseudo_expansion or getattr(node, "is_pseudo_expanded", False)
        ),
        "is_from_rospocc": bool(getattr(node, "is_from_rospocc", False)),
        "is_optimized": bool(getattr(node, "is_optimized", False)),
        "expansion_depth": base_depth + (1 if pseudo_expansion else 0),
    }


def _emit_immediate_loading_for_value(
    value: int, rd: int, src: dict = None, flags=None
) -> List[Instruction]:
    instrs: List[Instruction] = []
    f = flags or {}
    high = (value >> 16) & 0xFFFF
    low = value & 0xFFFF
    if high != 0:
        instrs.append(
            Instruction(
                type="i", name="addi", rd=rd, rs1=0, imm=ImmValue(high), src=src, **f
            )
        )
        instrs.append(
            Instruction(
                type="i", name="shli", rd=rd, rs1=rd, imm=ImmValue(16), src=src, **f
            )
        )
        if low != 0:
            instrs.append(
                Instruction(
                    type="i", name="ori", rd=rd, rs1=rd, imm=ImmValue(low), src=src, **f
                )
            )
    else:
        instrs.append(
            Instruction(
                type="i", name="addi", rd=rd, rs1=0, imm=ImmValue(low), src=src, **f
            )
        )
    return instrs


def _emit_immediate_loading_for_label(
    label_name: str, rd: int, src: dict = None, flags=None
) -> List[Instruction]:
    f = flags or {}
    return [
        Instruction(
            type="i",
            name="addi",
            rd=rd,
            rs1=0,
            imm=ImmLabelPart(label=label_name, part="high"),
            src=src,
            **f,
        ),
        Instruction(
            type="i", name="shli", rd=rd, rs1=rd, imm=ImmValue(16), src=src, **f
        ),
        Instruction(
            type="i",
            name="ori",
            rd=rd,
            rs1=rd,
            imm=ImmLabelPart(label=label_name, part="low"),
            src=src,
            **f,
        ),
    ]


def _emit_stack_push(reg: int, src: dict = None, flags=None) -> List[Instruction]:
    f = flags or {}
    return [
        Instruction(
            type="i", name="addi", rd=SP_REG, rs1=SP_REG, imm=ImmValue(-4), src=src, **f
        ),
        Instruction(
            type="l", name="sw", rd=reg, rs1=SP_REG, imm=ImmValue(0), src=src, **f
        ),
    ]


def _emit_stack_pop(reg: int, src: dict = None, flags=None) -> List[Instruction]:
    f = flags or {}
    return [
        Instruction(
            type="l", name="lw", rd=reg, rs1=SP_REG, imm=ImmValue(0), src=src, **f
        ),
        Instruction(
            type="i", name="addi", rd=SP_REG, rs1=SP_REG, imm=ImmValue(4), src=src, **f
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
            src = _clone_src(node.src)
            pseudo_flags = _node_flags(node, pseudo_expansion=True)
            if name == "push":
                # node.imm contains register number
                reg = (
                    node.imm.value if isinstance(node.imm, ImmValue) else int(node.imm)
                )
                out.extend(_emit_stack_push(reg, src=src, flags=pseudo_flags))
                continue
            if name == "pop":
                reg = (
                    node.imm.value if isinstance(node.imm, ImmValue) else int(node.imm)
                )
                out.extend(_emit_stack_pop(reg, src=src, flags=pseudo_flags))
                continue
            if name == "lli":
                rd = node.rd
                imm = node.imm
                if isinstance(imm, ImmLifted):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), rd, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(
                            imm.name, rd, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), rd, src=src, flags=pseudo_flags
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
                            int(imm.value), TEMP_REG, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(
                            imm.name, TEMP_REG, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=src, flags=pseudo_flags
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
                        src=src,
                        **pseudo_flags,
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
                            int(imm.value), TEMP_REG, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmLabel):
                    out.extend(
                        _emit_immediate_loading_for_label(
                            imm.name, TEMP_REG, src=src, flags=pseudo_flags
                        )
                    )
                elif isinstance(imm, ImmValue):
                    out.extend(
                        _emit_immediate_loading_for_value(
                            int(imm.value), TEMP_REG, src=src, flags=pseudo_flags
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
                        src=src,
                        **pseudo_flags,
                    )
                )
                continue

        # For normal instructions, handle lifted `li` immediates.
        if node.type in ["i", "l"] and isinstance(node.imm, ImmLifted):
            li = node.imm
            const_val = li.value
            src = _clone_src(node.src)
            base_flags = _node_flags(node, pseudo_expansion=False)
            # Use TEMP_REG to hold the constant.
            out.extend(_emit_stack_push(TEMP_REG, src=src, flags=base_flags))
            out.extend(
                _emit_immediate_loading_for_value(
                    int(const_val), TEMP_REG, src=src, flags=base_flags
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
                        src=src,
                        **base_flags,
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
                            src=src,
                            **base_flags,
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
                            src=src,
                            **base_flags,
                        )
                    )
                    out.append(
                        Instruction(
                            type="l",
                            name="lw",
                            rd=node.rd,
                            rs1=TEMP_REG,
                            imm=ImmValue(0),
                            src=src,
                            **base_flags,
                        )
                    )

            out.extend(_emit_stack_pop(TEMP_REG, src=src, flags=base_flags))
            continue

        # Otherwise, keep instruction unchanged
        out.append(node)

    return out
