from pathlib import Path
import json

from errors import ParseError
from lark import Lark

grammar_file = Path(__file__).parent / "rospoas.lark"
with open(grammar_file, "r") as f:
    rospoas_grammar = f.read()

# Enable position propagation so instruction nodes carry source line info.
parser = Lark(rospoas_grammar, start="program", parser="lalr", propagate_positions=True)


def parse_source(source_code):
    return parser.parse(source_code)


def _parse_rospocc_sidecar(sidecar_path):
    mappings = {}
    if not sidecar_path.exists():
        return mappings

    mode = None
    with open(sidecar_path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            if line.startswith("MAPPINGS:"):
                mode = "mappings"
                continue
            if mode != "mappings":
                continue

            # Format: [ros_line] [rosc_file] [rosc_line] [quoted original text]
            parts = line.split(" ", 3)
            if len(parts) != 4:
                continue
            try:
                ros_line = int(parts[0])
                rosc_file = parts[1]
                rosc_line = int(parts[2])
                original_text = json.loads(parts[3])
            except Exception:
                continue

            mappings[ros_line] = {
                "file": rosc_file,
                "line": rosc_line,
                "original_text": original_text,
                "from_rospocc": True,
            }
    return mappings


def _load_rospocc_mappings_for_ros_file(current_file):
    current_file = Path(current_file)
    candidates = [
        current_file.with_suffix(".rosc.debug"),
        current_file.with_suffix(current_file.suffix + ".debug"),
    ]
    for candidate in candidates:
        mappings = _parse_rospocc_sidecar(candidate)
        if mappings:
            return mappings
    return {}


def preprocess_includes(
    source_code, current_file, included_files=None, include_chain=None
):
    """Preprocess `.INC` directives and return (lines, origins).

    Returns:
      - processed_lines: list of strings (one per output line)
            - origins: list of dict entries aligned with processed_lines
                Keys: file, line, original_text, include_chain

    This preserves origin information so later stages can report file/line locations.
    """
    if included_files is None:
        included_files = set()
    if include_chain is None:
        include_chain = []

    current_file = Path(current_file)
    rospocc_mappings = _load_rospocc_mappings_for_ros_file(current_file)

    lines = source_code.splitlines()
    processed_lines = []
    origins = []

    for idx, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if line.startswith(".INC"):
            # Extract the filename from the .INC directive
            start_idx = line.find('"') + 1
            end_idx = line.rfind('"')
            if start_idx == 0 or end_idx == -1:
                raise ParseError(f"Invalid .INC directive: {line}")
            include_path = Path(current_file).parent / line[start_idx:end_idx]

            # Check for circular includes
            if include_path in included_files:
                raise ParseError(f"Circular include detected: {include_path}")
            included_files.add(include_path)

            # Read and preprocess the included file
            if not include_path.exists():
                raise ParseError(f"Included file not found: {include_path}")
            with open(include_path, "r") as f:
                included_code = f.read()
            child_lines, child_origins = preprocess_includes(
                included_code,
                include_path,
                included_files,
                include_chain + [str(current_file)],
            )
            processed_lines.extend(child_lines)
            origins.extend(child_origins)
        else:
            processed_lines.append(raw_line)
            if idx in rospocc_mappings:
                m = rospocc_mappings[idx]
                origins.append(
                    {
                        "file": m.get("file") or str(current_file),
                        "line": m.get("line", idx),
                        "original_text": m.get("original_text", raw_line),
                        "include_chain": list(include_chain) + [str(current_file)],
                        "from_rospocc": True,
                    }
                )
            else:
                origins.append(
                    {
                        "file": str(current_file),
                        "line": idx,
                        "original_text": raw_line,
                        "include_chain": list(include_chain),
                        "from_rospocc": False,
                    }
                )

    return processed_lines, origins
