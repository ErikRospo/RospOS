import argparse
import sys
from pathlib import Path

from compilation_pipeline import (
    CompilationOptions,
    CompilationPipeline,
    build_frontend_registry,
    select_frontend,
)
from compile_debug import register_debug_handlers


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile RospoAS source code.")
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="Input source file to compile. Should be a .ros file",
    )
    parser.add_argument(
        "--output",
        type=str,
        required=False,
        help="Output binary file. If not provided, will use the input filename with .rosp extension.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug output during compilation (e.g., print IR, layout info, etc.)",
    )
    parser.add_argument(
        "--debug-ast",
        action="store_true",
        help="Output the parsed AST to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-preprocessed",
        action="store_true",
        help="Output the preprocessed source code (after handling includes) to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-parse",
        action="store_true",
        help="Output the parsed AST to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-ir",
        action="store_true",
        help="Output the generated IR to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-layout",
        action="store_true",
        help="Output the layout information (addresses, segments) to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-mapping",
        action="store_true",
        help="Output the mapping of IR nodes to addresses in the final binary for debugging purposes.",
    )
    parser.add_argument(
        "--debug-segments",
        action="store_true",
        help="Output the final segments (address and size) to a file for debugging purposes.",
    )
    parser.add_argument(
        "--debug-all",
        action="store_true",
        help="Enable all debug outputs (AST, IR, layout, mapping, segments).",
    )
    parser.add_argument(
        "--optimize",
        action="store_true",
        help="Enable optimizations on the IR before layout and encoding.",
    )
    parser.add_argument(
        "--no-optimize",
        dest="optimize",
        action="store_false",
        help="Disable optimizations on the IR before layout and encoding.",
    )
    parser.set_defaults(optimize=True)
    parser.add_argument(
        "--bin-version",
        type=int,
        default=2,
        help="Output binary version (default: 2)",
    )
    parser.add_argument(
        "--rospocc-mapping",
        action="store_true",
        help="Attempt to load source mappings from a RospoCC sidecar debug file (.rosc.debug) if it exists.",
    )
    parser.set_defaults(rospocc_mapping=True)
    parser.add_argument(
        "--segment-debug",
        action="store_true",
        help="Include debug information in the output binary as separate debug segments.",
    )
    return parser


def build_debug_enabled(args) -> dict[str, bool]:
    debug_enabled = {
        "ast": args.debug_ast,
        "parse": args.debug_parse,
        "preprocessed": args.debug_preprocessed,
        "ir": args.debug_ir,
        "layout": args.debug_layout,
        "mapping": args.debug_mapping,
        "segments": args.debug_segments,
    }
    if args.debug_all:
        for key in debug_enabled:
            debug_enabled[key] = True
    return debug_enabled


def build_options(args) -> CompilationOptions:
    input_path = Path(args.input)
    output_path = Path(args.output or input_path.with_suffix(".rosp"))
    return CompilationOptions(
        input_path=input_path,
        output_path=output_path,
        optimize=args.optimize,
        bin_version=args.bin_version,
        rospocc_mapping=args.rospocc_mapping,
        segment_debug=args.segment_debug,
        verbose=args.verbose,
        debug_enabled=build_debug_enabled(args),
    )


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    options = build_options(args)

    if options.rospocc_mapping and options.bin_version < 2:
        print(
            "Warning: --rospocc-mapping is only supported for binary version 2. Ignoring this option."
        )

    frontends = build_frontend_registry()
    pipeline = CompilationPipeline()
    register_debug_handlers(pipeline)

    try:
        frontend = select_frontend(frontends, options.input_path)
        pipeline.compile(frontend, options)
    except Exception as exc:
        print(exc)
        return 1

    if options.bin_version == 2:
        print(f"Wrote V2 binary to {options.output_path}")
    else:
        print(f"Wrote V{options.bin_version} binary to {options.output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
