import re

from transformer_utils import copy_line, find_identifier, find_number_in_node


class StatementTransformer:
    def __init__(self, ctx, expr_transformer):
        self.ctx = ctx
        self.expr = expr_transformer

    def process_decl_stmt(self, decl_node):
        """Process a declaration statement node."""
        name = None
        init = None
        decl_type = None

        for child in decl_node.get("children", []):
            if isinstance(child, dict) and child.get("node") == "type_specifier":
                for type_child in child.get("children", []):
                    if isinstance(type_child, dict):
                        if "node" in type_child:
                            decl_type = type_child["node"]
                        elif "token" in type_child and type_child["token"].isidentifier():
                            decl_type = type_child["token"]

        for child in decl_node.get("children", []):
            if isinstance(child, dict) and child.get("node") == "init_declarator_list":
                for init_decl in child.get("children", []):
                    if isinstance(init_decl, dict) and init_decl.get("node") == "init_declarator":
                        for part in init_decl.get("children", []):
                            if isinstance(part, dict) and part.get("node") == "declarator":
                                decl_children = part.get("children", [])
                                ident = find_identifier(part)
                                if ident:
                                    name = ident
                                for i, token_node in enumerate(decl_children):
                                    if (
                                        isinstance(token_node, dict)
                                        and "node" in token_node
                                        and token_node["node"] == "array"
                                    ):
                                        child_node = decl_children[i]
                                        assert child_node["node"] == "array"
                                        c_child = child_node.get("children", [])
                                        assert len(c_child) > 0
                                        if "int" in c_child[0]:
                                            array_len = int(c_child[0]["int"])
                                            init = {"type": "array", "size": array_len}
                                        elif "token" in c_child[0]:
                                            tok = c_child[0]["token"]
                                            if isinstance(tok, str) and re.fullmatch(
                                                r"-?\d+|0x[0-9a-fA-F]+", tok
                                            ):
                                                try:
                                                    array_len = int(tok, 0)
                                                except Exception:
                                                    array_len = int(tok)
                                                init = {
                                                    "type": "array",
                                                    "size": array_len,
                                                }
                                        break
                                if init is not None:
                                    break
                            if isinstance(part, dict) and part.get("node") is None:
                                if "int" in part:
                                    init = {"type": "const", "value": int(part["int"])}
                                elif "token" in part:
                                    tok = part.get("token")
                                    if isinstance(tok, str) and re.fullmatch(
                                        r"-?\d+|0x[0-9a-fA-F]+", tok
                                    ):
                                        try:
                                            init = {"type": "const", "value": int(tok, 0)}
                                        except Exception:
                                            init = {"type": "const", "value": int(tok)}
                            if (
                                isinstance(part, dict)
                                and "token" in part
                                and part["token"].startswith('"')
                            ):
                                val = part["token"][1:-1]
                                if len(val) == 1:
                                    init = {"type": "const", "value": ord(val)}
                                else:
                                    label = self.ctx.get_or_create_string_label(val)
                                    init = {"type": "string_addr", "label": label}
                            if isinstance(part, dict) and part.get("node"):
                                val = find_number_in_node(part)
                                if val is not None:
                                    init = {"type": "const", "value": val}

        if name:
            decl = copy_line(decl_node, {"type": "decl", "name": name, "init": init})
            if decl_type:
                decl["decl_type"] = decl_type
            return [decl]
        return []

    def process_stmt_node(self, stmt_node):
        """Process a single statement node (compound or simple)."""
        if not isinstance(stmt_node, dict):
            return []

        node_type = stmt_node.get("node")

        if node_type == "compound_stmt":
            return self.compound_to_stmts(stmt_node)

        if node_type == "expr_stmt":
            expr = None
            for child in stmt_node.get("children", []):
                if isinstance(child, dict):
                    expr = self.expr.from_node(child)
                    break
            if expr:
                if expr.get("type") == "call":
                    return [
                        copy_line(
                            stmt_node,
                            {
                                "type": "call_stmt",
                                "name": expr.get("name"),
                                "args": expr.get("args", []),
                            },
                        )
                    ]
                if expr.get("type") == "assign":
                    return [
                        copy_line(
                            stmt_node,
                            {
                                "type": "assign",
                                "target": expr.get("target"),
                                "value": expr.get("value"),
                            },
                        )
                    ]
            return []

        if node_type == "declaration":
            return self.process_decl_stmt(stmt_node)

        if node_type == "return_stmt":
            expr = None
            for child in stmt_node.get("children", []):
                if isinstance(child, dict):
                    expr = self.expr.from_node(child)
                    break
            return [copy_line(stmt_node, {"type": "return", "value": expr})]

        return []

    @staticmethod
    def _find_name_in_node(node):
        if isinstance(node, dict):
            if (
                "token" in node
                and isinstance(node["token"], str)
                and node["token"].isidentifier()
            ):
                return node["token"]
            for child in node.get("children", []):
                result = StatementTransformer._find_name_in_node(child)
                if result is not None:
                    return result
        return None

    def compound_to_stmts(self, comp_node):
        stmts = []
        for child in comp_node.get("children", []):
            if not isinstance(child, dict):
                continue
            node_type = child.get("node")

            if node_type == "while_stmt":
                children = child.get("children", [])
                cond = None
                body_node = None
                for ch in children:
                    if isinstance(ch, dict) and "token" in ch:
                        if cond is None:
                            candidate = self.expr.from_node(ch)
                            if candidate is not None:
                                cond = candidate
                                continue
                    if (
                        isinstance(ch, dict)
                        and ch.get("node")
                        and ch.get("node") not in ("(", ")")
                    ):
                        if cond is None and ch.get("node") not in (
                            "statement",
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            cond = self.expr.from_node(ch)
                        elif cond is None and ch.get("node") in (
                            "expr",
                            "assignment",
                            "conditional",
                            "logic_or",
                            "additive",
                            "multiplicative",
                            "postfix",
                            "primary",
                            "unary",
                        ):
                            cond = self.expr.from_node(ch)
                        elif body_node is None and ch.get("node") in (
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            body_node = ch
                if cond is None and len(children) >= 3 and isinstance(children[2], dict):
                    cond = self.expr.from_node(children[2])
                if body_node is None and children:
                    body_node = children[-1]

                body_stmts = self.process_stmt_node(body_node) if body_node else []
                stmts.append(copy_line(child, {"type": "while", "cond": cond, "body": body_stmts}))
                continue

            if node_type == "if_stmt":
                children = child.get("children", [])
                cond = None
                then_node = None
                else_node = None
                for ch in children:
                    if isinstance(ch, dict) and "token" in ch:
                        if cond is None:
                            candidate = self.expr.from_node(ch)
                            if candidate is not None:
                                cond = candidate
                                continue
                    if (
                        isinstance(ch, dict)
                        and ch.get("node")
                        and ch.get("node") not in ("(", ")")
                    ):
                        if cond is None and ch.get("node") in (
                            "expr",
                            "assignment",
                            "conditional",
                            "logic_or",
                            "additive",
                            "multiplicative",
                            "postfix",
                            "primary",
                            "unary",
                        ):
                            cond = self.expr.from_node(ch)
                        elif then_node is None and ch.get("node") in (
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            then_node = ch
                        elif (
                            ch.get("node")
                            in (
                                "compound_stmt",
                                "expr_stmt",
                                "declaration",
                                "return_stmt",
                            )
                            and then_node is not None
                            and else_node is None
                        ):
                            else_node = ch
                if cond is None and len(children) >= 3 and isinstance(children[2], dict):
                    cond = self.expr.from_node(children[2])

                if cond is None:
                    name_found = self._find_name_in_node(child)
                    if name_found is not None:
                        cond = {"type": "var", "name": name_found}
                    else:
                        cond = {"type": "const", "value": 1}
                if then_node is None:
                    for ch in children:
                        if isinstance(ch, dict) and ch.get("node") in (
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            then_node = ch
                            break
                if else_node is None:
                    for i, ch in enumerate(children):
                        if isinstance(ch, dict) and "token" in ch and ch["token"] == "else":
                            if i + 1 < len(children) and isinstance(children[i + 1], dict):
                                else_node = children[i + 1]
                                break

                then_stmts = self.process_stmt_node(then_node) if then_node else []
                else_stmts = self.process_stmt_node(else_node) if else_node else []

                stmts.append(
                    copy_line(
                        child,
                        {
                            "type": "if",
                            "cond": cond,
                            "then": then_stmts,
                            "else": else_stmts,
                        },
                    )
                )
                continue

            stmts.extend(self.process_stmt_node(child))
        return stmts
