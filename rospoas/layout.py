"""Layout stage: compute symbol addresses and segment buffers from typed IR.

This module performs a deterministic single-pass layout that records
label addresses and allocates segment bytearrays sized to hold the
instructions/data. It does not perform relocations; it only computes
addresses and sizes to be used by the encoder stage.
"""
from typing import List, Tuple, Dict

from ir import Instruction, LabelDecl, Directive, Segment, ImmValue


def _instr_size(node) -> int:
    if isinstance(node, Instruction):
        return 4
    if isinstance(node, Directive) and node.name == "data":
        if node.length is not None:
            # enforce minimum word-sized allocation for data directives
            return max(4, int(node.length))
        # fallback: if immediate is ImmValue, estimate minimum bytes
        if isinstance(node.imm, ImmValue):
            v = node.imm.value
            return max(4, (v.bit_length() // 8) + 1)
        return 4
    return 0


def layout_ir(ir_list: List) -> Tuple[Dict[str, int], List[Tuple[int, bytearray]]]:
    """Compute addresses for labels and allocate segments.

    Returns (addresses, segments) where segments is a list of (addr, data_bytearray).
    """
    addresses: Dict[str, int] = {}
    segments: List[Tuple[int, bytearray]] = []

    current_segment_addr = 0
    current_segment_data = None
    current_address = 0

    # Use index-based loop so we can peek next node for label alignment decisions

    last_was_data = False
    for idx in range(len(ir_list)):
        node = ir_list[idx]
        # Segment directive
        if isinstance(node, Directive) and node.name == "seg":
            # flush previous segment
            if current_segment_data is not None:
                segments.append((current_segment_addr, current_segment_data))

            # start new segment
            seg_addr = None
            if node.imm is not None:
                if hasattr(node.imm, "value"):
                    seg_addr = int(node.imm.value)
                else:
                    seg_addr = int(node.imm)
            else:
                seg_addr = 0

            current_segment_addr = seg_addr
            current_segment_data = bytearray()
            current_address = seg_addr
            last_was_data = False
            continue

        # Ensure we have a segment
        if current_segment_data is None:
            current_segment_addr = 0
            current_segment_data = bytearray()
            current_address = 0

        # Label declaration
        if isinstance(node, LabelDecl):
            next_node = ir_list[idx + 1] if idx + 1 < len(ir_list) else None
            # If the label is immediately followed by an instruction, ensure
            # the label address is instruction-aligned (4 bytes) so jumps
            # targeting the label land at the proper word boundary.
            if isinstance(next_node, Instruction):
                # If previous node was data, always align to next 4-byte boundary
                align = (4 - (current_address % 4)) % 4
                if align:
                    current_segment_data.extend(b"\x00" * align)
                    current_address += align
            addresses[node.name] = current_address
            continue

        # Data directive
        if isinstance(node, Directive) and node.name == "data":
            size = _instr_size(node)
            current_segment_data.extend(b"\x00" * size)
            current_address += size
            last_was_data = True
            continue

        # Instruction: ensure 4-byte alignment before reserving instruction bytes
        if isinstance(node, Instruction):
            # If previous node was data, always align to next 4-byte boundary
            if last_was_data:
                align = (4 - (current_address % 4)) % 4
                if align:
                    current_segment_data.extend(b"\x00" * align)
                    current_address += align
            last_was_data = False
            align = (4 - (current_address % 4)) % 4
            if align:
                current_segment_data.extend(b"\x00" * align)
                current_address += align
            current_segment_data.extend(b"\x00" * 4)
            current_address += 4
            continue

        # Unknown node: ignore

    if current_segment_data is not None:
        segments.append((current_segment_addr, current_segment_data))

    # Validate segments do not overlap
    if segments:
        # sort by address and ensure no overlap
        segments_sorted = sorted(segments, key=lambda s: s[0])
        prev_addr, prev_data = segments_sorted[0]
        prev_end = prev_addr + len(prev_data)
        for addr, data in segments_sorted[1:]:
            if addr < prev_end:
                raise ValueError(f"Segment overlap detected: segment at {hex(addr)} overlaps previous end {hex(prev_end)}")
            prev_end = addr + len(data)

    return addresses, segments
