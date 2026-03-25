import argparse
import re
from pathlib import Path

import emitter
from debug_emitter import RoscDebugEmitter
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

code = preprocess(code, current_file=args.input)

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
    # Enable propagate_positions to preserve line information
    parser = Lark(grammar, parser="earley", debug=False, propagate_positions=True)
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
tu = transform_to_translation_unit(tree, source_file=args.input)

# Load source lines for tracking
with open(out_dir / preprocessed_name, "r") as f:
    source_lines = f.read().splitlines()

# Emit translation unit with source tracking enabled
mappings = emitter.emit_translation_unit(
    tu,
    str(out),
    source_file=str(out_dir / preprocessed_name),
    source_lines=source_lines,
)

# Write sidecar debug file with tracked mappings
dbg = RoscDebugEmitter(source_file=out_dir / preprocessed_name)
for mapping in mappings:
    dbg.add_mapping(
        mapping["output_line"],
        out_dir / preprocessed_name,
        mapping["source_line"],
        mapping["source_text"],
    )

sidecar_path = out.with_suffix(".rosc.debug")
dbg.write(sidecar_path)
print(f"Emitted {out}")
print(f"Emitted {sidecar_path} with {len(mappings)} tracked mappings")
