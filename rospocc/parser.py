import argparse
import json
from copy import copy
from pathlib import Path

from lark import Lark, Token, Tree

import emitter
from preprocess import preprocess
from transformer import  transform_to_translation_unit

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
preprocessed = copy(code)

# Ensure output directory exists and write files there
out_dir = HERE / "out"
out_dir.mkdir(exist_ok=True)

preprocessed_name = f"{Path(args.input).stem}_preprocessed.rosc"
with open(out_dir / preprocessed_name, "w") as f:
    f.write(code)

if args.output is None:
    out = Path(args.input).with_suffix(".ros")
else:
    out = Path(args.output)


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

out = out_dir / "generated.ros"
emitter.emit_translation_unit(tu, str(out))
print("Emitted", out)
