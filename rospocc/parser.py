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


with open(HERE / "first_test.rosc", "r") as f:
    code = f.read()

code = preprocess(code)
preprocessed = copy(code)

# Ensure output directory exists and write files there
out_dir = HERE / "out"
out_dir.mkdir(exist_ok=True)

with open(out_dir / "preprocessed_code.rosc", "w") as f:
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

out = out_dir / "generated.ros"
emitter.emit_translation_unit(tu, str(out))
print("Emitted", out)
