import json
from lark import Lark, Transformer
with open("./rospoas.lark", "r") as f:
    rospoas_grammar=f.read()
    
parser = Lark(rospoas_grammar, start='program', parser='lalr')

with open("./test.ros","r") as f:
    source_code=f.read()
parse_tree = parser.parse(source_code)

opcode_type_map={
    "r": 0b0000,
    "i": 0b0001,
    "l": 0b0010,
    "s": 0b0011,
    "b": 0b0100,
    "j": 0b0101,
    "u": 0b0110,
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
class RospoasTransformer(Transformer):
    def labeluse(self, items):
        name_t = items[0]
        return {"type": "u", "name": str(name_t)}
    def register(self, items):
        name_t = items[0]
        return str(name_t)
    def imm(self, items):
        value_t = items[0]
        value_v = value_t
        try:
            value_v=int(value_v, base=0) # auto-detect base
        except:
            pass
        return value_v
    def rinstructuse(self, items):
        name_t, rd_t, rs1_t, rs2_t = items
        name_v=name_t.data
        rd_v=rd_t
        rs1_v=rs1_t
        rs2_v=rs2_t
        
        return {"type": "r", "name": name_v, "rd": rd_v, "rs1": rs1_v, "rs2": rs2_v}       
    def iinstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v=name_t.data
        rd_v=rd_t
        rs_v=rs_t
        imm_v=imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type": "i", "name": name_v, "rd": rd_v, "rs": rs_v, "imm": imm_v}
    def lsinstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v=name_t.data
        rd_v=rd_t
        rs_v=rs_t
        imm_v=imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type":"l", "name":name_v,"rd":rd_v,"rs":rs_v,"imm":imm_v}
    def binstructuse(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v=name_t.data
        rd_v=rd_t
        rs_v=rs_t
        imm_v=imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type":"b", "name":name_v,"rd":rd_v,"rs":rs_v,"imm":imm_v}
    def jinstructuser(self, items):
        name_t, rd_t, rs_t, imm_t = items
        name_v=name_t.data
        rd_v=rd_t
        rs_v=rs_t
        imm_v=imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type":"j", "name":name_v,"rd":rd_v,"rs":rs_v, "imm":imm_v}
    def jinstructusei(self,items):
        name_t, rd_t, imm_t = items
        name_v=name_t.data
        rd_v=rd_t
        imm_v=imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type":"j", "name":name_v,"rd":rd_v,"rs":"r0", "imm":imm_v}
    def jmppseudo(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v=int(imm_v)
        except:
            pass
        return {"type":"j", "name":"jal", "rd":"r0","rs":"r0", "imm":imm_v}
    def systeminstructuse(self, items):
        name_t = items[0]
        name_v = name_t.data
        return {"type":"s", "name":name_v}
    def specialmarkeruse(self, items):
        marker_t = items[0]
        marker_v = marker_t.data
        if len(items) > 1:
            imm_t = items[1]
            imm_v = imm_t
            try:
                imm_v=int(imm_v)
            except:
                pass
            return {"type":"m", "name":marker_v, "imm":imm_v}
        else:
            return {"type":"m", "name":marker_v}
    def label(self, items):
        name_t = items[0]
        name_str = str(name_t)
        name_v = name_str[:-1]
        return {"type":"a", "name":name_v}
    
transformer = RospoasTransformer()
ast = transformer.transform(parse_tree)
with open("ast.txt","w") as f:
    print(ast.pretty(), file=f)