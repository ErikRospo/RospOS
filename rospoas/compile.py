import argparse
import json
import struct
from grammar_parser import parse_source, preprocess_includes
from transformer import transform_parse_tree, transform_parse_tree_ir
from lower import lower_ir
from layout import layout_ir
from encode import encode_ir
from preprocessor import preprocess_ast
from code_generator import generate_absolute_jump, generate_immediate_loading, generate_stack_push, generate_stack_pop
from encoding import opcode_type_map, instr_type_maps, i_to_r_map, register_map

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Compile RospoAS source code.")
parser.add_argument("--input", type=str, required=True, help="Input source file to compile. Should be a .ros file")
parser.add_argument("--output", type=str, required=False, help="Output binary file. If not provided, will use the input filename with .rosp extension.")
args = parser.parse_args()
if args.output is None:
    args.output = args.input.rsplit(".", 1)[0] + ".rosp" #ROS Program

# Read source code
with open(args.input, "r") as f:
    source_code = f.read()


preprocessed_code = "\n".join(preprocess_includes(source_code, args.input))

# Parse and transform the preprocessed source code
parse_tree = parse_source(preprocessed_code)
# Produce typed IR (from legacy AST) and lifted constants
ir_list, lifted_constants = transform_parse_tree_ir(parse_tree)

# Lower pseudo-instructions and lifted constants into concrete IR
ir_list = lower_ir(ir_list)
debug_parse_filename = args.output.rsplit(".", 1)[0] + "_debug_parse.txt"
with open(debug_parse_filename, "w") as f:
    f.write(str(parse_tree.pretty()))
    f.write("\n\n")
    f.write(str(ir_list))
    f.write("\n\n")
    f.write(preprocessed_code)

# Write AST to JSON
filename_json = args.output.rsplit(".", 1)[0] + "_ast.json"
with open(filename_json, "w") as f:
    json.dump({"ir": ir_list, "lifted_constants": lifted_constants}, f, indent=4, default=str)

# Layout and encode
addresses, segments = layout_ir(ir_list)
segments = encode_ir(ir_list, addresses, segments)

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