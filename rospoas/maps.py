opcode_type_map = {
    "r": 0b0000,
    "i": 0b0001,
    "l": 0b0010,
    "b": 0b0011,
    "j": 0b0100,
    "s": 0b0101,
}
r_type_map = {
    "add": 0b0000,
    "sub": 0b0001,
    "and": 0b0010,
    "or": 0b0011,
    "xor": 0b0100,
    "mul": 0b0101,
    "mulh": 0b0110,
    "neg": 0b0111,
    "not": 0b1000,
    "shl": 0b1001,
    "shr": 0b1010,
    "sar": 0b1011,
    "div": 0b1100,
    "divu": 0b1101,
    "rem": 0b1110,
    "remu": 0b1111,
}
i_type_map = {
    "addi": 0b0000,
    "andi": 0b0001,
    "ori": 0b0010,
    "xori": 0b0011,
    "shli": 0b0100,
    "shri": 0b0101,
    "sari": 0b0110,
}
i_to_r_map = {
    "addi": "add",
    "andi": "and",
    "ori": "or",
    "xori": "xor",
    "shli": "shl",
    "shri": "shr",
    "sari": "sar",
}
l_type_map = {
    "lb": 0b0000,
    "lbu": 0b0001,
    "lh": 0b0010,
    "lhu": 0b0011,
    "lw": 0b0100,
    "sb": 0b0101,
    "sh": 0b0110,
    "sw": 0b0111,
}
b_type_map = {
    "beq": 0b0000,
    "bne": 0b0001,
    "blt": 0b0010,
    "bge": 0b0011,
    "bltu": 0b0100,
    "bgeu": 0b0101,
}
j_type_map = {
    "jal": 0b0000,
    "jalr": 0b0001,
}
s_type_map = {
    "ecall": 0b0000,
    "break": 0b0001,
}

instr_type_maps = [
    r_type_map,
    i_type_map,
    l_type_map,
    b_type_map,
    j_type_map,
    s_type_map,
]
register_map = {"r" + str(i): i for i in range(16)}
register_map["sp"] = 15
register_map["lr"] = 14
register_map["fp"] = 13
