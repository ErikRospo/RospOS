import argparse
import json
import struct
import sys
from pathlib import Path

from encode import encode_ir
from grammar_parser import parse_source, preprocess_includes
from ir import Directive, ImmValue
from ir import Instruction as IRInstruction
from ir import LabelDecl
from layout import layout_ir
from lower import lower_ir
from optimizer import optimize
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
args = parser.parse_args()
if args.output is None:
    args.output = args.input.rsplit(".", 1)[0] + ".rosp"  # ROS Program

# Read source code
with open(args.input, "r") as f:
    source_code = f.read()


pre_lines, origin_map = preprocess_includes(source_code, args.input)
preprocessed_code = "\n".join(pre_lines)
preprocessed_filename = args.output.rsplit(".", 1)[0] + "_preprocessed.ros"
with open(preprocessed_filename, "w") as f:
    f.write(preprocessed_code)
# Parse and transform the preprocessed source code
parse_tree = parse_source(preprocessed_code)
# Produce typed IR (from legacy AST) and lifted constants
ir_list, lifted_constants = transform_parse_tree_ir(parse_tree, origin_map=origin_map)

opt_ir_list = optimize(ir_list, outloc=Path(args.output).parent)
# Lower pseudo-instructions and lifted constants into concrete IR
ir_list = lower_ir(opt_ir_list)
debug_parse_filename = args.output.rsplit(".", 1)[0] + "_debug_parse.txt"
with open(debug_parse_filename, "w") as f:
    f.write(str(parse_tree.pretty()))
    f.write("\n\n")
    f.write(str(ir_list))
    f.write("\n\n")
    f.write(preprocessed_code)

# Detailed mapping: for each IR node, show segment and offset where it was laid out/encoded.
# (mapping will be written after layout/encode where `addresses` and `segments` exist)

# Write AST to JSON
filename_json = args.output.rsplit(".", 1)[0] + "_ast.json"
with open(filename_json, "w") as f:
    json.dump(
        {"ir": ir_list, "lifted_constants": lifted_constants}, f, indent=4, default=str
    )

# Layout and encode
addresses, segments = layout_ir(ir_list)
try:
    segments = encode_ir(ir_list, addresses, segments)
except Exception as e:
    print(f"Error during encoding: {e}")
    sys.exit(1)

# Write the output file
MAGIC = 0x50534F52  # 'ROSP' in little-endian
VERSION = 1
print("final segments:", [(hex(addr), len(data)) for addr, data in segments])
with open(args.output, "wb") as f:
    # Header
    f.write(struct.pack("<III", MAGIC, VERSION, len(segments)))

    # Segments
    for addr, data in segments:
        f.write(struct.pack("<II", addr, len(data)))
        f.write(data)

print(f"Wrote binary to {args.output}")

# Now write a detailed mapping of IR nodes to addresses using resolved `addresses` and `segments`.
mapping_filename = args.output.rsplit(".", 1)[0] + "_mapping.txt"


def _imm_to_int(imm):
    if imm is None:
        return None
    if hasattr(imm, "value"):
        try:
            return int(imm.value)
        except Exception:
            pass
    try:
        return int(imm)
    except Exception:
        return None


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
            assert hasattr(node, "imm"), "Instruction node should have imm attribute"
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
