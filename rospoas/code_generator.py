from maps import *


def generate_immediate_loading(value, rd):
    file = bytearray()

    # Break the constant into high and low parts
    high = (value >> 16) & 0xFFFF
    low = value & 0xFFFF
    if high != 0:
        # Generate ADDI to load the high part, then shift and OR the low part.
        op_byte = opcode_type_map["i"] << 4 | i_type_map["addi"]
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (0 & 0x0F)  # rs1 = 0
        op_byte = (op_byte << 16) | (high & 0xFFFF)
        file += op_byte.to_bytes(4, byteorder="big")

        # Shift high part into place
        op_byte = opcode_type_map["i"] << 4 | i_type_map["shli"]
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rd & 0x0F)  # rs1 = rd
        op_byte = (op_byte << 16) | 16  # Shift by 16 bits
        file += op_byte.to_bytes(4, byteorder="big")
        if low != 0:
            # ORI to add the low part
            op_byte = opcode_type_map["i"] << 4 | i_type_map["ori"]
            op_byte = (op_byte << 4) | (rd & 0x0F)
            op_byte = (op_byte << 4) | (rd & 0x0F)  # rs1 = rd
            op_byte = (op_byte << 16) | (low & 0xFFFF)
            file += op_byte.to_bytes(4, byteorder="big")
    else:
        # Only low part
        if low != 0:
            op_byte = opcode_type_map["i"] << 4 | i_type_map["addi"]
            op_byte = (op_byte << 4) | (rd & 0x0F)
            op_byte = (op_byte << 4) | (0 & 0x0F)  # rs1 = 0
            op_byte = (op_byte << 16) | (low & 0xFFFF)
            file += op_byte.to_bytes(4, byteorder="big")
    return file


def generate_stack_push(rs):
    file = bytearray()
    # Generate SW instruction to store register to stack
    op_byte = opcode_type_map["s"] << 4 | l_type_map["sw"]
    op_byte = (op_byte << 4) | (rs & 0x0F)  # data=rs
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rs1 = sp
    op_byte = (op_byte << 16) | (-4 & 0xFFFF)  # offset -4
    file += op_byte.to_bytes(4, byteorder="big")

    # Generate ADDI to decrement stack pointer
    op_byte = opcode_type_map["i"] << 4 | i_type_map["addi"]
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rd = sp
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rs1 = sp
    op_byte = (op_byte << 16) | (-4 & 0xFFFF)  # immediate -4
    file += op_byte.to_bytes(4, byteorder="big")
    return file


def generate_stack_pop(rd):
    file = bytearray()
    # Generate ADDI to increment stack pointer
    op_byte = opcode_type_map["i"] << 4 | i_type_map["addi"]
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rd = sp
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rs1 = sp
    op_byte = (op_byte << 16) | (4 & 0xFFFF)  # immediate +4
    file += op_byte.to_bytes(4, byteorder="big")

    # Generate LW instruction to pop register from stack
    op_byte = opcode_type_map["l"] << 4 | l_type_map["lw"]
    op_byte = (op_byte << 4) | (rd & 0x0F)  # rd = rd
    op_byte = (op_byte << 4) | (register_map["sp"] & 0x0F)  # rs1 = sp
    op_byte = (op_byte << 16) | (0 & 0xFFFF)  # offset 0
    file += op_byte.to_bytes(4, byteorder="big")
    return file


def generate_absolute_jump(address, rd=0):
    file = bytearray()

    # If address doesn't fit in 16 bits, load it into a temp register and use JALR
    if address > 0xFFFF:
        file += generate_stack_push(register_map["r1"])
        # Load full address into a register first
        file += generate_immediate_loading(address, register_map["r1"])
        # Generate JALR instruction to jump to address in r1
        op_byte = opcode_type_map["j"] << 4 | j_type_map["jalr"]
        op_byte = (op_byte << 4) | (rd & 0x0F)  # rd (link register)
        op_byte = (op_byte << 4) | (register_map["r1"] & 0x0F)  # rs1 = r1
        op_byte = (op_byte << 16) | 0  # immediate 0
        file += op_byte.to_bytes(4, byteorder="big")
        file += generate_stack_pop(register_map["r1"])
        return file

    # For small absolute addresses, encode the immediate as a word address
    # so that JALR's runtime shift left by 2 yields the correct byte address.
    word_addr = (address >> 2) & 0xFFFF
    op_byte = opcode_type_map["j"] << 4 | j_type_map["jalr"]
    op_byte = (op_byte << 4) | (rd & 0x0F)  # rd (link register)
    op_byte = (op_byte << 4) | 0  # rs1 = r0
    op_byte = (op_byte << 16) | word_addr  # immediate = address / 4
    file += op_byte.to_bytes(4, byteorder="big")
    return file
