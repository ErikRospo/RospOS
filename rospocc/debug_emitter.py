import json


class RoscDebugEmitter:
    def __init__(self, source_file):
        self.source_file = str(source_file)
        self.mappings = []

    def add_mapping(self, ros_line, rosc_file, rosc_line, original_text):
        self.mappings.append(
            {
                "ros_line": int(ros_line),
                "rosc_file": str(rosc_file),
                "rosc_line": int(rosc_line),
                "original_text": "" if original_text is None else str(original_text),
            }
        )

    def write(self, output_path):
        lines = [
            "VERSION: 1",
            f"SOURCE: {self.source_file}",
            "MAPPINGS:",
        ]

        for m in self.mappings:
            quoted = json.dumps(m["original_text"], ensure_ascii=False)
            lines.append(
                f"{m['ros_line']} {m['rosc_file']} {m['rosc_line']} {quoted}"
            )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
