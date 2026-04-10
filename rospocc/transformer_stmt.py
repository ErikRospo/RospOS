import re

from transformer_utils import (
    copy_line,
    decode_string_token,
    find_identifier,
    node_name,
)


class StatementTransformer:
    def __init__(self, ctx, expr_transformer):
        self.ctx = ctx
        self.expr = expr_transformer

    def process_decl_stmt(self, decl_node):
        """Process a declaration statement node."""
        name = None
        init = None
        decl_type = None
        type_pointer_count = 0
        decl_pointer_count = 0

        def _parse_type_specifier(type_node):
            base_type = None
            pointer_count = 0
            if not isinstance(type_node, dict):
                return base_type, pointer_count

            for type_child in type_node.get("children", []):
                if not isinstance(type_child, dict):
                    continue
                if "node" in type_child:
                    node_val = node_name(type_child.get("node"))
                    if node_val == "pointer":
                        pointer_count = pointer_count + 1
                    elif isinstance(node_val, str) and node_val != "struct_type":
                        base_type = node_val
                elif "token" in type_child and type_child["token"].isidentifier():
                    base_type = type_child["token"]

            return base_type, pointer_count

        def _count_declarator_pointers(declarator_node):
            count = 0
            if not isinstance(declarator_node, dict):
                return count

            for child in declarator_node.get("children", []):
                if not isinstance(child, dict):
                    continue
                if node_name(child.get("node")) == "pointer":
                    count = count + 1
                elif child.get("node") == "declarator":
                    count = count + _count_declarator_pointers(child)
            return count

        def _resolved_type(base_type, pointer_count, is_array=False):
            if is_array:
                if base_type == "char":
                    return "char_ptr"
                if base_type == "int":
                    return "int_ptr"
                return f"{base_type}_ptr" if base_type else "int_ptr"
            if pointer_count > 0:
                if base_type == "char":
                    return "char_ptr"
                if base_type == "int":
                    return "int_ptr"
                return f"{base_type}_ptr" if base_type else "int_ptr"
            return base_type or "int"

        for child in decl_node.get("children", []):
            if isinstance(child, dict) and child.get("node") == "type_specifier":
                decl_type, type_pointer_count = _parse_type_specifier(child)

        for child in decl_node.get("children", []):
            if isinstance(child, dict) and child.get("node") == "init_declarator_list":
                for init_decl in child.get("children", []):
                    if (
                        isinstance(init_decl, dict)
                        and init_decl.get("node") == "init_declarator"
                    ):
                        for part in init_decl.get("children", []):
                            if (
                                isinstance(part, dict)
                                and part.get("node") == "declarator"
                            ):
                                decl_children = part.get("children", [])
                                ident = find_identifier(part)
                                if ident:
                                    name = ident
                                decl_pointer_count = _count_declarator_pointers(part)
                                array_len = None
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
                                        elif "token" in c_child[0]:
                                            tok = c_child[0]["token"]
                                            if isinstance(tok, str) and re.fullmatch(
                                                r"-?\d+|0x[0-9a-fA-F]+", tok
                                            ):
                                                try:
                                                    array_len = int(tok, 0)
                                                except Exception:
                                                    array_len = int(tok)
                                        if array_len is not None:
                                            init = {
                                                "type": "array",
                                                "size": array_len,
                                            }
                                        break

                                # Keep scanning init_declarator parts to allow
                                # array initializers like: char buf[32] = "...";
                                continue
                            if isinstance(part, dict) and part.get("node") is None:
                                if "int" in part:
                                    init = {"type": "const", "value": int(part["int"])}
                                elif "token" in part:
                                    tok = part.get("token")
                                    if isinstance(tok, str) and re.fullmatch(
                                        r"-?\d+|0x[0-9a-fA-F]+", tok
                                    ):
                                        try:
                                            init = {
                                                "type": "const",
                                                "value": int(tok, 0),
                                            }
                                        except Exception:
                                            init = {"type": "const", "value": int(tok)}
                            if (
                                isinstance(part, dict)
                                and "token" in part
                                and part["token"].startswith('"')
                            ):
                                val = decode_string_token(part["token"])
                                if init and init.get("type") == "array":
                                    init = {
                                        "type": "array_init_string",
                                        "size": int(init.get("size", 0)),
                                        "value": val,
                                    }
                                elif len(val) == 1:
                                    init = {"type": "const", "value": ord(val)}
                                else:
                                    label = self.ctx.get_or_create_string_label(val)
                                    init = {"type": "string_addr", "label": label}
                            if isinstance(part, dict) and part.get("node"):
                                expr_init = self.expr.from_node(part)
                                if expr_init is not None:
                                    init = expr_init

        if name:
            if decl_type == "return":
                ret_value = init
                if ret_value is None:
                    ret_value = {"type": "var", "name": name}
                return [copy_line(decl_node, {"type": "return", "value": ret_value})]

            decl = copy_line(decl_node, {"type": "decl", "name": name, "init": init})
            if decl_type:
                total_pointer_count = type_pointer_count + decl_pointer_count
                decl["decl_type"] = _resolved_type(
                    decl_type, total_pointer_count, is_array=(init and init.get("type") == "array")
                )
            return [decl]
        return []

    @staticmethod
    def _is_stmt_node(node):
        return isinstance(node, dict) and node.get("node") in (
            "compound_stmt",
            "expr_stmt",
            "declaration",
            "return_stmt",
            "if_stmt",
            "while_stmt",
            "for_stmt",
        )

    @staticmethod
    def _is_expr_node(node):
        if not isinstance(node, dict):
            return False
        n = node.get("node")
        return n in {
            "expr",
            "assignment",
            "conditional",
            "logic_or",
            "logic_and",
            "bit_or",
            "bit_xor",
            "bit_and",
            "equality",
            "relational",
            "shift",
            "additive",
            "multiplicative",
            "postfix",
            "primary",
            "unary",
            "call_suffix",
            "array_index",
            "member_access",
            "ptr_member_access",
            "post_inc",
            "post_dec",
        } or ("token" in node)

    def _expr_to_stmt(self, expr_node, src_node):
        expr = self.expr.from_node(expr_node)
        if not expr:
            return None
        if expr.get("type") == "assign":
            return copy_line(
                src_node,
                {
                    "type": "assign",
                    "target": expr.get("target"),
                    "value": expr.get("value"),
                },
            )
        if expr.get("type") == "call":
            return copy_line(
                src_node,
                {
                    "type": "call_stmt",
                    "name": expr.get("name"),
                    "args": expr.get("args", []),
                },
            )
        return None

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
                # Some parse trees represent `return(expr);` as a call to
                # an identifier named `return`. Recover it into a return stmt.
                if expr.get("type") == "call" and expr.get("name") == "return":
                    args = expr.get("args", []) or []
                    ret_value = args[0] if args else None
                    return [
                        copy_line(stmt_node, {"type": "return", "value": ret_value})
                    ]
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
                    candidate = self.expr.from_node(child)
                    if candidate is not None:
                        expr = candidate
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

    def _extract_condition_and_body(self, children):
        cond = None
        body_node = None

        for ch in children:
            if not isinstance(ch, dict):
                continue
            if cond is None and self._is_expr_node(ch):
                candidate = self.expr.from_node(ch)
                if candidate is not None:
                    cond = candidate
                    continue
            if body_node is None and self._is_stmt_node(ch):
                body_node = ch

        if cond is None and len(children) >= 3 and isinstance(children[2], dict):
            cond = self.expr.from_node(children[2])
        if body_node is None and children:
            body_node = children[-1]

        return cond, body_node

    def compound_to_stmts(self, comp_node):
        stmts = []
        for child in comp_node.get("children", []):
            if not isinstance(child, dict):
                continue
            node_type = child.get("node")

            if node_type == "while_stmt":
                children = child.get("children", [])
                cond, body_node = self._extract_condition_and_body(children)
                body_stmts = self.process_stmt_node(body_node) if body_node else []
                stmts.append(
                    copy_line(
                        child, {"type": "while", "cond": cond, "body": body_stmts}
                    )
                )
                continue

            if node_type == "if_stmt":
                children = child.get("children", [])
                cond = None
                then_node = None
                else_node = None

                for ch in children:
                    if not isinstance(ch, dict):
                        continue
                    if cond is None and self._is_expr_node(ch):
                        candidate = self.expr.from_node(ch)
                        if candidate is not None:
                            cond = candidate
                            continue
                    if self._is_stmt_node(ch):
                        if then_node is None:
                            then_node = ch
                        elif else_node is None:
                            else_node = ch

                if (
                    cond is None
                    and len(children) >= 3
                    and isinstance(children[2], dict)
                ):
                    cond = self.expr.from_node(children[2])

                if cond is None:
                    name_found = self._find_name_in_node(child)
                    if name_found is not None:
                        cond = {"type": "var", "name": name_found}
                    else:
                        cond = {"type": "const", "value": 1}

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

            if node_type == "for_stmt":
                children = [
                    ch for ch in child.get("children", []) if isinstance(ch, dict)
                ]
                init_node = None
                cond_node = None
                step_node = None
                body_node = None

                if children and children[0].get("node") in ("declaration", "expr_stmt"):
                    init_node = children[0]
                    children = children[1:]

                if children:
                    if self._is_stmt_node(children[0]):
                        body_node = children[0]
                        children = children[1:]
                    else:
                        cond_node = children[0]
                        children = children[1:]

                if children:
                    if self._is_stmt_node(children[0]):
                        body_node = children[0]
                        children = children[1:]
                    else:
                        step_node = children[0]
                        children = children[1:]

                if body_node is None and children:
                    body_node = children[-1]

                init_stmts = self.process_stmt_node(init_node) if init_node else []
                cond_expr = (
                    self.expr.from_node(cond_node)
                    if cond_node
                    else {"type": "const", "value": 1}
                )
                body_stmts = self.process_stmt_node(body_node) if body_node else []
                step_stmt = self._expr_to_stmt(step_node, child) if step_node else None

                while_body = list(body_stmts)
                if step_stmt is not None:
                    while_body.append(step_stmt)

                stmts.extend(init_stmts)
                stmts.append(
                    copy_line(
                        child,
                        {
                            "type": "while",
                            "cond": cond_expr,
                            "body": while_body,
                        },
                    )
                )
                continue

            stmts.extend(self.process_stmt_node(child))
        return stmts
