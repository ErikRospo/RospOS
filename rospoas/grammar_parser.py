from pathlib import Path

from lark import Lark

grammar_file = Path(__file__).parent / "rospoas.lark"
with open(grammar_file, "r") as f:
    rospoas_grammar = f.read()

parser = Lark(rospoas_grammar, start="program", parser="lalr")


def parse_source(source_code):
    return parser.parse(source_code)


def preprocess_includes(source_code, current_file, included_files=None):
    if included_files is None:
        included_files = set()

    lines = source_code.splitlines()
    processed_lines = []

    for line in lines:
        line = line.strip()
        if line.startswith(".INC"):
            # Extract the filename from the .INC directive
            start_idx = line.find('"') + 1
            end_idx = line.rfind('"')
            if start_idx == 0 or end_idx == -1:
                raise ValueError(f"Invalid .INC directive: {line}")
            include_path = Path(current_file).parent / line[start_idx:end_idx]

            # Check for circular includes
            if include_path in included_files:
                raise ValueError(f"Circular include detected: {include_path}")
            included_files.add(include_path)

            # Read and preprocess the included file
            if not include_path.exists():
                raise FileNotFoundError(f"Included file not found: {include_path}")
            with open(include_path, "r") as f:
                included_code = f.read()
            processed_lines.extend(
                preprocess_includes(included_code, include_path, included_files)
            )
        else:
            processed_lines.append(line)

    return processed_lines
