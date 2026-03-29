import json
from typing import Dict, List, Optional

from ir import Directive
from ir import Instruction as IRInstruction
from ir import LabelDecl
from utility import _debug_flags_from_node, _imm_to_int, _node_original_text


class RegisterAllocation:
    """Register allocation metadata captured for an instruction address."""

    def __init__(
        self,
        register: str,
        variable_name: str,
        variable_type: str,
        var_kind: str = "local",
        origin: Optional[str] = None,
    ):
        self.register = register
        self.variable_name = variable_name
        self.variable_type = variable_type
        self.var_kind = var_kind
        self.origin = origin

    def to_dict(self) -> Dict[str, object]:
        return {
            "register": self.register,
            "variable_name": self.variable_name,
            "variable_type": self.variable_type,
            "var_kind": self.var_kind,
            "origin": self.origin,
        }


def collect_debug_segments(ir_nodes):
    writers = {}

    current_segment = 0
    current_address = 0
    gap_pending = False
    last_was_data = False

    def ensure_writer():
        nonlocal current_segment, gap_pending
        if current_segment is None or gap_pending:
            current_segment = current_address
            gap_pending = False
        return writers.setdefault(current_segment, DebugInfoWriter())

    for idx, node in enumerate(ir_nodes):
        if isinstance(node, Directive) and node.name == "seg":
            seg_addr = _imm_to_int(node.imm)
            if seg_addr is None:
                seg_addr = 0
            current_segment = seg_addr
            current_address = seg_addr
            gap_pending = False
            last_was_data = False
            continue

        if isinstance(node, LabelDecl):
            next_node = ir_nodes[idx + 1] if idx + 1 < len(ir_nodes) else None
            if isinstance(next_node, IRInstruction):
                align = (4 - (current_address % 4)) % 4
                if align:
                    ensure_writer()
                    current_address += align
            continue

        if isinstance(node, Directive) and node.name == "space":
            size = _imm_to_int(node.imm)
            if size is None and node.length is not None:
                size = int(node.length)
            if size is None:
                size = 0
            current_address += int(size)
            current_segment = None
            gap_pending = True
            last_was_data = False
            continue

        if isinstance(node, Directive) and node.name == "data":
            writer = ensure_writer()
            addr = current_address
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
            current_address += int(size)
            last_was_data = True
            continue

        if isinstance(node, IRInstruction):
            writer = ensure_writer()

            if last_was_data:
                align = (4 - (current_address % 4)) % 4
                if align:
                    current_address += align
            last_was_data = False

            align = (4 - (current_address % 4)) % 4
            if align:
                current_address += align

            addr = current_address
            writer.add_entry(
                address=addr,
                flags=_debug_flags_from_node(node),
                src_info=getattr(node, "src", None),
                original_text=_node_original_text(node),
            )
            current_address += 4

    return writers


class DebugInfoWriter:
    def __init__(self):
        self.entries: List[Dict[str, object]] = []
        self.file_table: Dict[str, int] = {}
        self.file_id_counter = 0
        self.register_allocations: Dict[int, List[RegisterAllocation]] = {}

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

        pp_line_raw = src.get("pp_line", 0)
        if isinstance(pp_line_raw, int):
            pp_line = pp_line_raw
        else:
            try:
                pp_line = int(str(pp_line_raw))
            except Exception:
                pp_line = 0

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
                "line": int(line),
                "pp_line": int(pp_line),
                "original_text": str(text),
            }
        )

    def add_register_allocation(self, address: int, register_alloc: RegisterAllocation):
        self.register_allocations.setdefault(int(address), []).append(register_alloc)

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

        if self.register_allocations:
            lines.append("REGISTERS:")
            for addr in sorted(self.register_allocations.keys()):
                allocs = self.register_allocations[addr]
                for alloc in allocs:
                    alloc_json = json.dumps(alloc.to_dict(), ensure_ascii=False)
                    lines.append(f"0x{addr:08X} {alloc_json}")

        return "\n".join(lines) + "\n"
