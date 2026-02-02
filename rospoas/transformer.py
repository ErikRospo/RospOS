import random

from lark import Transformer

from ir import instr_list_from_legacy
from maps import register_map


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
                return {"type": "li", "name": const_name, "value": value_v}
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
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
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
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
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
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
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
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )

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
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )

        return {"type": "j", "name": name_v, "rd": rd_v, "rs1": 0, "imm": imm_v}

    def jmpseudo(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass

        return {"type": "p", "name": "jmp", "imm": imm_v}

    def push(self, items):
        reg_t = items[0]
        reg_v = reg_t
        return {
            "type": "p",
            "name": "push",
            "imm": reg_v,
        }  # Yes, imm is register here for simplicity. Should really be "arg" or something

    def pop(self, items):
        reg_t = items[0]
        reg_v = reg_t
        return {"type": "p", "name": "pop", "imm": reg_v}  # Same as above

    def lli(self, items):
        reg_t = items[0]
        imm_t = items[1]
        reg_v = reg_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                reg_v  # Pass the destination register to the `li` pseudo-instruction
            )
        return {"type": "p", "name": "lli", "reg": reg_v, "imm": imm_v}

    def callpseudo(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass

        # Emit as a pseudo jump so the assembler can expand to an absolute-call
        # sequence that properly sets the link register (rd=14).
        return {"type": "p", "name": "jmp", "imm": imm_v, "rd": 14}

    def retpseudo(self, items):
        return {"type": "j", "rd": 0, "rs1": 14, "name": "jalr", "imm": 0}

    def systeminstructuse(self, items):
        name_t = items[0]
        name_v = name_t.data
        return {"type": "s", "name": name_v}

    def seg(self, items):
        if items:
            imm_t = items[0]
            imm_v = imm_t
            try:
                imm_v = int(imm_v)
            except:
                pass
            return {"type": "d", "name": "seg", "imm": imm_v}
        else:
            return {"type": "d", "name": "seg", "imm": None}

    def data(self, items):
        if items:
            imm_t = items[0]
            imm_v = imm_t
            try:
                imm_v = int(imm_v)
            except:
                pass
            if isinstance(imm_v, dict) and imm_v.get("type") == "li":
                imm_v = imm_v["value"]
            assert isinstance(
                imm_v, int
            ), "Data directive requires an integer immediate value"
            # Use at least 4 bytes for numeric data directives (word-sized)
            computed_len = int.bit_length(imm_v) // 8 + 1
            length = max(4, computed_len)
            return {
                "type": "d",
                "name": "data",
                "imm": imm_v,
                "d": "data",
                "len": length,
            }
        else:
            return {
                "type": "d",
                "name": "data",
                "imm": 0,
                "d": "data",
                "len": 4,
            }  # allocate 4 bytes by default

    def space(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        assert isinstance(
            imm_v, int
        ), "SPACE directive requires an integer immediate value"
        return {
            "type": "d",
            "name": "data",
            "imm": bytes(imm_v),
            "d": "space",
            "len": imm_v,
        }

    def strv(self, items):
        str_t = items[0]
        str_v = str_t[1:-1]  # Remove the surrounding quotes
        value = str_v.encode().decode("unicode_escape")  # Handle escape sequences
        value_bytes = value.encode("utf-8") + b"\x00"  # Null-terminated
        return {
            "type": "d",
            "name": "data",
            "imm": value_bytes,
            "d": "str",
            "len": len(value_bytes),
        }

    def func(self, items):
        label_t = items[0]
        print(f"Defining function: {label_t}")
        return label_t

    def rand(self, items):
        imm_t = items[0]
        imm_l = imm_t
        try:
            imm_l = int(imm_l)
        except:
            pass
        # This generates a random integer with the specified byte length
        # -1 bit to allow for negative values
        # Whether we interpret it as signed or unsigned is the user's responsibility
        # But the assembler assumes signed values for data directives
        imm_v = random.getrandbits(imm_l * 8)
        return {
            "type": "d",
            "name": "data",
            "imm": imm_v.to_bytes(imm_l, byteorder="little"),
            "d": "rand",
            "len": imm_l,
        }

    def label(self, items):
        name_t = items[0]
        name_str = str(name_t)
        name_v = name_str[:-1]
        return {"type": "a", "name": name_v, "d": "label"}

    def directiveuse(self, items):
        return items[0]

    def codeline(self, items):
        return items[0]

    def program(self, items):
        return items


def transform_parse_tree(parse_tree):
    transformer = RospoasTransformer()
    return transformer.transform(parse_tree), RospoasTransformer.lifted_constants


def transform_parse_tree_ir(parse_tree):
    """Compatibility helper: transform parse tree and convert legacy dict AST
    into the typed IR defined in `rospoas/ir.py`.
    Returns: (ir_list, lifted_constants)
    """
    legacy_ast, lifted = transform_parse_tree(parse_tree)
    ir_list = instr_list_from_legacy(legacy_ast)
    return ir_list, lifted
