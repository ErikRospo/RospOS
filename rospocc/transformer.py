"""Lark AST transformer for rospocc.

This module provides an `ASTTransformer` class that condenses the
Lark parse `Tree`/`Token` into a lightweight dict structure used
by the rest of the `rospocc` pipeline.

The output shape matches the previous `tree_to_dict` output:
  {'node': <rule_name>, 'children': [ ... ]}
and tokens become `{'token': '...'}"""


from lark import Transformer, Token, Tree
import re


class ASTTransformer(Transformer):
    """Transformer that converts a Lark parse tree into a compact dict
    representation used across `rospocc`.

    It preserves node names for structural constructs but performs a few
    safe normalizations:
      - tokens remain as `{'token': '...'}' but numeric and string tokens
        also carry parsed helpers (`int` and `str_val`) to avoid repeated
        conversions downstream
      - simple wrapper nodes like `primary` are flattened when safe
    """

    def __default_token__(self, token: Token):
        tok = str(token)
        out = {"token": tok}
        # annotate integers for convenience
        if re.fullmatch(r"0x[0-9a-fA-F]+|\d+", tok):
            try:
                out["int"] = int(tok, 0)
            except Exception:
                try:
                    out["int"] = int(tok)
                except Exception:
                    pass
        # annotate string literal unescaped form
        if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
            # remove surrounding quotes, keep escape sequences as-is
            out["str_val"] = tok[1:-1]
        # booleans and nullptr
        if tok == "true":
            out["bool"] = True
        if tok == "false":
            out["bool"] = False
        if tok == "nullptr":
            out["null"] = True
        return out

    def __default__(self, data, children, meta):
        # children already transformed by Transformer
        node = {"node": data, "children": children}

        # Safe flattening: if node is a `primary` wrapper with a single child,
        # return the child directly (removes parentheses / single nesting).
        if data == "primary" and len(children) == 1:
            return children[0]

        # Flatten the start wrapper to expose translation_unit directly
        if data == "start" and len(children) == 1:
            return children[0]

        return node


def transform_tree(tree: Tree):
    """Transform a Lark `Tree` into the condensed dict form.

    Returns the transformed dict or the token-dict for Token inputs.
    """
    if isinstance(tree, Tree):
        return ASTTransformer().transform(tree)
    if isinstance(tree, Token):
        return ASTTransformer().__default_token__(tree)
    return tree


def transform_to_translation_unit(input_data) -> dict:
    """Convert parsed AST (Lark Tree or transformed dict) into a
    `translation_unit` dict consumed by the emitter.

    This logic was previously in `frontend.code_to_translation_unit` and
    has been moved here so the transformer owns AST normalization and TU
    extraction.
    """
    # Accept either a Lark Tree/Token or the already-transformed dict
    ast = transform_tree(input_data) if isinstance(input_data, (Tree, Token)) else input_data

    tu = {"globals": [], "functions": []}

    def _get_or_create_string_label(val: str, str_pool: dict, str_count: int, tu: dict):
        for lab, v in str_pool.items():
            if v == val:
                return lab, str_count
        lab = f"str_{str_count}"
        str_count += 1
        str_pool[lab] = val
        tu["globals"].append({"kind": "string", "name": lab, "value": val})
        return lab, str_count

    def _find_number_in_node(n):
        if isinstance(n, dict):
            if "int" in n:
                return n["int"]
            if "token" in n and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", n["token"]):
                try:
                    return int(n["token"], 0)
                except Exception:
                    return None
            for c in n.get("children", []):
                v = _find_number_in_node(c)
                if v is not None:
                    return v
        return None

    # Main conversion functions (walk AST and produce translation unit)
    str_pool = {}
    str_count = 0

    def walk(node):
        res = []
        if not isinstance(node, dict):
            return res
        if node.get("node") == "translation_unit" or node.get("node") == "start":
            for c in node.get("children", []):
                res.extend(walk(c))
            return res

        # function_def nodes
        if node.get("node") == "function_def":
            children = node.get("children", [])
            name = None
            params = []
            param_types = {}
            body_node = None
            for c in children:
                if isinstance(c, dict) and c.get("node") == "declarator":
                    for d in c.get("children", []):
                        if (
                            isinstance(d, dict)
                            and "token" in d
                            and d["token"].isidentifier()
                        ):
                            name = d["token"]
                            break
                if isinstance(c, dict) and c.get("node") == "param_list":
                    for p in c.get("children", []):
                        if isinstance(p, dict) and p.get("node") == "param":
                            for pp in p.get("children", []):
                                if (
                                    isinstance(pp, dict)
                                    and pp.get("node") == "declarator"
                                ):
                                    for n in pp.get("children", []):
                                        if (
                                            isinstance(n, dict)
                                            and "token" in n
                                            and n["token"].isidentifier()
                                        ):
                                            params.append(n["token"])
                                            found_ptr = False
                                            for tchild in p.get("children", []):
                                                if (
                                                    isinstance(tchild, dict)
                                                    and tchild.get("node")
                                                    == "type_specifier"
                                                ):
                                                    for pc in tchild.get("children", []):
                                                        if (
                                                            isinstance(pc, dict)
                                                            and pc.get("node")
                                                            == "pointer"
                                                        ):
                                                            param_types[n["token"]] = "char_ptr"
                                                            found_ptr = True
                                                            break
                                            if not found_ptr:
                                                for dc in pp.get("children", []):
                                                    if (
                                                        isinstance(dc, dict)
                                                        and dc.get("node")
                                                        == "pointer"
                                                    ):
                                                        param_types[n["token"]] = "char_ptr"
                                                        break
                if isinstance(c, dict) and c.get("node") == "compound_stmt":
                    body_node = c

            body = []
            if body_node:
                body = compound_to_stmts(body_node)

            fdict = {"name": name or "fn", "params": params, "body": body}
            if param_types:
                fdict["param_types"] = param_types
            tu["functions"].append(fdict)
            return [None]

        # global declarations
        if node.get("node") == "declaration":
            children = node.get("children", [])
            t_spec = None
            init_list = None
            for c in children:
                if isinstance(c, dict) and c.get("node") == "type_specifier":
                    for d in c.get("children", []):
                        if isinstance(d, dict) and "token" in d:
                            t_spec = d["token"]
                if isinstance(c, dict) and c.get("node") == "init_declarator_list":
                    init_list = c
            if t_spec == "char" and init_list:
                for init in init_list.get("children", []):
                    if isinstance(init, dict) and init.get("node") == "init_declarator":
                        decl_children = init.get("children", [])
                        name = None
                        val = None
                        for dc in decl_children:
                            if isinstance(dc, dict) and dc.get("node") == "declarator":
                                for dd in dc.get("children", []):
                                    if (
                                        isinstance(dd, dict)
                                        and "token" in dd
                                        and dd["token"].isidentifier()
                                    ):
                                        name = dd["token"]
                            if isinstance(dc, dict) and "token" in dc and dc["token"].startswith('"'):
                                val = dc["token"][1:-1]
                        if name and val is not None:
                            tu["globals"].append({"kind": "string", "name": name, "value": val})
            return []

        # recurse
        for c in node.get("children", []):
            res.extend(walk(c) or [])
        return res

    def compound_to_stmts(comp_node):
        nonlocal str_count
        stmts = []
        for c in comp_node.get("children", []):
            if not isinstance(c, dict):
                continue
            nd = c.get("node")
            if nd == "while_stmt":
                children = c.get("children", [])
                cond = None
                body_node = None
                for ch in children:
                    if isinstance(ch, dict) and "token" in ch:
                        if cond is None:
                            cand = expr_from_node(ch)
                            if cand is not None:
                                cond = cand
                                continue
                    if isinstance(ch, dict) and ch.get("node") and ch.get("node") not in ("(", ")"):
                        if cond is None and ch.get("node") not in (
                            "statement",
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            cond = expr_from_node(ch)
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
                            cond = expr_from_node(ch)
                        elif body_node is None and ch.get("node") in (
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            body_node = ch
                if cond is None:
                    if len(children) >= 3 and isinstance(children[2], dict):
                        cond = expr_from_node(children[2])
                if body_node is None and children:
                    body_node = children[-1]
                body_stmts = []
                if body_node and isinstance(body_node, dict):
                    if body_node.get("node") == "compound_stmt":
                        body_stmts = compound_to_stmts(body_node)
                    else:
                        if body_node.get("node") == "expr_stmt":
                            ev = None
                            for cc in body_node.get("children", []):
                                if isinstance(cc, dict):
                                    ev = expr_from_node(cc)
                                    break
                            if ev:
                                if ev.get("type") == "call":
                                    body_stmts.append({"type": "call_stmt", "name": ev.get("name"), "args": ev.get("args", [])})
                                elif ev.get("type") == "assign":
                                    body_stmts.append({"type": "assign", "target": ev.get("target"), "value": ev.get("value")})
                stmts.append({"type": "while", "cond": cond, "body": body_stmts})
                continue
            if nd == "if_stmt":
                children = c.get("children", [])
                cond = None
                then_node = None
                else_node = None
                for ch in children:
                    if isinstance(ch, dict) and "token" in ch:
                        if cond is None:
                            cand = expr_from_node(ch)
                            if cand is not None:
                                cond = cand
                                continue
                    if isinstance(ch, dict) and ch.get("node") and ch.get("node") not in ("(", ")"):
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
                            cond = expr_from_node(ch)
                        elif then_node is None and ch.get("node") in (
                            "compound_stmt",
                            "expr_stmt",
                            "declaration",
                            "return_stmt",
                        ):
                            then_node = ch
                        elif ch.get("node") in ("compound_stmt", "expr_stmt", "declaration", "return_stmt") and then_node is not None and else_node is None:
                            else_node = ch
                if cond is None and len(children) >= 3 and isinstance(children[2], dict):
                    cond = expr_from_node(children[2])

                def find_name_in_node(n):
                    if isinstance(n, dict):
                        if ("token" in n and isinstance(n["token"], str) and n["token"].isidentifier()):
                            return n["token"]
                        for cc in n.get("children", []):
                            r = find_name_in_node(cc)
                            if r is not None:
                                return r
                    return None

                if cond is None:
                    name_found = find_name_in_node(c)
                    if name_found is not None:
                        cond = {"type": "var", "name": name_found}
                    else:
                        cond = {"type": "const", "value": 1}
                if then_node is None:
                    for ch in children:
                        if isinstance(ch, dict) and ch.get("node") in ("compound_stmt", "expr_stmt", "declaration", "return_stmt"):
                            then_node = ch
                            break
                if else_node is None:
                    for i, ch in enumerate(children):
                        if isinstance(ch, dict) and "token" in ch and ch["token"] == "else":
                            if i + 1 < len(children) and isinstance(children[i + 1], dict):
                                else_node = children[i + 1]
                                break

                then_stmts = []
                else_stmts = []
                if then_node:
                    if then_node.get("node") == "compound_stmt":
                        then_stmts = compound_to_stmts(then_node)
                    else:
                        if then_node.get("node") == "expr_stmt":
                            ev = None
                            for cc in then_node.get("children", []):
                                if isinstance(cc, dict):
                                    ev = expr_from_node(cc)
                                    break
                            if ev:
                                if ev.get("type") == "call":
                                    then_stmts.append({"type": "call_stmt", "name": ev.get("name"), "args": ev.get("args", [])})
                                elif ev.get("type") == "assign":
                                    then_stmts.append({"type": "assign", "target": ev.get("target"), "value": ev.get("value")})
                        elif then_node.get("node") == "declaration":
                            name = None
                            init = None
                            for cc in then_node.get("children", []):
                                if isinstance(cc, dict) and cc.get("node") == "init_declarator_list":
                                    for idc in cc.get("children", []):
                                        if isinstance(idc, dict) and idc.get("node") == "init_declarator":
                                            for part in idc.get("children", []):
                                                if isinstance(part, dict) and part.get("node") == "declarator":
                                                    for t in part.get("children", []):
                                                        if isinstance(t, dict) and "token" in t and t["token"].isidentifier():
                                                            name = t["token"]
                                                if isinstance(part, dict) and "token" in part and part["token"].startswith('"'):
                                                    val = part["token"][1:-1]
                                                    lab, str_count = _get_or_create_string_label(val, str_pool, str_count, tu)
                                                    init = {"type": "string_addr", "label": lab}
                            if name:
                                then_stmts.append({"type": "decl", "name": name, "init": init})
                        elif then_node.get("node") == "return_stmt":
                            rv = None
                            for cc in then_node.get("children", []):
                                if isinstance(cc, dict):
                                    rv = expr_from_node(cc)
                                    break
                            then_stmts.append({"type": "return", "value": rv})

                if else_node:
                    if else_node.get("node") == "compound_stmt":
                        else_stmts = compound_to_stmts(else_node)
                    else:
                        if else_node.get("node") == "expr_stmt":
                            ev = None
                            for cc in else_node.get("children", []):
                                if isinstance(cc, dict):
                                    ev = expr_from_node(cc)
                                    break
                            if ev:
                                if ev.get("type") == "call":
                                    else_stmts.append({"type": "call_stmt", "name": ev.get("name"), "args": ev.get("args", [])})
                                elif ev.get("type") == "assign":
                                    else_stmts.append({"type": "assign", "target": ev.get("target"), "value": ev.get("value")})
                        elif else_node.get("node") == "declaration":
                            name = None
                            init = None
                            for cc in else_node.get("children", []):
                                if isinstance(cc, dict) and cc.get("node") == "init_declarator_list":
                                    for idc in cc.get("children", []):
                                        if isinstance(idc, dict) and idc.get("node") == "init_declarator":
                                            for part in idc.get("children", []):
                                                if isinstance(part, dict) and part.get("node") == "declarator":
                                                    for t in part.get("children", []):
                                                        if isinstance(t, dict) and "token" in t and t["token"].isidentifier():
                                                            name = t["token"]
                                                if isinstance(part, dict) and "token" in part and part["token"].startswith('"'):
                                                    val = part["token"][1:-1]
                                                    lab, str_count = _get_or_create_string_label(val, str_pool, str_count, tu)
                                                    init = {"type": "string_addr", "label": lab}
                            if name:
                                else_stmts.append({"type": "decl", "name": name, "init": init})
                        elif else_node.get("node") == "return_stmt":
                            rv = None
                            for cc in else_node.get("children", []):
                                if isinstance(cc, dict):
                                    rv = expr_from_node(cc)
                                    break
                            else_stmts.append({"type": "return", "value": rv})

                stmts.append({"type": "if", "cond": cond, "then": then_stmts, "else": else_stmts})
                continue
            if nd == "return_stmt":
                expr = None
                for cc in c.get("children", []):
                    if isinstance(cc, dict):
                        expr = expr_from_node(cc)
                        break
                stmts.append({"type": "return", "value": expr})
            elif nd == "declaration":
                name = None
                init = None
                for cc in c.get("children", []):
                    if isinstance(cc, dict) and cc.get("node") == "init_declarator_list":
                        for idc in cc.get("children", []):
                            if isinstance(idc, dict) and idc.get("node") == "init_declarator":
                                for part in idc.get("children", []):
                                    if isinstance(part, dict) and part.get("node") == "declarator":
                                        decl_children = part.get("children", [])
                                        for i, t in enumerate(decl_children):
                                            if isinstance(t, dict) and "token" in t and t["token"].isidentifier():
                                                name = t["token"]
                                        for i, t in enumerate(decl_children):
                                            if isinstance(t, dict) and "token" in t and t["token"] == "[":
                                                if i + 1 < len(decl_children) and isinstance(decl_children[i + 1], dict):
                                                    next_child = decl_children[i + 1]
                                                    if "int" in next_child:
                                                        array_len = int(next_child["int"])
                                                        init = {"type": "array", "size": array_len}
                                                    elif "token" in next_child:
                                                        tok = next_child["token"]
                                                        if isinstance(tok, str) and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", tok):
                                                            try:
                                                                array_len = int(tok, 0)
                                                            except Exception:
                                                                array_len = int(tok)
                                                            init = {"type": "array", "size": array_len}
                                                break
                                    if isinstance(part, dict) and part.get("node") is None:
                                        if "int" in part:
                                            init = {"type": "const", "value": int(part["int"])}
                                        elif "token" in part:
                                            tok = part.get("token")
                                            if isinstance(tok, str) and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", tok):
                                                try:
                                                    init = {"type": "const", "value": int(tok, 0)}
                                                except Exception:
                                                    init = {"type": "const", "value": int(tok)}
                                    if isinstance(part, dict) and "token" in part and part["token"].startswith('"'):
                                        val = part["token"][1:-1]
                                        lab, str_count = _get_or_create_string_label(val, str_pool, str_count, tu)
                                        init = {"type": "string_addr", "label": lab}
                                    if isinstance(part, dict) and part.get("node"):
                                        val = _find_number_in_node(part)
                                        if val is not None:
                                            init = {"type": "const", "value": val}
                if name:
                    stmts.append({"type": "decl", "name": name, "init": init})
            elif nd == "expr_stmt":
                expr = None
                for cc in c.get("children", []):
                    if isinstance(cc, dict):
                        expr = expr_from_node(cc)
                        break
                if expr:
                    if expr.get("type") == "call":
                        stmts.append({"type": "call_stmt", "name": expr.get("name"), "args": expr.get("args", [])})
                    elif expr.get("type") == "assign":
                        stmts.append({"type": "assign", "target": expr.get("target"), "value": expr.get("value")})
            else:
                pass
        return stmts

    def find_number_in_node(n):
        return _find_number_in_node(n)

    def expr_from_node(n):
        nonlocal str_count
        if not isinstance(n, dict):
            return None
        if "token" in n:
            tok = n["token"]
            if isinstance(n, dict) and "int" in n:
                return {"type": "const", "value": int(n["int"])}
            if re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", tok):
                try:
                    return {"type": "const", "value": int(tok, 0)}
                except Exception:
                    return {"type": "const", "value": int(tok)}
            if tok.startswith('"') and tok.endswith('"'):
                val = tok[1:-1]
                lab, new_count = _get_or_create_string_label(val, str_pool, str_count, tu)
                str_count = new_count
                return {"type": "string_addr", "label": lab}
            if tok.isidentifier():
                return {"type": "var", "name": tok}
            return None

        node_name = n.get("node")
        if node_name in ("additive", "multiplicative", "relational", "equality", "shift"):
            children = n.get("children", [])
            if not children:
                return None
            left = expr_from_node(children[0])
            i = 1
            while i + 1 < len(children):
                opn = children[i]
                rightn = children[i + 1]
                op = None
                if isinstance(opn, dict) and "token" in opn:
                    op = opn["token"]
                right = expr_from_node(rightn)
                if op and left and right:
                    left = {"type": "binop", "op": op, "left": left, "right": right}
                i += 2
            return left

        if node_name == "assignment":
            children = n.get("children", [])
            if (
                len(children) >= 3
                and isinstance(children[1], dict)
                and "token" in children[1]
                and children[1]["token"] == "="
            ):
                left = expr_from_node(children[0])
                right = expr_from_node(children[2])
                if left and left.get("type") == "var":
                    return {"type": "assign", "target": left.get("name"), "value": right}
            return None

        if node_name == "unary":
            children = n.get("children", [])
            if not children:
                return None
            first = children[0]
            if isinstance(first, dict) and "token" in first and first["token"] == "*":
                if len(children) > 1:
                    inner = expr_from_node(children[1])
                    if inner:
                        return {"type": "deref", "expr": inner}
            return expr_from_node(children[-1])

        if node_name == "postfix":
            children = n.get("children", [])
            if not children:
                return None
            primary = children[0]
            has_inc = False
            has_dec = False
            for c in children[1:]:
                if isinstance(c, dict) and "token" in c:
                    if c["token"] == "++":
                        has_inc = True
                    if c["token"] == "--":
                        has_dec = True
            for c in children[1:]:
                if isinstance(c, dict) and c.get("node") == "arg_list":
                    if isinstance(primary, dict) and "token" in primary and primary["token"].isidentifier():
                        args = []
                        for a in c.get("children", []):
                            if isinstance(a, dict):
                                ev = expr_from_node(a)
                                if ev:
                                    args.append(ev)
                        return {"type": "call", "name": primary["token"], "args": args}
            primary_expr = expr_from_node(primary)
            if (has_inc or has_dec) and primary_expr and primary_expr.get("type") == "var":
                pname = primary_expr.get("name")
                op = "+" if has_inc else "-"
                assign_expr = {"type": "assign", "target": pname, "value": {"type": "binop", "op": op, "left": {"type": "var", "name": pname}, "right": {"type": "const", "value": 1}}}
                return assign_expr
            return expr_from_node(primary)

        for c in n.get("children", []):
            r = expr_from_node(c)
            if r is not None:
                return r
        return None

    walk(ast)
    return tu


__all__ = ["ASTTransformer", "transform_tree", "transform_to_translation_unit"]
