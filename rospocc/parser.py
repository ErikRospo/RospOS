import argparse
import json
import re
import sys
from pathlib import Path
from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from rospolog import configure_logging

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


def compile_source(code, output_path, source_file="<memory>", verbosity=0):
    """Compile source text to assembler text and return source mappings."""
    code = preprocess(code, current_file=source_file)
    logger.debug("Preprocessed {} into {} lines", source_file, len(code.splitlines()))
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    preprocessed_path = out.with_name(f"{out.stem}_preprocessed.rosc")
    preprocessed_path.write_text(code, encoding="utf-8")
    tree = parse_code(code)
    logger.debug("Parsed {}", source_file)
    if verbosity >= 2:
        logger.trace("RospoCC parse tree for {}:\n{}", source_file, tree.pretty())
    tu = transform_to_translation_unit(tree, source_file=source_file)
    if verbosity >= 3:
        logger.trace(
            "RospoCC translation unit for {}:\n{}",
            source_file,
            json.dumps(tu, indent=2, ensure_ascii=False, default=str),
        )
    mappings = emitter.emit_translation_unit(
        tu,
        str(out),
        source_file=str(preprocessed_path),
        source_lines=code.splitlines(),
    )
    return out, preprocessed_path, tu, mappings


def build_parser():
    argp = argparse.ArgumentParser(description="Parse a .rosc file and emit .ros output")
    argp.add_argument("--input", type=str, required=True, help="Input .rosc file")
    argp.add_argument(
        "-v",
        "--verbose",
        action="count",
        default=0,
        help="Show warning references (-v), source context (-vv), and full details (-vvv).",
    )
    argp.add_argument(
        "--diagnose",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override Loguru's variable diagnostics for exceptions (default: enabled with -vvv).",
    )
    argp.add_argument(
        "--backtrace",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override Loguru's expanded exception backtraces (default: enabled with -vv).",
    )
    argp.add_argument("--output", type=str, help="Output .ros file")
    argp.add_argument("--fast", action="store_true", help="Skip optional parse artifacts and debug sidecar")
    argp.add_argument("--no-ast-dump", action="store_true", help="Do not write ast.txt")
    argp.add_argument("--no-tu-dump", action="store_true", help="Do not write tu.json")
    argp.add_argument("--no-debug-sidecar", action="store_true", help="Do not write .rosc.debug")
    return argp


def main(argv=None):
    args = build_parser().parse_args(argv)
    input_path = Path(args.input)
    out = Path(args.output) if args.output else input_path.with_suffix(".ros")
    log_path = configure_logging(
        "rospocc",
        args.verbose,
        out.parent / "rospocc.log",
        diagnose=args.diagnose,
        backtrace=args.backtrace,
    )
    logger.info("Starting compiler; detailed log: {}", log_path)
    try:
        code = input_path.read_text(encoding="utf-8")
        out, preprocessed_path, tu, mappings = compile_source(
            code, out, str(input_path), verbosity=args.verbose
        )
        if not (args.fast or args.no_ast_dump):
            (out.parent / "ast.txt").write_text(
                parse_code(preprocessed_path.read_text()).pretty(), encoding="utf-8"
            )
        if not (args.fast or args.no_tu_dump):
            (out.parent / "tu.json").write_text(
                json.dumps(tu, indent=2, ensure_ascii=False, default=str),
                encoding="utf-8",
            )
        if not (args.fast or args.no_debug_sidecar):
            dbg = RoscDebugEmitter(source_file=preprocessed_path)
            for mapping in mappings:
                dbg.add_mapping(
                    mapping["output_line"],
                    preprocessed_path,
                    mapping["source_line"],
                    mapping["source_text"],
                )
            sidecar = out.with_suffix(".rosc.debug")
            dbg.write(sidecar)
            logger.info("Emitted {} with {} tracked mappings", sidecar, len(mappings))
        logger.info("Emitted {}", out)
    except Exception as exc:
        logger.exception("Compilation failed: {}", exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
