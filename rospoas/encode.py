"""Encoding stage: resolve immediates, validate ranges, and write final bytes."""

import sys
from typing import Dict, List, Tuple

from encoding import (instr_type_maps, opcode_type_map,
                      validate_immediate_for_type)
from ir import (Directive, ImmLabel, ImmLabelPart, ImmLifted, ImmValue,
                Instruction, LabelDecl)


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


def encode_ir(
    ir_list: List, addresses: Dict[str, int], segments: List[Tuple[int, bytearray]]
):
    current_segment = None
    current_segment_data = None
    cursor = 0
    # record layout of nodes per segment for post-encode diagnostics
    segment_node_map = {}
    # track cursors per segment for validation
    segment_cursor_map = {}
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
            # record previous segment usage before switching
            if current_segment is not None:
                segment_cursor_map[current_segment] = cursor

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
            if cursor + len(data_bytes) > len(current_segment_data):
                raise ValueError(
                    f"Data write would overflow segment {hex(current_segment)} at cursor {cursor}"
                )
            current_segment_data[cursor : cursor + len(data_bytes)] = data_bytes
            # record node
            segment_node_map.setdefault(current_segment, []).append(
                (cursor, len(data_bytes), "data")
            )
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
                    assert (
                        rd is not None and rs1 is not None and resolved_imm is not None
                    )
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 3:  # B-type
                    assert (
                        rd is not None and rs1 is not None and resolved_imm is not None
                    )
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 4:  # J-type
                    assert (
                        rd is not None and rs1 is not None and resolved_imm is not None
                    )
                    validate_immediate_for_type(type_id, resolved_imm)
                    op_byte = (op_byte << 4) | (rd & 0x0F)
                    op_byte = (op_byte << 4) | (rs1 & 0x0F)
                    op_byte = (op_byte << 16) | (resolved_imm & 0xFFFF)

                elif type_id == 5:  # S-type
                    op_byte = op_byte << 24
            except AssertionError:
                raise ValueError(
                    f"Encoding assertion failed at segment {current_segment} cursor {cursor} for node: {node}"
                )

            bytes_out = (op_byte & 0xFFFFFFFF).to_bytes(4, byteorder="big")
            if cursor + 4 > len(current_segment_data):
                raise ValueError(
                    f"Instruction write would overflow segment {hex(current_segment)} at cursor {cursor}"
                )
            current_segment_data[cursor : cursor + 4] = bytes_out
            segment_node_map.setdefault(current_segment, []).append(
                (cursor, 4, "instr")
            )
            cursor += 4
            continue

    # Record final cursor for the last segment
    if current_segment is not None:
        segment_cursor_map[current_segment] = cursor

    # Post-encode diagnostics: check labels land on expected node types
    for name, addr in addresses.items():
        found_seg = None
        for seg_addr, seg_data in segments:
            if seg_addr <= addr < seg_addr + len(seg_data):
                found_seg = (seg_addr, seg_data)
                break
        if found_seg is None:
            print(
                f"Warning: label {name} at {hex(addr)} is not in any segment",
                file=sys.stderr,
            )
            continue
        seg_addr, seg_data = found_seg
        offset = addr - seg_addr
        node_list = segment_node_map.get(seg_addr, [])
        hit = None
        for start, size, ntype in node_list:
            if start <= offset < start + size:
                hit = (start, size, ntype)
                break
        if hit is None:
            # label points between nodes: OK but warn
            print(
                f"Note: label {name} at {hex(addr)} points between nodes in segment {hex(seg_addr)}",
                file=sys.stderr,
            )
        else:
            if hit[2] == "data":
                print(
                    f"Warning: label {name} at {hex(addr)} falls inside a data region (segment {hex(seg_addr)} offset {hit[0]})",
                    file=sys.stderr,
                )

    # Print per-segment node map for debugging
    print("--- Segment node layout ---", file=sys.stderr)
    for seg_addr, nodes in segment_node_map.items():
        print(
            f"Segment {hex(seg_addr)} (size {len(next(d for a,d in segments if a==seg_addr))}):",
            file=sys.stderr,
        )
        for start, size, ntype in nodes:
            print(f"  {start:04} - {start+size-1:04} : {ntype}", file=sys.stderr)

    # Validate that each segment was fully reserved by layout and encoded writes match sizes
    for seg_addr, data in segments:
        reserved = len(data)
        used = segment_cursor_map.get(seg_addr, 0)
        if used != reserved:
            print(
                f"Warning: segment {hex(seg_addr)} reserved {reserved} bytes but encoder used {used} bytes",
                file=sys.stderr,
            )

    # Post-encode verification: check that each instruction slot decodes to a valid opcode/type
    for seg_addr, seg_data in segments:
        node_list = segment_node_map.get(seg_addr, [])
        for start, size, ntype in node_list:
            if ntype == "instr":
                word = int.from_bytes(seg_data[start : start + 4], byteorder="big")
                op_nibble = (word >> 28) & 0xF
                opcode = (word >> 24) & 0xF
                valid = False
                if 0 <= op_nibble < len(instr_type_maps):
                    t_map = instr_type_maps[op_nibble]
                    if opcode in t_map.values():
                        valid = True
                if not valid:
                    print(
                        f"Warning: instruction at segment {hex(seg_addr)} offset {start} decodes as NOP/UNKNOWN (word={word:08x})",
                        file=sys.stderr,
                    )
    return segments
