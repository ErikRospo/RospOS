import re


class ExpressionTransformer:
    def __init__(self, ctx):
        self.ctx = ctx

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
                value = token[1:-1]
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
            if not children:
                return None

            return {
                "type": "binop",
                "op": children[1].get("node"),
                "left": self.from_node(children[0]),
                "right": self.from_node(children[2]),
            }

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
                elif first["node"] == "addr_of":
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
            has_inc = False
            has_dec = False
            member_accesses = []

            for child in children[1:]:
                if isinstance(child, dict) and "token" in child:
                    tok = child["token"]
                    if tok == "++":
                        has_inc = True
                    elif tok == "--":
                        has_dec = True
                elif isinstance(child, dict) and "node" in child:
                    if child["node"] == "member_access":
                        for member_child in child.get("children", []):
                            if isinstance(member_child, dict) and "token" in member_child:
                                member_accesses.append(
                                    {"op": ".", "member": member_child["token"]}
                                )
                                break
                    elif child["node"] == "ptr_member_access":
                        for member_child in child.get("children", []):
                            if isinstance(member_child, dict) and "token" in member_child:
                                member_accesses.append(
                                    {"op": "->", "member": member_child["token"]}
                                )
                                break

            for child in children[1:]:
                if isinstance(child, dict) and child.get("node") == "arg_list":
                    if (
                        isinstance(primary, dict)
                        and "token" in primary
                        and primary["token"].isidentifier()
                    ):
                        args = []
                        for arg in child.get("children", []):
                            if isinstance(arg, dict):
                                expr_value = self.from_node(arg)
                                if expr_value:
                                    args.append(expr_value)
                        return {"type": "call", "name": primary["token"], "args": args}

            if member_accesses:
                base_expr = self.from_node(primary)
                result = base_expr
                for access in member_accesses:
                    result = {
                        "type": "member_access",
                        "op": access["op"],
                        "base": result,
                        "member": access["member"],
                    }
                return result

            primary_expr = self.from_node(primary)
            if (
                (has_inc or has_dec)
                and primary_expr
                and primary_expr.get("type") == "var"
            ):
                pname = primary_expr.get("name")
                op = "+" if has_inc else "-"
                return {
                    "type": "assign",
                    "target": pname,
                    "value": {
                        "type": "binop",
                        "op": op,
                        "left": {"type": "var", "name": pname},
                        "right": {"type": "const", "value": 1},
                    },
                }
            return self.from_node(primary)

        for child in node.get("children", []):
            result = self.from_node(child)
            if result is not None:
                return result
        return None
