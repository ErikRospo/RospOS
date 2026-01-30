import json
from lark import Lark, Transformer
from enum import Enum, auto

with open("./rospoas.lark", "r") as f:
    rospoas_grammar = f.read()
    
parser = Lark(rospoas_grammar, start="program", parser="lalr")

with open("./test.ros", "r") as f:
    source_code = f.read()
parse_tree = parser.parse(source_code)

opcode_type_map={
    "r": 0b0000,
    "i": 0b0001,
    "l": 0b0010,
    "b": 0b0011,
    "j": 0b0100,
    "s": 0b0101,
}
r_type_map={
    "add": 0b0000,
    "sub": 0b0001,
    "and": 0b0010,
    "or":  0b0011,
    "xor": 0b0100,
    "mul": 0b0101,
    "mulh": 0b0110,
    "neg": 0b0111,
    "not": 0b1000,
    "shl":0b1001,
    "shr":0b1010,
    "sar":0b1011,
    "div":0b1100,
    "divu":0b1101,
    "rem":0b1110,
    "remu":0b1111,
}
i_type_map={
    "addi": 0b0000,
    "andi": 0b0001,
    "ori":  0b0010,
    "xori": 0b0011,
    "shli": 0b0100,
    "shri": 0b0101,
    "sari": 0b0110,
}
l_type_map={
    "lb": 0b0000,
    "lbu": 0b0001,
    "lh": 0b0010,
    "lhu": 0b0011,
    "lw": 0b0100,
    "sb": 0b0101,
    "sh": 0b0110,
    "sw": 0b0111,
}
b_type_map={
    "beq": 0b0000,
    "bne": 0b0001,
    "blt": 0b0010,
    "bge": 0b0011,
    "bltu":0b0100,
    "bgeu":0b0101,
}
j_type_map={
    "jal": 0b0000,
    "jalr":0b0001,
}
s_type_map={
    "ecall": 0b0000,
    "break":0b0001,
}

instr_type_maps=[r_type_map, i_type_map, l_type_map, b_type_map, j_type_map, s_type_map]
register_map={
    "r"+str(i): i for i in range(16)
}
register_map["sp"]=15
register_map["lr"]=14
register_map["fp"]=13

class RospoasTransformer(Transformer):
    lifted_constants = {}
    def labeluse(self, items):
        name_t = items[0]
        return {"type": "u", "name": str(name_t)}

    def register(self, items):
        name_t = items[0]
        return register_map[str(name_t).lower()]
    
    def imm(self, items):
        value_t = items[0]
        value_v = value_t
        try:
            value_v = int(value_v, base=0)  # auto-detect base
        except:
            pass
        if isinstance(value_v, int):
            if not (-32768 <= value_v <= 65535):
                const_name = f"LCONST_{len(self.lifted_constants)}"
                self.lifted_constants[const_name] = value_v
                return const_name
        return value_v

    def instruction(self, items):
        return items[0]

    def rinstructuse(self, items):
        name_t, rd_t, rs1_t, rs2_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs1_v = rs1_t
        rs2_v = rs2_t
        
        return {"type": "r", "name": name_v, "rd": rd_v, "rs1": rs1_v, "rs2": rs2_v}       

    def iinstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs_v = rs_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "i", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}

    def lsinstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs_v = rs_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "l", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}

    def binstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs_v = rs_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "b", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}

    def jinstructuser(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs_v = rs_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "j", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}

    def jinstructusei(self, items):
        name_t, rd_t, imm_t = items
        name_v = name_t.data
        rd_v = rd_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "j", "name": name_v, "rd": rd_v, "rs1": 0, "imm": imm_v}

    def jmppseudo(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        return {"type": "j", "name": "jal", "rd": 0, "rs1": 0, "imm": imm_v}

    def systeminstructuse(self, items):
        name_t = items[0]
        name_v = name_t.data
        return {"type": "s", "name": name_v}

    def specialmarkeruse(self, items):
        marker_t = items[0]
        marker_v = marker_t.data
        if len(items) > 1:
            imm_t = items[1]
            imm_v = imm_t
            try:
                imm_v = int(imm_v)
            except:
                pass
            return {"type": "m", "name": marker_v, "imm": imm_v}
        else:
            return {"type": "m", "name": marker_v}

    def label(self, items):
        name_t = items[0]
        name_str = str(name_t)
        name_v = name_str[:-1]
        return {"type": "a", "name": name_v}
    def codeline(self,items):
        return items[0]
    def program(self, items):
        return items


    
transformer = RospoasTransformer()
ast = transformer.transform(parse_tree)
data = {
    "ast": ast,
    "lifted_constants": RospoasTransformer.lifted_constants
}
with open("./ast.json", "w") as f:
    json.dump(data, f, indent=4)

def translate_instruction(t_type, name, rd=None, rs1=None, rs2=None, imm=None):
    type_id = opcode_type_map[t_type]
    opcode = instr_type_maps[type_id][name]
    op_byte=type_id << 4 | opcode
    if type_id==0:
        assert rd is not None, "RD is required for R-type"
        assert rs1 is not None, "RS1 is required for R-type"
        assert rs2 is not None, "RS2 is required for R-type"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 4) | (rs2 & 0x0F)
    elif type_id in [1,2]:
        assert rd is not None, "RD is required for I/L-type"
        assert rs1 is not None, "RS is required for I/L-type"
        assert imm is not None, "IMM is required for I/L-type"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id==3:
        assert rd is not None, "RD is required for B-type"
        assert rs1 is not None, "RS is required for B-type"
        assert imm is not None, "IMM is required for B-type"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id==4:
        assert rd is not None, "RD is required for J-type"
        assert rs1 is not None, "RS is required for J-type"
        assert imm is not None, "IMM is required for J-type"
        op_byte = (op_byte << 4) | (rd & 0x0F)
        op_byte = (op_byte << 4) | (rs1 & 0x0F)  
        op_byte = (op_byte << 16) | (imm & 0xFFFF)
    elif type_id==5:
        assert imm is None, "IMM is not used for S-type"
        assert rd is None, "RD is not used for S-type"
        assert rs1 is None, "RS is not used for S-type"
        assert rs2 is None, "RS2 is not used for S-type"
        op_byte = (op_byte << 24)
    
    return op_byte

for instr in ast:
    if instr["type"] in ["r", "i", "l", "b", "j", "s"]:
        print(translate_instruction(instr["type"], instr["name"], rd=instr.get("rd", None), rs1=instr.get("rs1", None), rs2=instr.get("rs2", None), imm=instr.get("imm", None)))