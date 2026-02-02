"""Encoding stage: resolve immediates, validate ranges, and write final bytes.
"""
from typing import List, Tuple, Dict
from ir import Instruction, LabelDecl, Directive, ImmValue, ImmLabel, ImmLabelPart, ImmLifted
from encoding import opcode_type_map, instr_type_maps, validate_immediate_for_type


def _resolve_imm(imm, addresses, current_segment_addr, cursor):
    if imm is None:
        return None
    if isinstance(imm, ImmValue):
        return int(imm.value)
    if isinstance(imm, ImmLifted):
        return int(imm.value)
    if isinstance(imm, ImmLabelPart):
        lbl = imm.label
        if lbl not in addresses:
            raise ValueError(f"Undefined label for label-part: {lbl}")
        addr = addresses[lbl]
        if imm.part == "high":
            return (addr >> 16) & 0xFFFF
        elif imm.part == "low":
            return addr & 0xFFFF
        else:
            raise ValueError(f"Unknown label part: {imm.part}")
    if isinstance(imm, ImmLabel):
        name = imm.name
        if name not in addresses:
            raise ValueError(f"Undefined label: {name}")
        # relative offset in words from next instruction
        return (addresses[name] - (current_segment_addr + cursor)) // 4
    # fallback: assume raw int
    return int(imm)


def encode_ir(ir_list: List, addresses: Dict[str, int], segments: List[Tuple[int, bytearray]]):
    current_segment = None
    current_segment_data = None
    cursor = 0
    for node in ir_list:
        if isinstance(node, Directive) and node.name == "seg":
            seg_addr = None
            if node.imm is not None:
                try:
                    seg_addr = int(node.imm.value)
                except Exception:
                    seg_addr = int(node.imm)
            else:
                seg_addr = 0
            # find matching segment buffer
            current_segment = seg_addr
            current_segment_data = next((d for a, d in segments if a == seg_addr), None)
            cursor = 0
            continue

        if current_segment_data is None:
            raise AssertionError("No current segment while encoding")

        if isinstance(node, LabelDecl):
            # labels do not consume bytes
            continue

        if isinstance(node, Directive) and node.name == "data":
            data_value = node.imm
            if isinstance(data_value, bytes):
                data_bytes = data_value
            elif isinstance(data_value, ImmValue):
                v = int(data_value.value)
                length = node.length or ((v.bit_length() // 8) + 1)
                data_bytes = v.to_bytes(length, byteorder="little", signed=True)
            else:
                v = int(data_value)
                length = node.length or ((v.bit_length() // 8) + 1)
                data_bytes = v.to_bytes(length, byteorder="little", signed=True)
            current_segment_data[cursor:cursor+len(data_bytes)] = data_bytes
            cursor += len(data_bytes)
            continue

        if isinstance(node, Instruction):
            t_type = node.type
            name = node.name
            rd = node.rd
            rs1 = node.rs1
            rs2 = node.rs2

            # Coerce register-like fields to ints if they are wrapped immediates
            def _reg_to_int(x):
                if x is None:
                    return None
                if hasattr(x, "value"):
                    try:
                        return int(x.value)
                    except Exception:
                        pass
                try:
                    return int(x)
                except Exception:
                    return x

            rd = _reg_to_int(rd)
            rs1 = _reg_to_int(rs1)
            rs2 = _reg_to_int(rs2)

            # Do not unconditionally default registers here; each type
            # branch asserts presence when required to avoid noisy warnings.
            imm = node.imm

            type_id = opcode_type_map[t_type]
            opcode = instr_type_maps[type_id][name]
            op_byte = (type_id << 4) | opcode

            # resolve immediates to ints where applicable
            resolved_imm = None
            if imm is not None:
                resolved_imm = _resolve_imm(imm, addresses, current_segment, cursor)

            try:
                if type_id == 0:  # R-type
                    assert rd is not None and rs1 is not None and rs2 is not None
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 4) | (rs2 & 0x0F)
                    op_byte = op_byte << 12

                elif type_id in [1, 2]:  # I/L-type
                    assert rd is not None and rs1 is not None and resolved_imm is not None
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 3:  # B-type
                    assert rd is not None and rs1 is not None and resolved_imm is not None
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 4:  # J-type
                    assert rd is not None and rs1 is not None and resolved_imm is not None
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 5:  # S-type
                    op_byte = op_byte << 24
            except AssertionError:
                raise ValueError(f"Encoding assertion failed at segment {current_segment} cursor {cursor} for node: {node}")

            bytes_out = (op_byte & 0xFFFFFFFF).to_bytes(4, byteorder="big")
            current_segment_data[cursor:cursor+4] = bytes_out
            cursor += 4
            continue

    return segments
