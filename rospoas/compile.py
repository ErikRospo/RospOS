import argparse
import json
import struct
from grammar_parser import parse_source, preprocess_includes
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


preprocessed_code = "\n".join(preprocess_includes(source_code, args.input))

# Parse and transform the preprocessed source code
parse_tree = parse_source(preprocessed_code)
ast, lifted_constants = transform_parse_tree(parse_tree)
debug_parse_filename = args.output.rsplit(".", 1)[0] + "_debug_parse.txt"
with open(debug_parse_filename, "w") as f:
    f.write(str(parse_tree.pretty()))
    f.write("\n\n")
    f.write(str(ast))
    f.write("\n\n")
    f.write(preprocessed_code)

# Write AST to JSON
filename_json = args.output.rsplit(".", 1)[0] + "_ast.json"
with open(filename_json, "w") as f:
    json.dump({"ast": ast, "lifted_constants": lifted_constants}, f, indent=4, default=str)

file = bytearray()

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
        op_byte = op_byte << 12 # Unused bits
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


def resolve_imm(imm, addresses, fallback_addresses=None):
    if isinstance(imm, dict):
        if "value" in imm:
            return imm["value"]
        elif "name" in imm:
            name = imm["name"]
            if name in addresses:
                return addresses[name]
            if fallback_addresses and name in fallback_addresses:
                return fallback_addresses[name]
            else:
                raise ValueError(f"Undefined label: {name}")
    return imm

def calculate_size(instr, addresses, fallback_addresses=None):
    t_type = instr["type"]
    name = instr["name"]
    if t_type == "d" and name == "data":
        return instr["len"]
    elif t_type == "p":
        imm = resolve_imm(instr["imm"], addresses, fallback_addresses)
        if name == "jmp":
            return len(generate_absolute_jump(imm, instr.get("rd", 0)))
        elif name == "lli":
            return len(generate_immediate_loading(imm, instr["reg"]))
        elif name == "push":
            return len(generate_stack_push(imm))
        elif name == "pop":
            return len(generate_stack_pop(imm))
    elif t_type in ["i", "l"]:
        imm = instr.get("imm")
        if imm is not None:
            imm = resolve_imm(imm, addresses, fallback_addresses)
            assert isinstance(imm, int), "Immediate value must be an integer at this point"
            if not (-32768 <= imm <= 65535):
                rd = instr["rd"]
                rs1 = instr["rs1"]
                if t_type == "l" and rs1 == 0:
                    # load from absolute address
                    return len(generate_immediate_loading(imm, rd)) + 4  # + lw
                elif t_type == "l":
                    # use temp reg
                    temp_reg = 1 if rd != 1 and rs1 != 1 else (2 if rd != 2 and rs1 != 2 else 3)
                    return len(generate_stack_push(temp_reg)) + len(generate_immediate_loading(imm, temp_reg)) + 4 + len(generate_stack_pop(temp_reg)) + 4  # push, imm, add, pop, lw
                else:  # i type
                    return len(generate_immediate_loading(imm, rd))
    return 4  # default 4 bytes


# Tentative pass: Assume all instructions are 4 bytes
def tentative_pass(ast):
    tentative_addresses = {}
    current_address = 0
    for instr in ast:
        if instr["type"] == "a":
            tentative_addresses[instr["name"]] = current_address
        elif instr["type"] == "d" and instr["name"] == "seg":
            segment_address = instr["imm"]
            if isinstance(segment_address, dict):
                segment_address = segment_address["value"]
            current_address = segment_address
        else:
            current_address += 4  # assume 4 bytes
    return tentative_addresses

# Actual pass: Calculate actual addresses accounting for expansions
def actual_pass(ast, tentative_addresses):
    # Iterate until addresses stabilize because some instruction sizes
    # (e.g. absolute jumps / large immediates) depend on final addresses.
    actual_addresses = {}
    while True:
        new_addresses = {}
        current_address = 0
        for instr in ast:
            if instr["type"] == "a":
                new_addresses[instr["name"]] = current_address
            elif instr["type"] == "d" and instr["name"] == "seg":
                segment_address = instr["imm"]
                if isinstance(segment_address, dict):
                    segment_address = segment_address["value"]
                current_address = segment_address
            else:
                size = calculate_size(instr, new_addresses, tentative_addresses)
                current_address += size

        if new_addresses == actual_addresses:
            return actual_addresses
        actual_addresses = new_addresses

def initialize_segments(ast):
    segments = []
    current_segment_data = None
    current_segment = None
    for instr in ast:
        if instr["type"] == "d" and instr["name"] == "seg":
            if current_segment_data is not None:
                segments.append((current_segment, current_segment_data))
            segment_address = instr["imm"]
            if isinstance(segment_address, dict):
                segment_address = segment_address["value"]
            current_segment_data = bytearray()
            current_segment = segment_address
    if current_segment_data is not None:
        segments.append((current_segment, current_segment_data))
    return segments


# Second pass: Compile instructions and write to segments
def second_pass(ast, actual_addresses, segments):
    current_segment = None
    current_segment_data = None
    def emit(b, note=""):
        if current_segment is None or current_segment_data is None:
            raise ValueError("Segment not initialized when emitting bytes")
        addr = current_segment + len(current_segment_data)
        current_segment_data.extend(b)
    for instr in ast:
        if instr["type"] == "d" and instr["name"] == "seg":
            # Handle .SEG directive
            segment_address = instr["imm"]
            if type(segment_address) == dict:
                segment_address = segment_address["value"]
            current_segment_data = next((data for addr, data in segments if addr == segment_address), None)
            current_segment = segment_address
        else:
            assert current_segment_data is not None, "Current segment data is not initialized. Ensure segments are properly set up before writing instructions."
            print("Compiling instruction at address", hex(len(current_segment_data)), ":", instr)
            if instr["type"] =="a":
                continue  # Skip label definitions
            if instr["type"] =="p":
                imm=instr["imm"]
                if isinstance(instr["imm"], dict):
                    label_value= instr["imm"].get("value")
                    if label_value is not None:
                        imm = label_value
                    else:
                        label_name = instr["imm"].get("name")
                        if label_name in actual_addresses:
                            imm = actual_addresses[label_name]
                        else:
                            raise ValueError(f"Undefined label: {label_name}")
                generated_instrs = None
                if instr["name"]=="jmp":
                    # If this pseudo has an rd (link register), ensure rd contains
                    # the address after the *entire* expansion so returns land
                    # at the correct place (not inside the expansion). We do
                    # this by loading that link address into rd, then performing
                    # the jump with rd=0 so the jalr doesn't overwrite it.
                    rd_arg = instr.get("rd", 0)
                    if rd_arg:
                        # base jump sequence with rd=0
                        jump_seq = generate_absolute_jump(imm, 0)
                        # compute prelude size (loading rd) iteratively until stable
                        assert current_segment is not None, "Current segment is None while computing link target"
                        prelude_size = 0
                        while True:
                            link_target = current_segment + len(current_segment_data) + prelude_size + len(jump_seq)
                            new_prelude = generate_immediate_loading(link_target, rd_arg)
                            new_size = len(new_prelude)
                            if new_size == prelude_size:
                                prelude = new_prelude
                                break
                            prelude_size = new_size
                        generated_instrs = prelude + jump_seq
                    else:
                        generated_instrs = generate_absolute_jump(imm, 0)
                elif instr["name"]=="lli":
                    generated_instrs = generate_immediate_loading(imm, instr["reg"])
                elif instr["name"]=="push":
                    generated_instrs = generate_stack_push(imm)
                elif instr["name"]=="pop":
                    generated_instrs = generate_stack_pop(imm)
                assert generated_instrs is not None, f"Unknown pseudo-instruction: {instr['name']}"

                if current_segment_data is not None:
                    emit(generated_instrs, f"pseudo:{instr['name']} imm={imm} rd={instr.get('rd')}")
                else:
                    raise ValueError("Segment data is not initialized. Ensure segments are properly set up before writing instructions.")

                continue
            if instr["type"]=="d" and instr["name"]=="data":
                data_value = instr["imm"]
                if isinstance(data_value, dict):
                    data_value = data_value["value"]
                print(instr)
                if isinstance(data_value, bytes):
                    data_bytes = data_value
                else:
                    data_bytes = data_value.to_bytes(instr["len"], byteorder="little", signed=True)
                if current_segment_data is not None:
                    emit(data_bytes, "data")
                else:
                    raise ValueError("Segment data is not initialized. Ensure segments are properly set up before writing instructions.")
                continue
            # Resolve all immediates to actual addresses/values
            if instr.get("imm") is not None and type(instr["imm"]) == dict:
                if "value" in instr["imm"]:
                    instr["imm"] = instr["imm"]["value"]
                elif "name" in instr["imm"]:
                    label_name = instr["imm"].get("name")
                    if label_name in actual_addresses:
                        assert current_segment is not None, "Current segment is None while resolving label addresses"
                        # Compute current PC for this instruction
                        pc = current_segment + len(current_segment_data)
                        # J-type and B-type instructions expect a PC-relative word offset
                        if instr.get("type") == "j" or instr.get("type") == "b":
                            instr["imm"] = (actual_addresses[label_name] - pc) // 4
                        else:
                            # For I/L-type (loads/immediates) and other instructions we need
                            # the absolute byte address so that immediate-loading sequences
                            # receive the full address value.
                            instr["imm"] = actual_addresses[label_name]
                    else:
                        raise ValueError(f"Undefined label: {label_name}. Current instruction: {instr}. Labels: {actual_addresses.keys()}")

            # Now, try to correct immediates if they don't fit
            if instr["type"] == "l" or instr["type"] == "i":
                imm = instr.get("imm")
                if -32768 <= imm <= 65535:
                    pass  # Fits in I-type
                else:
                    if instr["rs1"] == 0: # if loading with an offset of r0 (absolute load)
                        # Use immediate loading sequence to get the address into the destination register
                        # Because that's the only register that is guaranteed to be able to be clobbered safely
                        emit(generate_immediate_loading(imm, instr["rd"]), f"lli->rd={instr['rd']}")
                        # Then change
                        instr["imm"] = 0
                        instr["rs1"] = instr["rd"]
                        print(f"Rewrote load instruction to load from address in rd register due to large immediate ({imm})")
                        
                    else:
                        # If we are actually loading from an address + offset, we need to use a temp register to calculate the sum ourselves
                        # Find a temp register that is not used in this instruction
                        if instr["rd"] != 1 and instr["rs1"] != 1:
                            temp_reg = 1
                        elif instr["rd"] != 2 and instr["rs1"] != 2:
                            temp_reg = 2
                        else:
                            temp_reg = 3
                        print(f"Using temp register {temp_reg} to resolve large immediate ({imm}) for load instruction ({instr})")
                        # Push temp register
                        emit(generate_stack_push(temp_reg), f"push temp={temp_reg}") # 2 instructions
                        # Load full address into temp register
                        emit(generate_immediate_loading(imm, temp_reg), f"lli temp={temp_reg}") # 3 instructions
                        # Generate an ADD instruction to add base + offset into rs1
                        add_op_byte = opcode_type_map["r"] << 4 | instr_type_maps[opcode_type_map["r"]]["add"]
                        add_op_byte = (add_op_byte << 4) | (temp_reg & 0x0F)  # rd = temp_reg
                        add_op_byte = (add_op_byte << 4) | (instr["rs1"] & 0x0F)  # rs1 = original rs1
                        add_op_byte = (add_op_byte << 4) | (temp_reg & 0x0F)  # rs2 = temp_reg
                        emit(add_op_byte.to_bytes(4, byteorder="big"), f"add temp={temp_reg}") # 1 instruction
                        # Change rs1 to temp_reg
                        instr["rs1"] = temp_reg
                        instr["imm"] = 0

                        # Pop temp register
                        emit(generate_stack_pop(temp_reg), f"pop temp={temp_reg}") # 2 instructions

            print("Final instruction after immediate resolution:", instr)
            print("-"*40)
            # Write the instruction to the current segment data
            instr_bytes = compile_instruction(instr)
            emit(instr_bytes, f"instr:{instr['name']}")


# Perform the compilation
tentative_addresses = tentative_pass(ast)
actual_addresses = actual_pass(ast, tentative_addresses)
segments = initialize_segments(ast)
second_pass(ast, actual_addresses, segments)

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