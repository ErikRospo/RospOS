import argparse
from pathlib import Path

from debug_emitter import RoscDebugEmitter
import emitter
from lark import Lark
from preprocess import preprocess
from transformer import transform_to_translation_unit

# Resolve all filesystem paths relative to this file
HERE = Path(__file__).resolve().parent

with open(HERE / "rosc.lark", "r") as f:
    grammar = f.read()


# Use the transformer to convert Lark parse trees into a condensed dict
# structure consumed by the frontend/emitter.


# Command-line arguments (mirror compile.py behavior)
argp = argparse.ArgumentParser(description="Parse a .rosc file and emit .ros output")
argp.add_argument(
    "--input",
    type=str,
    required=True,
    help="Input source file to parse. Should be a .rosc file",
)
argp.add_argument(
    "--output",
    type=str,
    required=False,
    help="Output .ros file. If not provided, will use the input filename with .ros extension.",
)
args = argp.parse_args()

with open(args.input, "r") as f:
    code = f.read()

code = preprocess(code)

# Ensure output directory exists and write files there

if args.output is None:
    out = Path(args.input).with_suffix(".ros")
else:
    out = Path(args.output)

out_dir = out.parent
out_dir.mkdir(exist_ok=True)

preprocessed_name = f"{out.stem}_preprocessed.rosc"
with open(out_dir / preprocessed_name, "w") as f:
    f.write(code)


def parse_code(code):
    # Use Earley parser to avoid LALR reduce/reduce conflicts
    parser = Lark(grammar, parser="earley", debug=False)
    return parser.parse(code)


try:
    tree = parse_code(code)
except Exception as e:
    print("Error: parsing failed:", e)
    raise
ast_str = tree.pretty()
with open(out_dir / "ast.txt", "w") as f:
    f.write(ast_str)
# Convert parsed AST into the translation-unit for emitter (centralized)
tu = transform_to_translation_unit(tree)
emitter.emit_translation_unit(tu, str(out))

# Emit sidecar debug mapping for RospoAS consumption.
# This is line-based and captures the source text rospocc had during emission.
rosc_lines = code.splitlines()
with open(out, "r", encoding="utf-8") as f:
    ros_lines = f.read().splitlines()

dbg = RoscDebugEmitter(source_file=args.input)
for ros_line_no, ros_line in enumerate(ros_lines, start=1):
    stripped = ros_line.strip()
    if not stripped or stripped.startswith("//"):
        continue
    # Best-effort line map: preserve rospocc-owned source text by index.
    if ros_line_no <= len(rosc_lines):
        rosc_line_no = ros_line_no
        src_text = rosc_lines[rosc_line_no - 1]
    else:
        rosc_line_no = 0
        src_text = ""
    dbg.add_mapping(ros_line_no, args.input, rosc_line_no, src_text)

sidecar_path = out.with_suffix(".rosc.debug")
dbg.write(sidecar_path)
print("Emitted", out)
print("Emitted", sidecar_path)
