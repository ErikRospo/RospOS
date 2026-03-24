import re

from transformer_utils import decode_string_token


class ExpressionTransformer:
    def __init__(self, ctx):
        self.ctx = ctx

    def _fold_left_binops(self, children):
        if not children:
            return None

        left = self.from_node(children[0])
        i = 1
        while i + 1 < len(children):
            op_node = children[i]
            right_node = children[i + 1]
            if not isinstance(op_node, dict):
                i += 1
                continue
            op_name = op_node.get("node")
            right = self.from_node(right_node)
            if op_name is None or left is None or right is None:
                i += 2
                continue
            left = {
                "type": "binop",
                "op": op_name,
                "left": left,
                "right": right,
            }
            i += 2

        return left

    def from_node(self, node):
        if not isinstance(node, dict):
            return None
        if "token" in node:
            token = node["token"]
            if "int" in node:
                return {"type": "const", "value": int(node["int"])}
            if re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", token):
                try:
                    return {"type": "const", "value": int(token, 0)}
                except Exception:
                    return {"type": "const", "value": int(token)}
            if token.startswith('"') and token.endswith('"'):
                value = decode_string_token(token)
                if len(value) == 1:
                    return {"type": "const", "value": ord(value)}
                label = self.ctx.get_or_create_string_label(value)
                return {"type": "string_addr", "label": label}
            if token.isidentifier():
                return {"type": "var", "name": token}
            return None

        node_type = node.get("node")
        if node_type in (
            "additive",
            "multiplicative",
            "relational",
            "equality",
            "shift",
        ):
            children = node.get("children", [])
            return self._fold_left_binops(children)

        if node_type == "assignment":
            children = node.get("children", [])
            print("assignment children:", children)
            if len(children) == 2:
                left = self.from_node(children[0])
                right = self.from_node(children[1])
                print(left, right)
                if left:
                    if left.get("type") == "var":
                        return {
                            "type": "assign",
                            "target": left.get("name"),
                            "value": right,
                        }
                    if left.get("type") in ("member_access", "deref"):
                        return {
                            "type": "assign",
                            "target": left,
                            "value": right,
                        }
            return None

        if node_type == "unary":
            children = node.get("children", [])
            print("unary children:", children)
            if not children:
                return None
            first = children[0]
            if isinstance(first, dict) and "node" in first and len(children) > 1:
                if first["node"] == "deref":
                    inner = self.from_node(children[1])
                    if inner:
                        return {"type": "deref", "expr": inner}
                elif first["node"] in ("addr_of", "addrof"):
                    inner = self.from_node(children[1])
                    if inner:
                        return {"type": "addr_of", "expr": inner}
                elif first["node"] == "uminus":
                    inner = self.from_node(children[1])
                    if inner:
                        return {
                            "type": "binop",
                            "op": "minus",
                            "left": {"type": "const", "value": 0},
                            "right": inner,
                        }
                elif first["node"] == "uplus":
                    inner = self.from_node(children[1])
                    if inner:
                        return {
                            "type": "binop",
                            "op": "plus",
                            "left": {"type": "const", "value": 0},
                            "right": inner,
                        }
                elif first["node"] == "not":
                    inner = self.from_node(children[1])
                    if inner:
                        return {"type": "unop", "op": "not", "operand": inner}
                elif first["node"] == "bitnot":
                    inner = self.from_node(children[1])
                    if inner:
                        return {
                            "type": "binop",
                            "op": "xor",
                            "left": {"type": "const", "value": 0xFFFF_FFFF},
                            "right": inner,
                        }

            return self.from_node(children[-1])

        if node_type == "postfix":
            children = node.get("children", [])
            if not children:
                return None
            primary = children[0]
            result = self.from_node(primary)

            for child in children[1:]:
                if not isinstance(child, dict):
                    continue

                suffix_type = child.get("node")
                if suffix_type == "call_suffix":
                    if (
                        isinstance(primary, dict)
                        and "token" in primary
                        and primary["token"].isidentifier()
                    ):
                        args = []
                        arg_list = None
                        for suffix_child in child.get("children", []):
                            if isinstance(suffix_child, dict) and suffix_child.get("node") == "arg_list":
                                arg_list = suffix_child
                                break
                        if arg_list is not None:
                            for arg in arg_list.get("children", []):
                                if isinstance(arg, dict):
                                    expr_value = self.from_node(arg)
                                    if expr_value:
                                        args.append(expr_value)
                        return {"type": "call", "name": primary["token"], "args": args}
                    continue

                if suffix_type == "member_access":
                    member_name = None
                    for member_child in child.get("children", []):
                        if isinstance(member_child, dict) and "token" in member_child:
                            member_name = member_child["token"]
                            break
                    if member_name and result is not None:
                        result = {
                            "type": "member_access",
                            "op": ".",
                            "base": result,
                            "member": member_name,
                        }
                    continue

                if suffix_type == "ptr_member_access":
                    member_name = None
                    for member_child in child.get("children", []):
                        if isinstance(member_child, dict) and "token" in member_child:
                            member_name = member_child["token"]
                            break
                    if member_name and result is not None:
                        result = {
                            "type": "member_access",
                            "op": "->",
                            "base": result,
                            "member": member_name,
                        }
                    continue

                if suffix_type == "array_index":
                    index_expr = None
                    for idx_child in child.get("children", []):
                        if isinstance(idx_child, dict):
                            index_expr = self.from_node(idx_child)
                            if index_expr is not None:
                                break
                    if result is not None and index_expr is not None:
                        result = {
                            "type": "deref",
                            "expr": {
                                "type": "binop",
                                "op": "plus",
                                "left": result,
                                "right": index_expr,
                            },
                        }
                    continue

                if suffix_type in ("post_inc", "post_dec"):
                    if result and result.get("type") == "var":
                        pname = result.get("name")
                        return {
                            "type": "assign",
                            "target": pname,
                            "value": {
                                "type": "binop",
                                "op": "plus" if suffix_type == "post_inc" else "minus",
                                "left": {"type": "var", "name": pname},
                                "right": {"type": "const", "value": 1},
                            },
                        }

            return result

        for child in node.get("children", []):
            result = self.from_node(child)
            if result is not None:
                return result
        return None
