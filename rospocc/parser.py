import argparse
import json
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


_PARSER = None


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
argp.add_argument(
    "--fast",
    action="store_true",
    help="Fast mode: skip non-essential parser artifacts and .rosc.debug generation.",
)
argp.add_argument(
    "--no-ast-dump",
    action="store_true",
    help="Do not write ast.txt.",
)
argp.add_argument(
    "--no-tu-dump",
    action="store_true",
    help="Do not write tu.json.",
)
argp.add_argument(
    "--no-debug-sidecar",
    action="store_true",
    help="Do not write .rosc.debug sidecar mappings.",
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
    global _PARSER

    # Use LALR for significantly faster parsing.
    # Enable propagate_positions to preserve line information.
    # Keep parser instance cached per-process and let Lark cache parse tables
    # across process invocations.
    if _PARSER is None:
        _PARSER = Lark(
            grammar,
            parser="lalr",
            debug=False,
            propagate_positions=True,
            cache=True,
        )
    return _PARSER.parse(code)


try:
    tree = parse_code(code)
except Exception as e:
    print("Error: parsing failed:", e)
    raise
ast_str = tree.pretty()
emit_ast_dump = not (args.fast or args.no_ast_dump)
if emit_ast_dump:
    with open(out_dir / "ast.txt", "w") as f:
        f.write(ast_str)
# Convert parsed AST into the translation-unit for emitter (centralized)
tu = transform_to_translation_unit(tree, source_file=args.input)


emit_tu_dump = not (args.fast or args.no_tu_dump)
if emit_tu_dump:
    tu_json = json.dumps(tu, indent=2, ensure_ascii=False, default=str)
    with open(out_dir / "tu.json", "w") as f:
        f.write(tu_json)
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
emit_debug_sidecar = not (args.fast or args.no_debug_sidecar)
if emit_debug_sidecar:
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
if emit_debug_sidecar:
    print(
        f"Emitted {out.with_suffix('.rosc.debug')} with {len(mappings)} tracked mappings"
    )
