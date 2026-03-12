import json

from ir import Directive
from ir import Instruction as IRInstruction
from ir import LabelDecl
from utility import _debug_flags_from_node, _imm_to_int, _node_original_text


def collect_debug_segments(ir_nodes):
    writers = {}

    current_segment = 0
    current_cursor = 0
    last_was_data = False

    for idx, node in enumerate(ir_nodes):
        if isinstance(node, Directive) and node.name == "seg":
            seg_addr = _imm_to_int(node.imm)
            if seg_addr is None:
                seg_addr = 0
            current_segment = seg_addr
            current_cursor = 0
            last_was_data = False
            writers.setdefault(current_segment, DebugInfoWriter())
            continue

        if isinstance(node, LabelDecl):
            next_node = ir_nodes[idx + 1] if idx + 1 < len(ir_nodes) else None
            if isinstance(next_node, IRInstruction):
                align = (4 - (current_cursor % 4)) % 4
                if align:
                    current_cursor += align
            continue

        if isinstance(node, Directive) and node.name == "data":
            writer = writers.setdefault(current_segment, DebugInfoWriter())
            addr = current_segment + current_cursor
            writer.add_entry(
                address=addr,
                flags=_debug_flags_from_node(node),
                src_info=getattr(node, "src", None),
                original_text=_node_original_text(node),
            )

            if node.length is not None:
                size = int(node.length)
            else:
                imm_int = _imm_to_int(node.imm)
                if imm_int is not None:
                    size = (imm_int.bit_length() // 8) + 1
                else:
                    size = 4
            size = max(4, size)
            current_cursor += size
            last_was_data = True
            continue

        if isinstance(node, IRInstruction):
            writer = writers.setdefault(current_segment, DebugInfoWriter())

            if last_was_data:
                align = (4 - (current_cursor % 4)) % 4
                if align:
                    current_cursor += align
            last_was_data = False

            align = (4 - (current_cursor % 4)) % 4
            if align:
                current_cursor += align

            addr = current_segment + current_cursor
            writer.add_entry(
                address=addr,
                flags=_debug_flags_from_node(node),
                src_info=getattr(node, "src", None),
                original_text=_node_original_text(node),
            )
            current_cursor += 4

    return writers


class DebugInfoWriter:
    def __init__(self):
        self.entries = []
        self.file_table = {}
        self.file_id_counter = 0

    def get_file_id(self, filepath):
        if filepath is None:
            filepath = "<unknown>"
        if filepath not in self.file_table:
            self.file_table[filepath] = self.file_id_counter
            self.file_id_counter += 1
        return self.file_table[filepath]

    def add_entry(self, address, flags, src_info, original_text):
        src = src_info if isinstance(src_info, dict) else {}
        file_id = self.get_file_id(src.get("file"))
        line_raw = src.get("line", 0)
        if isinstance(line_raw, int):
            line = line_raw
        else:
            try:
                line = int(str(line_raw))
            except Exception:
                line = 0
        text = original_text
        if text is None:
            text = src.get("original_text")
        if text is None:
            text = ""

        self.entries.append(
            {
                "address": int(address),
                "flags": int(flags),
                "file_id": int(file_id),
                "line": line,
                "original_text": str(text),
            }
        )

    def write_debug_segment(self, segment_addr):
        lines = [
            "DEBUG_VERSION: 1",
            f"SEGMENT_ADDRESS: 0x{int(segment_addr):08X}",
            "ENCODING: UTF-8",
            "",
        ]

        for entry in self.entries:
            quoted = json.dumps(entry["original_text"], ensure_ascii=False)
            lines.append(
                f"0x{entry['address']:08X} 0x{entry['flags']:08X} {entry['file_id']} {entry['line']} {quoted}"
            )

        lines.append("FILES:")
        file_items = sorted(self.file_table.items(), key=lambda kv: kv[1])
        for path, fid in file_items:
            lines.append(f"{fid} {path}")

        return "\n".join(lines) + "\n"
