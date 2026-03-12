import argparse
import json
import struct
import sys
from pathlib import Path

from debug_writer import DebugInfoWriter, collect_debug_segments
from encode import encode_ir
from grammar_parser import parse_source, preprocess_includes
from ir import Directive, ImmValue
from ir import Instruction as IRInstruction
from ir import LabelDecl
from layout import layout_ir
from lower import lower_ir
from optimizer import optimize
from utility import _imm_to_int
from transformer import transform_parse_tree_ir

# Parse command-line arguments
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
    "--bin-version", type=int, default=2, help="Output binary version (default: 2)"
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


args = parser.parse_args()

if args.rospocc_mapping and args.version < 2:
    print(
        "Warning: --rospocc-mapping is only supported for binary version 2. Ignoring this option."
    )

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

if args.output is None:
    args.output = args.input.rsplit(".", 1)[0] + ".rosp"  # ROS Program

# Read source code
with open(args.input, "r") as f:
    source_code = f.read()


pre_lines, origin_map = preprocess_includes(source_code, args.input)
preprocessed_code = "\n".join(pre_lines)
if debug_enabled["preprocessed"]:
    preprocessed_filename = args.output.rsplit(".", 1)[0] + "_preprocessed.ros"
    with open(preprocessed_filename, "w") as f:
        f.write(preprocessed_code)
# Parse and transform the preprocessed source code
parse_tree = parse_source(preprocessed_code)
# Produce typed IR (from legacy AST) and lifted constants
ir_list, lifted_constants = transform_parse_tree_ir(parse_tree, origin_map=origin_map)
if args.optimize:
    ir_list = optimize(
        ir_list, outloc=Path(args.output).parent, debug_enabled=debug_enabled
    )
# Lower pseudo-instructions and lifted constants into concrete IR
ir_list = lower_ir(ir_list)
if debug_enabled["ir"]:
    ir_filename = args.output.rsplit(".", 1)[0] + "_ir.txt"
    with open(ir_filename, "w") as f:
        for node in ir_list:
            f.write(str(node) + "\n")
if debug_enabled["parse"]:
    debug_parse_filename = args.output.rsplit(".", 1)[0] + "_parse.txt"
    with open(debug_parse_filename, "w") as f:
        f.write(str(parse_tree.pretty()))

# Detailed mapping: for each IR node, show segment and offset where it was laid out/encoded.
# (mapping will be written after layout/encode where `addresses` and `segments` exist)


# Write AST to JSON
if debug_enabled["ast"]:
    filename_json = args.output.rsplit(".", 1)[0] + "_ast.json"
    with open(filename_json, "w") as f:
        json.dump(
            {"ir": ir_list, "lifted_constants": lifted_constants},
            f,
            indent=4,
            default=str,
        )

# Layout and encode
addresses, segments = layout_ir(ir_list)
debug_writers = collect_debug_segments(ir_list)
try:
    segments = encode_ir(ir_list, addresses, segments)
except Exception as e:
    print(f"Error during encoding: {e}")
    sys.exit(1)
if args.bin_version == 1:
    MAGIC = 0x50534F52  # 'ROSP' in little-endian
    VERSION = 1
    with open(args.output, "wb") as f:
        f.write(struct.pack("<III", MAGIC, VERSION, len(segments)))
        for addr, data in segments:
            f.write(struct.pack("<II", addr, len(data)))
            f.write(data)

if args.bin_version == 2:
    # Write the output file
    MAGIC = 0x50534F52  # 'ROSP' in little-endian
    VERSION = 2
    SEGMENT_FLAG_LOADABLE = 0x00000001
    SEGMENT_FLAG_DEBUG = 0x00000002
    print("final segments:", [(hex(addr), len(data)) for addr, data in segments])
    # Generate sidecar debug segments (Phase 2 collection output).
    debug_segments = []
    if args.segment_debug:
        for seg_addr, _seg_data in segments:
            writer = debug_writers.get(seg_addr, DebugInfoWriter())
            debug_text = writer.write_debug_segment(seg_addr)
            debug_segments.append((seg_addr, debug_text))

    with open(args.output, "wb") as f:
        total_segment_count = len(segments) + len(debug_segments)
        # Header
        f.write(struct.pack("<III", MAGIC, VERSION, total_segment_count))

        # Loadable segments
        for addr, data in segments:
            f.write(struct.pack("<III", SEGMENT_FLAG_LOADABLE, addr, len(data)))
            f.write(data)

        # Debug segments
        if args.segment_debug:
            for parent_addr, debug_text in debug_segments:
                debug_bytes = debug_text.encode("utf-8")
                f.write(
                    struct.pack(
                        "<III", SEGMENT_FLAG_DEBUG, parent_addr, len(debug_bytes)
                    )
                )
                f.write(debug_bytes)

    print(f"Wrote V2 binary to {args.output}")
    if debug_enabled["segments"] and debug_segments:
        debug_segments_filename = args.output.rsplit(".", 1)[0] + "_debug_segments.txt"
        with open(debug_segments_filename, "w", encoding="utf-8") as f:
            for seg_addr, debug_text in debug_segments:
                f.write(f"=== SEGMENT 0x{seg_addr:08X} ===\n")
                f.write(debug_text)
                f.write("\n")

        print(f"Wrote debug segment sidecar to {debug_segments_filename}")

# Now write a detailed mapping of IR nodes to addresses using resolved `addresses` and `segments`.

if debug_enabled["mapping"]:
    mapping_filename = args.output.rsplit(".", 1)[0] + "_mapping.txt"
    with open(mapping_filename, "w") as mf:
        mf.write("Node mapping:\n")
        cur_seg = None
        cur_cursor = 0
        for idx, node in enumerate(ir_list):
            if isinstance(node, Directive) and node.name == "seg":
                seg_addr = _imm_to_int(node.imm)
                if seg_addr is None:
                    seg_addr = 0
                cur_seg = seg_addr
                cur_cursor = 0
                mf.write(f"SEGMENT {hex(cur_seg)}\n")
                continue

            if cur_seg is None:
                cur_seg = 0

            if isinstance(node, LabelDecl):
                addr = addresses.get(node.name, cur_seg + cur_cursor)
                src = getattr(node, "src", None)
                src_str = (
                    f"{src.get('file')}:{src.get('line')}"
                    if isinstance(src, dict) and src.get("file")
                    else "<unknown>"
                )
                mf.write(f"LABEL {node.name} -> {hex(addr)} src={src_str}\n")
                try:
                    cur_cursor = addr - cur_seg
                except Exception:
                    cur_cursor = cur_cursor
                continue

            if isinstance(node, Directive) and node.name == "data":
                if node.length is not None:
                    size = int(node.length)
                else:
                    imm_int = _imm_to_int(node.imm)
                    if imm_int is not None:
                        size = (imm_int.bit_length() // 8) + 1
                    else:
                        size = 4
                size = max(4, size)
                src = getattr(node, "src", None)
                src_str = (
                    f"{src.get('file')}:{src.get('line')}"
                    if isinstance(src, dict) and src.get("file")
                    else "<unknown>"
                )
                mf.write(
                    f"DATA @ {hex(cur_seg + cur_cursor)} size {size}: {node.imm} src={src_str}\n"
                )
                cur_cursor += size
                continue

            if isinstance(node, IRInstruction):
                align = (4 - (cur_cursor % 4)) % 4
                if align:
                    cur_cursor += align
                # Print detailed info for each instruction
                legacy = getattr(node, "legacy", None)
                src = None
                if isinstance(legacy, dict):
                    src = legacy.get("src")
                src = src or getattr(node, "src", None)
                src_str = "<unknown>"
                if isinstance(src, dict) and src.get("file"):
                    src_str = f"{src.get('file')}:{src.get('line')}"
                assert hasattr(
                    node, "imm"
                ), "Instruction node should have imm attribute"
                for attr in ["rd", "rs1", "rs2"]:
                    if getattr(node, attr) is None:
                        setattr(node, attr, -1)
                    if getattr(node, attr) is not None and isinstance(
                        getattr(node, attr), ImmValue
                    ):
                        setattr(node, attr, _imm_to_int(getattr(node, attr)))
                if node.imm is None:
                    node.imm = None

                print(
                    f"Processing instruction idx={idx} name={node.name} rd={node.rd} rs1={node.rs1} rs2={node.rs2} imm={node.imm} src={src_str}"
                )
                assert (
                    src_str is not None
                ), "Source string should be determined for instruction"
                mf.write(
                    f"INSTR idx={idx:05d} @ {cur_seg + cur_cursor:08x} name={node.name} rd={getattr(node, 'rd', None)} rs1={getattr(node, 'rs1', None)} rs2={getattr(node, 'rs2', None)} imm={getattr(node, 'imm', None)} raw={node} src={src_str}\n"
                )
                cur_cursor += 4
                continue

            mf.write(f"UNKNOWN NODE {node}\n")
