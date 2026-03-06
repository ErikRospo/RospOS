import json


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
