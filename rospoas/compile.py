import argparse
import json
import struct
from grammar_parser import parse_source
from transformer import transform_parse_tree
from code_generator import generate_absolute_jump, generate_immediate_loading, generate_stack_push, generate_stack_pop
from maps import opcode_type_map, instr_type_maps

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

# Parse and transform source code
parse_tree = parse_source(source_code)
ast, lifted_constants = transform_parse_tree(parse_tree)

# Write AST to JSON
filename_json = args.output.rsplit(".", 1)[0] + "_ast.json"
with open(filename_json, "w") as f:
    json.dump({"ast": ast, "lifted_constants": lifted_constants}, f, indent=4)

file = bytearray()

label_addresses = {}
current_address = 0

current_segment = None
segments = []
current_segment_data = None

i_to_r_map = {
    "addi": "add",
    "andi": "and",
    "ori": "or",
    "xori": "xor",
    "shli": "shl",
    "shri": "shr",
    "sari": "sar",
}


# Update resolve_labels to ensure current_segment is always set

def resolve_labels(ast):
    global current_address, current_segment, current_segment_data
    seg = 0
    for instr in ast:
        if instr["type"] == "a":  # Label definition
            label_name = instr["name"]
            label_addresses[label_name] = current_address
        elif instr["type"] == "m" and instr["name"] == "seg":
            # Handle .SEG directive
            if current_segment_data is not None:
                segments.append((current_segment, current_segment_data))
            segment_address = instr["imm"]
            if type(segment_address) == dict:
                segment_address = segment_address["value"]
            print(f"Switching to segment at address {segment_address}")

            current_segment_data = bytearray()
            current_segment = segment_address
            current_address = segment_address
            seg += 1
        else:
            current_address += 4  # Each instruction is 4 bytes

    # Add the last segment to the list
    if current_segment_data is not None:
        segments.append((current_segment, current_segment_data))


# Function to compile an individual instruction into binary representation
def compile_instruction(instr):
    t_type = instr["type"]
    name = instr["name"]
    rd = instr.get("rd", None)
    rs1 = instr.get("rs1", None)
    rs2 = instr.get("rs2", None)
    imm = instr.get("imm", None)

    type_id = opcode_type_map[t_type]
    opcode = instr_type_maps[type_id][name]
    op_byte = type_id << 4 | opcode

    if type_id == 0:  # R-type
        assert rd is not None, "RD is required for R-type"
        assert rs1 is not None, "RS1 is required for R-type"
        assert rs2 is not None, "RS2 is required for R-type"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 4) | (rs2 & 0x0F)
    elif type_id in [1, 2]:  # I/L-type
        assert rd is not None, "RD is required for I/L-type"
        assert rs1 is not None, "RS is required for I/L-type"
        assert imm is not None, "IMM is required for I/L-type"
        assert isinstance(imm, int), f"IMM must be an integer for I/L-type, is {imm}"
        assert -32768 <= imm <= 65535, f"IMM out of range for I/L-type, is {imm}"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id == 3:  # B-type
        assert rd is not None, "RD is required for B-type"
        assert rs1 is not None, "RS is required for B-type"
        assert imm is not None, "IMM is required for B-type"
        assert isinstance(imm, int), f"IMM must be an integer for B-type, is {imm}"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id == 4:  # J-type
        assert rd is not None, "RD is required for J-type"
        assert rs1 is not None, "RS is required for J-type"
        assert imm is not None, "IMM is required for J-type"
        assert isinstance(imm, int), f"IMM must be an integer for J-type, is {imm}"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id == 5:  # S-type
        assert imm is None, "IMM is not used for S-type"
        assert rd is None, "RD is not used for S-type"
        assert rs1 is None, "RS is not used for S-type"
        assert rs2 is None, "RS2 is not used for S-type"
        op_byte = op_byte << 24

    return op_byte.to_bytes(4, byteorder="big")


# First pass: Resolve labels and segment addresses
def first_pass(ast):
    global current_address, current_segment, current_segment_data
    for instr in ast:
        if instr["type"] == "a":  # Label definition
            label_name = instr["name"]
            label_addresses[label_name] = current_address
        elif instr["type"] == "m" and instr["name"] == "seg":
            # Handle .SEG directive
            if current_segment_data is not None:
                segments.append((current_segment, current_segment_data))
            segment_address = instr["imm"]
            if type(segment_address) == dict:
                segment_address = segment_address["value"]
            print(f"Switching to segment at address {segment_address}")

            current_segment_data = bytearray()
            current_segment = segment_address
            current_address = segment_address
        else:
            current_address += 4  # Each instruction is 4 bytes

    # Add the last segment to the list
    if current_segment_data is not None:
        segments.append((current_segment, current_segment_data))


# Second pass: Compile instructions and write to segments
def second_pass(ast):
    global current_address, current_segment, current_segment_data
    for instr in ast:
        if instr["type"] == "m" and instr["name"] == "seg":
            # Handle .SEG directive
            segment_address = instr["imm"]
            if type(segment_address) == dict:
                segment_address = segment_address["value"]
            current_segment_data = next((data for addr, data in segments if addr == segment_address), None)
            current_segment = segment_address
            current_address = segment_address
        else:
            assert current_segment_data is not None, "Current segment data is not initialized. Ensure segments are properly set up before writing instructions."
            print("Compiling instruction at address", hex(current_address), ":", instr)
            if instr["type"] =="a":
                continue  # Skip label definitions
            if instr["type"] == "p" and instr["name"]=="jmp":
                imm=instr["imm"]
                if isinstance(instr["imm"], dict):
                    label_name = instr["imm"].get("name")
                    if label_name in label_addresses:
                        imm = label_addresses[label_name]
                    else:
                        raise ValueError(f"Undefined label: {label_name}")
                abs_jump_instr = generate_absolute_jump(imm)
                if current_segment_data is not None:
                    current_segment_data.extend(abs_jump_instr)
                else:
                    raise ValueError("Segment data is not initialized. Ensure segments are properly set up before writing instructions.")
                continue
            if instr["type"]=="m" and instr["name"]=="data":
                data_value = instr["imm"]
                if isinstance(data_value, dict):
                    data_value = data_value["value"]
                data_bytes = data_value.to_bytes(4, byteorder="little", signed=True)
                if current_segment_data is not None:
                    current_segment_data.extend(data_bytes)
                else:
                    raise ValueError("Segment data is not initialized. Ensure segments are properly set up before writing instructions.")
                current_address +=4
                continue
            # Resolve all immediates to actual addresses/values
            if instr.get("imm") is not None and type(instr["imm"]) == dict:
                if "value" in instr["imm"]:
                    instr["imm"] = instr["imm"]["value"]
                elif "name" in instr["imm"]:
                    label_name = instr["imm"].get("name")
                    if label_name in label_addresses:
                        instr["imm"] = (current_address-label_addresses[label_name])//4
                    else:
                        raise ValueError(f"Undefined label: {label_name}")
                    
            # Now, try to correct immediates if they don't fit
            if instr["type"] == "l":
                imm = instr.get("imm")
                if -32768 <= imm <= 65535:
                    pass  # Fits in I-type
                else:
                    if instr["rs1"] == 0: # if loading with an offset of r0 (absolute load)
                        # Use immediate loading sequence to get the address into the destination register
                        # Because that's the only register that is guaranteed to be able to be clobbered safely
                        current_segment_data.extend(generate_immediate_loading(imm, instr["rd"]))
                        # Then change
                        instr["imm"] = 0
                        instr["rs1"] = instr["rd"]
                        current_address+=12 # 3 instructions added
                    else:
                        # If we are actually loading from an address + offset, we need to use a temp register to calculate the sum ourselves
                        # Find a temp register that is not used in this instruction
                        if instr["rd"] != 1 and instr["rs1"] != 1:
                            temp_reg = 1
                        elif instr["rd"] != 2 and instr["rs1"] != 2:
                            temp_reg = 2
                        else:
                            temp_reg = 3
                        # Push temp register
                        current_segment_data.extend(generate_stack_push(temp_reg)) # 2 instructions
                        # Load full address into temp register
                        current_segment_data.extend(generate_immediate_loading(imm, temp_reg)) # 3 instructions
                        # Generate an ADD instruction to add base + offset into rs1
                        add_op_byte = opcode_type_map["r"] << 4 | instr_type_maps[opcode_type_map["r"]]["add"]
                        add_op_byte = (add_op_byte << 4) | (temp_reg & 0x0F)  # rd = temp_reg
                        add_op_byte = (add_op_byte << 4) | (instr["rs1"] & 0x0F)  # rs1 = original rs1
                        add_op_byte = (add_op_byte << 4) | (temp_reg & 0x0F)  # rs2 = temp_reg
                        current_segment_data.extend(add_op_byte.to_bytes(4, byteorder="big")) # 1 instruction
                        # Change rs1 to temp_reg
                        instr["rs1"] = temp_reg
                        instr["imm"] = 0
                        
                        # Pop temp register
                        current_segment_data.extend(generate_stack_pop(temp_reg)) # 2 instructions
                        current_address+=8*4 # 8 instructions added
                        
                        
            
            # Write the instruction to the current segment data
            current_segment_data.extend(compile_instruction(instr))

            current_address += 4  # Each instruction is 4 bytes


# Perform the two-pass compilation
first_pass(ast)
current_address = 0  # Reset for second pass
current_segment = None
current_segment_data = None
second_pass(ast)

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