import random

from lark import Transformer, v_args

from errors import TransformError, fmt_node
from ir import instr_list_from_legacy
from maps import register_map


class RospoasTransformer(Transformer):
    def __init__(self, origin_map=None):
        super().__init__()
        self.origin_map = origin_map or []
        self.lifted_constants = {}

    def _get_line_from_item(self, itm):
        try:
            if hasattr(itm, "line"):
                return getattr(itm, "line")
            if hasattr(itm, "meta") and hasattr(itm.meta, "line"):
                return itm.meta.line
        except Exception:
            return None
        return None

    def _src_from_items(self, items):
        # Find the first item with a line number and map it back to original file/line
        line_no = None
        for itm in items:
            ln = self._get_line_from_item(itm)
            if ln:
                line_no = ln
                break
        if line_no is None:
            return {"file": None, "line": None}
        # origin_map is a list indexed by preprocessed line (1-based)
        if 1 <= line_no <= len(self.origin_map):
            file, orig_line = self.origin_map[line_no - 1]
            return {"file": file, "line": orig_line, "pp_line": line_no}
        return {"file": "<preprocessed>", "line": line_no, "pp_line": line_no}

    def _attach_src(self, node: dict, items):
        try:
            node["src"] = self._src_from_items(items)
        except Exception:
            node["src"] = {"file": None, "line": None}
        return node

    def _src_from_meta(self, meta):
        try:
            if meta is None or not hasattr(meta, "line"):
                return {"file": None, "line": None}
            line_no = meta.line
            if 1 <= line_no <= len(self.origin_map):
                file, orig_line = self.origin_map[line_no - 1]
                return {"file": file, "line": orig_line, "pp_line": line_no}
            return {"file": "<preprocessed>", "line": line_no, "pp_line": line_no}
        except Exception:
            return {"file": None, "line": None}

    def _attach_src_meta(self, node: dict, meta):
        node["src"] = self._src_from_meta(meta)
        return node

    def labeluse(self, items):
        name_t = items[0]
        return self._attach_src({"type": "u", "name": str(name_t)}, items)

    def register(self, items):
        name_t = items[0]
        # registers are simple ints; attach no src
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
                return self._attach_src(
                    {"type": "li", "name": const_name, "value": value_v, "og": value_t},
                    items,
                )
        return value_v

    def instruction(self, items):
        # instruction node likely already has src attached by the concrete instruction rule
        return items[0]

    def rinstructuse(self, items):
        name_t, rd_t, rs1_t, rs2_t = items
        name_v = name_t.data
        rd_v = rd_t
        rs1_v = rs1_t
        rs2_v = rs2_t

        return self._attach_src(
            {"type": "r", "name": name_v, "rd": rd_v, "rs1": rs1_v, "rs2": rs2_v}, items
        )

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
        return self._attach_src(
            {"type": "i", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}, items
        )

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
        return self._attach_src(
            {"type": "l", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}, items
        )

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
        return self._attach_src(
            {"type": "b", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}, items
        )

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

        return self._attach_src(
            {"type": "j", "name": name_v, "rd": rd_v, "rs1": rs_v, "imm": imm_v}, items
        )

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

        return self._attach_src(
            {"type": "j", "name": name_v, "rd": rd_v, "rs1": 0, "imm": imm_v}, items
        )

    @v_args(meta=True)
    def jmpseudo(self, meta, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass

        return self._attach_src_meta(
            {"type": "p", "name": "jmp", "imm": imm_v}, meta
        )

    @v_args(meta=True)
    def push(self, meta, items):
        reg_t = items[0]
        reg_v = reg_t
        return self._attach_src_meta(
            {"type": "p", "name": "push", "imm": reg_v}, meta
        )

    @v_args(meta=True)
    def pop(self, meta, items):
        reg_t = items[0]
        reg_v = reg_t
        return self._attach_src_meta(
            {"type": "p", "name": "pop", "imm": reg_v}, meta
        )

    @v_args(meta=True)
    def movpseudo(self, meta, items):
        rd_t, rs_t = items
        rd_v = rd_t
        rs_v = rs_t
        return self._attach_src_meta(
            {"type": "r", "name": "add", "rd": rd_v, "rs1": rs_v, "rs2": 0}, meta
        )

    @v_args(meta=True)
    def zeropseudo(self, meta, items):
        rd_t = items[0]
        rd_v = rd_t
        return self._attach_src_meta(
            {"type": "r", "name": "add", "rd": rd_v, "rs1": 0, "rs2": 0}, meta
        )

    @v_args(meta=True)
    def notpseudo(self, meta, items):
        rd_t, rs_t = items
        rd_v = rd_t
        rs_v = rs_t
        return self._attach_src_meta(
            {"type": "r", "name": "xor", "rd": rd_v, "rs1": rs_v, "rs2": -1}, meta
        )

    @v_args(meta=True)
    def negpseudo(self, meta, items):
        rd_t, rs_t = items
        rd_v = rd_t
        rs_v = rs_t
        return self._attach_src_meta(
            {"type": "r", "name": "sub", "rd": rd_v, "rs1": 0, "rs2": rs_v}, meta
        )

    @v_args(meta=True)
    def lli(self, meta, items):
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
        return self._attach_src_meta(
            {"type": "p", "name": "lli", "reg": reg_v, "imm": imm_v}, meta
        )

    @v_args(meta=True)
    def callpseudo(self, meta, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass

        # Emit as a pseudo jump so the assembler can expand to an absolute-call
        # sequence that properly sets the link register (rd=14).
        return self._attach_src_meta(
            {"type": "p", "name": "jmp", "imm": imm_v, "rd": 14}, meta
        )

    @v_args(meta=True)
    def retpseudo(self, meta, items):
        return self._attach_src_meta(
            {"type": "j", "rd": 0, "rs1": 14, "name": "jalr", "imm": 0}, meta
        )

    @v_args(meta=True)
    def subipseudo(self, meta, items):
        rd_t, rs1_t, imm_t = items
        rd_v = rd_t
        rs1_v = rs1_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
        return self._attach_src_meta(
            {"type": "p", "name": "subi", "rd": rd_v, "rs1": rs1_v, "imm": imm_v}, meta
        )

    @v_args(meta=True)
    def muliipseudo(self, meta, items):
        rd_t, rs1_t, imm_t = items
        rd_v = rd_t
        rs1_v = rs1_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
        return self._attach_src_meta(
            {"type": "p", "name": "muli", "rd": rd_v, "rs1": rs1_v, "imm": imm_v}, meta
        )

    @v_args(meta=True)
    def divipseudo(self, meta, items):
        rd_t, rs1_t, imm_t = items
        rd_v = rd_t
        rs1_v = rs1_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
        return self._attach_src_meta(
            {"type": "p", "name": "divi", "rd": rd_v, "rs1": rs1_v, "imm": imm_v}, meta
        )

    @v_args(meta=True)
    def remipseudo(self, meta, items):
        rd_t, rs1_t, imm_t = items
        rd_v = rd_t
        rs1_v = rs1_t
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if isinstance(imm_v, dict) and imm_v.get("type") == "li":
            imm_v["rd"] = (
                rd_v  # Pass the destination register to the `li` pseudo-instruction
            )
        return self._attach_src_meta(
            {"type": "p", "name": "remi", "rd": rd_v, "rs1": rs1_v, "imm": imm_v}, meta
        )

    def systeminstructuse(self, items):
        name_t = items[0]
        name_v = name_t.data
        return self._attach_src({"type": "s", "name": name_v}, items)

    def seg(self, items):
        if items:
            imm_t = items[0]
            imm_v = imm_t
            try:
                imm_v = int(imm_v)
            except:
                pass
            return self._attach_src({"type": "d", "name": "seg", "imm": imm_v}, items)
        else:
            return self._attach_src({"type": "d", "name": "seg", "imm": None}, items)

    def data(self, items):
        if items:
            imm_t = items[0]
            imm_v = imm_t
            # Handle label uses (e.g. {'type':'u','name':'LABEL'}) as 4-byte references
            if isinstance(imm_v, dict) and imm_v.get("type") == "u":
                return {
                    "type": "d",
                    "name": "data",
                    "imm": {"name": imm_v.get("name")},
                    "d": "data",
                    "len": 4,
                }

            # Preserve bytes (string / rand) immediates
            if isinstance(imm_v, (bytes, bytearray)):
                return {
                    "type": "d",
                    "name": "data",
                    "imm": imm_v,
                    "d": "data",
                    "len": len(imm_v),
                }

            og_v = imm_v["og"] if isinstance(imm_v, dict) and "og" in imm_v else imm_v
            og_v = og_v.replace("_", "") if isinstance(og_v, str) else og_v

            # Determine length heuristically for numeric string forms
            if isinstance(og_v, str):
                if og_v.startswith("0x"):
                    length = (len(og_v) - 2) * 4
                elif og_v.startswith("0b"):
                    length = len(og_v) - 2
                else:
                    try:
                        length = (int(og_v).bit_length() + 7) // 8 * 8
                    except Exception:
                        length = 32
                length //= 8
            else:
                length = 4

            # Unwrap lifted-constant dicts produced by the parser
            if isinstance(imm_v, dict) and imm_v.get("type") == "li":
                imm_v = imm_v.get("value")

            try:
                imm_v = int(imm_v)
            except Exception:
                pass

            if not isinstance(imm_v, int):
                raise TransformError(
                    f"Data directive requires an integer immediate value or a label/bytes; got {fmt_node(imm_v)}"
                )

            return self._attach_src(
                {
                    "type": "d",
                    "name": "data",
                    "imm": imm_v,
                    "d": "data",
                    "len": length,
                },
                items,
            )
        else:
            return self._attach_src(
                {
                    "type": "d",
                    "name": "data",
                    "imm": 0,
                    "d": "data",
                    "len": 4,
                },
                items,
            )  # allocate 4 bytes by default

    def space(self, items):
        imm_t = items[0]
        imm_v = imm_t
        try:
            imm_v = int(imm_v)
        except:
            pass
        if not isinstance(imm_v, int):
            raise TransformError(
                f"SPACE directive requires an integer immediate value; got {fmt_node(imm_v)}"
            )
        return self._attach_src(
            {
                "type": "d",
                "name": "data",
                "imm": bytes(imm_v),
                "d": "space",
                "len": imm_v,
            },
            items,
        )

    def strv(self, items):
        str_t = items[0]
        str_v = str_t[1:-1]  # Remove the surrounding quotes
        value = str_v.encode().decode("unicode_escape")  # Handle escape sequences
        value_bytes = value.encode("utf-8") + b"\x00"  # Null-terminated
        return self._attach_src(
            {
                "type": "d",
                "name": "data",
                "imm": value_bytes,
                "d": "str",
                "len": len(value_bytes),
            },
            items,
        )

    def func(self, items):
        label_t = items[0]
        print(f"Defining function: {label_t}")
        # label_t is likely a dict from `label` rule
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
        return self._attach_src(
            {
                "type": "d",
                "name": "data",
                "imm": imm_v.to_bytes(imm_l, byteorder="little"),
                "d": "rand",
                "len": imm_l,
            },
            items,
        )

    def label(self, items):
        name_t = items[0]
        name_str = str(name_t)
        name_v = name_str[:-1]
        return self._attach_src({"type": "a", "name": name_v, "d": "label"}, items)

    def directiveuse(self, items):
        return items[0]

    def codeline(self, items):
        return items[0]

    def program(self, items):
        return items


def transform_parse_tree(parse_tree, origin_map=None):
    transformer = RospoasTransformer(origin_map=origin_map)
    return transformer.transform(parse_tree), transformer.lifted_constants


def transform_parse_tree_ir(parse_tree, origin_map=None):
    """Compatibility helper: transform parse tree and convert legacy dict AST
    into the typed IR defined in `rospoas/ir.py`.
    Returns: (ir_list, lifted_constants)
    """
    legacy_ast, lifted = transform_parse_tree(parse_tree, origin_map=origin_map)
    ir_list = instr_list_from_legacy(legacy_ast)
    return ir_list, lifted
