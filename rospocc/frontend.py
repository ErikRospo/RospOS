"""Tiny frontend to convert preprocessed C-like source into the
translation-unit dict shape expected by `rospocc.emitter`.

This is deliberately small and heuristic-based to bootstrap the
pipeline. It recognizes:
- `int main(...) { ... return <int>; }`
- simple string globals like: `char name[] = "...";`
"""

import re
import sys
from typing import Any, Dict


# Utility to centralize string literal label creation and reuse
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
        # Prefer transformer-provided integer annotation when available
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


def code_to_translation_unit(input_data) -> Dict[str, Any]:
    """Convert either raw preprocessed code (str) or a parsed AST dict
    (as produced by `parser.tree_to_dict`) into the simple
    `translation_unit` dict expected by the emitter.

    The function attempts AST-driven extraction first; if given a
    string it uses the previous regex-based heuristics.
    """
    tu = {"globals": [], "functions": []}

    # If input is a dict-like AST produced by parser.tree_to_dict, walk it
    if isinstance(input_data, dict) and "node" in input_data:
        ast = input_data

        # pool for string literals encountered while walking AST
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
                # children: type_specifier, declarator, '(', param_list?, ')', compound_stmt
                children = node.get("children", [])
                name = None
                params = []
                param_types = {}
                body_node = None
                for c in children:
                    if isinstance(c, dict) and c.get("node") == "declarator":
                        # find NAME token inside declarator
                        for d in c.get("children", []):
                            if (
                                isinstance(d, dict)
                                and "token" in d
                                and d["token"].isidentifier()
                            ):
                                name = d["token"]
                                break
                    if isinstance(c, dict) and c.get("node") == "param_list":
                        # param_list -> param (',' param)*
                        for p in c.get("children", []):
                            if isinstance(p, dict) and p.get("node") == "param":
                                # look for declarator child
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
                                                # detect pointer in the param's type_specifier (char* etc.)
                                                # search parent p for a type_specifier child containing a pointer node
                                                found_ptr = False
                                                for tchild in p.get("children", []):
                                                    if (
                                                        isinstance(tchild, dict)
                                                        and tchild.get("node")
                                                        == "type_specifier"
                                                    ):
                                                        for pc in tchild.get(
                                                            "children", []
                                                        ):
                                                            if (
                                                                isinstance(pc, dict)
                                                                and pc.get("node")
                                                                == "pointer"
                                                            ):
                                                                param_types[
                                                                    n["token"]
                                                                ] = "char_ptr"
                                                                found_ptr = True
                                                                break
                                                # also check declarator itself for pointer nodes (pointer may be attached there)
                                                if not found_ptr:
                                                    for dc in pp.get("children", []):
                                                        if (
                                                            isinstance(dc, dict)
                                                            and dc.get("node")
                                                            == "pointer"
                                                        ):
                                                            param_types[n["token"]] = (
                                                                "char_ptr"
                                                            )
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
                # check for char NAME [] = STRING
                children = node.get("children", [])
                t_spec = None
                init_list = None
                for c in children:
                    if isinstance(c, dict) and c.get("node") == "type_specifier":
                        # find token inside
                        for d in c.get("children", []):
                            if isinstance(d, dict) and "token" in d:
                                t_spec = d["token"]
                    if isinstance(c, dict) and c.get("node") == "init_declarator_list":
                        init_list = c
                if t_spec == "char" and init_list:
                    # init_declarator_list contains init_declarator nodes
                    for init in init_list.get("children", []):
                        if (
                            isinstance(init, dict)
                            and init.get("node") == "init_declarator"
                        ):
                            decl_children = init.get("children", [])
                            name = None
                            val = None
                            for dc in decl_children:
                                if (
                                    isinstance(dc, dict)
                                    and dc.get("node") == "declarator"
                                ):
                                    for dd in dc.get("children", []):
                                        if (
                                            isinstance(dd, dict)
                                            and "token" in dd
                                            and dd["token"].isidentifier()
                                        ):
                                            name = dd["token"]
                                if (
                                    isinstance(dc, dict)
                                    and "token" in dc
                                    and dc["token"].startswith('"')
                                ):
                                    val = dc["token"][1:-1]
                            if name and val is not None:
                                tu["globals"].append(
                                    {"kind": "string", "name": name, "value": val}
                                )
                return []

            # recurse into children by default
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
                    # children: 'while', '(', expr, ')', statement
                    children = c.get("children", [])
                    cond = None
                    body_node = None
                    for ch in children:
                        # Support token-only children (e.g., NAME or NUMBER tokens) as expressions
                        if isinstance(ch, dict) and "token" in ch:
                            # treat token as expr candidate
                            if cond is None:
                                cand = expr_from_node(ch)
                                if cand is not None:
                                    cond = cand
                                    continue
                        if (
                            isinstance(ch, dict)
                            and ch.get("node")
                            and ch.get("node") != "("
                            and ch.get("node") != ")"
                        ):
                            # heuristics: first expr-like node is cond, next statement node is body
                            if cond is None and ch.get("node") not in (
                                "statement",
                                "compound_stmt",
                                "expr_stmt",
                                "declaration",
                                "return_stmt",
                            ):
                                # try to find expr inside
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
                        # fallback: try children[2]
                        if len(children) >= 3 and isinstance(children[2], dict):
                            cond = expr_from_node(children[2])
                    if body_node is None:
                        # try last child
                        if children:
                            body_node = children[-1]
                    # convert body_node to stmts
                    body_stmts = []
                    if body_node and isinstance(body_node, dict):
                        if body_node.get("node") == "compound_stmt":
                            body_stmts = compound_to_stmts(body_node)
                        else:
                            # single statement
                            if body_node.get("node") == "expr_stmt":
                                ev = None
                                for cc in body_node.get("children", []):
                                    if isinstance(cc, dict):
                                        ev = expr_from_node(cc)
                                        break
                                if ev:
                                    if ev.get("type") == "call":
                                        body_stmts.append(
                                            {
                                                "type": "call_stmt",
                                                "name": ev.get("name"),
                                                "args": ev.get("args", []),
                                            }
                                        )
                                    elif ev.get("type") == "assign":
                                        body_stmts.append(
                                            {
                                                "type": "assign",
                                                "target": ev.get("target"),
                                                "value": ev.get("value"),
                                            }
                                        )
                            else:
                                # unsupported single stmt
                                pass
                    stmts.append({"type": "while", "cond": cond, "body": body_stmts})
                    continue
                if nd == "if_stmt":
                    # children: 'if', '(', expr, ')', statement, ('else', statement)?
                    children = c.get("children", [])
                    cond = None
                    then_node = None
                    else_node = None
                    for ch in children:
                        # capture first expr-like child as condition
                        if isinstance(ch, dict) and "token" in ch:
                            if cond is None:
                                cand = expr_from_node(ch)
                                if cand is not None:
                                    cond = cand
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
                                cond = expr_from_node(ch)
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
                                # this may be the else branch
                                else_node = ch
                    # fallback heuristics: try positional child
                    if (
                        cond is None
                        and len(children) >= 3
                        and isinstance(children[2], dict)
                    ):
                        cond = expr_from_node(children[2])
                    # try to find a NAME token anywhere in the if node as a last-ditch cond
                    if cond is None:

                        def find_name_in_node(n):
                            if isinstance(n, dict):
                                if (
                                    "token" in n
                                    and isinstance(n["token"], str)
                                    and n["token"].isidentifier()
                                ):
                                    return n["token"]
                                for cc in n.get("children", []):
                                    r = find_name_in_node(cc)
                                    if r is not None:
                                        return r
                            return None

                        name_found = find_name_in_node(c)
                        if name_found is not None:
                            cond = {"type": "var", "name": name_found}
                        else:
                            # final fallback: assume true so we don't emit BEQ r0,r0 nonsense
                            cond = {"type": "const", "value": 1}
                    if then_node is None:
                        # try to find the statement after the ')' or last child
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
                        # attempt to find an 'else' token followed by a stmt node
                        for i, ch in enumerate(children):
                            if (
                                isinstance(ch, dict)
                                and "token" in ch
                                and ch["token"] == "else"
                            ):
                                if i + 1 < len(children) and isinstance(
                                    children[i + 1], dict
                                ):
                                    else_node = children[i + 1]
                                    break

                    # convert then/else nodes to stmt lists
                    then_stmts = []
                    else_stmts = []
                    if then_node:
                        if then_node.get("node") == "compound_stmt":
                            then_stmts = compound_to_stmts(then_node)
                        else:
                            # single statement
                            if then_node.get("node") == "expr_stmt":
                                ev = None
                                for cc in then_node.get("children", []):
                                    if isinstance(cc, dict):
                                        ev = expr_from_node(cc)
                                        break
                                if ev:
                                    if ev.get("type") == "call":
                                        then_stmts.append(
                                            {
                                                "type": "call_stmt",
                                                "name": ev.get("name"),
                                                "args": ev.get("args", []),
                                            }
                                        )
                                    elif ev.get("type") == "assign":
                                        then_stmts.append(
                                            {
                                                "type": "assign",
                                                "target": ev.get("target"),
                                                "value": ev.get("value"),
                                            }
                                        )
                            elif then_node.get("node") == "declaration":
                                # reuse declaration handling: find name/init
                                name = None
                                init = None
                                for cc in then_node.get("children", []):
                                    if (
                                        isinstance(cc, dict)
                                        and cc.get("node") == "init_declarator_list"
                                    ):
                                        for idc in cc.get("children", []):
                                            if (
                                                isinstance(idc, dict)
                                                and idc.get("node") == "init_declarator"
                                            ):
                                                for part in idc.get("children", []):
                                                    if (
                                                        isinstance(part, dict)
                                                        and part.get("node")
                                                        == "declarator"
                                                    ):
                                                        for t in part.get(
                                                            "children", []
                                                        ):
                                                            if (
                                                                isinstance(t, dict)
                                                                and "token" in t
                                                                and t[
                                                                    "token"
                                                                ].isidentifier()
                                                            ):
                                                                name = t["token"]
                                                    if (
                                                        isinstance(part, dict)
                                                        and "token" in part
                                                        and part["token"].startswith(
                                                            '"'
                                                        )
                                                    ):
                                                        val = part["token"][1:-1]
                                                        lab = None
                                                        for k, v in str_pool.items():
                                                            if v == val:
                                                                lab = k
                                                                break
                                                        if lab is None:
                                                            lab = f"str_{str_count}"
                                                            str_count += 1
                                                            str_pool[lab] = val
                                                            tu["globals"].append(
                                                                {
                                                                    "kind": "string",
                                                                    "name": lab,
                                                                    "value": val,
                                                                }
                                                            )
                                                        init = {
                                                            "type": "string_addr",
                                                            "label": lab,
                                                        }
                                if name:
                                    then_stmts.append(
                                        {"type": "decl", "name": name, "init": init}
                                    )
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
                                        else_stmts.append(
                                            {
                                                "type": "call_stmt",
                                                "name": ev.get("name"),
                                                "args": ev.get("args", []),
                                            }
                                        )
                                    elif ev.get("type") == "assign":
                                        else_stmts.append(
                                            {
                                                "type": "assign",
                                                "target": ev.get("target"),
                                                "value": ev.get("value"),
                                            }
                                        )
                            elif else_node.get("node") == "declaration":
                                name = None
                                init = None
                                for cc in else_node.get("children", []):
                                    if (
                                        isinstance(cc, dict)
                                        and cc.get("node") == "init_declarator_list"
                                    ):
                                        for idc in cc.get("children", []):
                                            if (
                                                isinstance(idc, dict)
                                                and idc.get("node") == "init_declarator"
                                            ):
                                                for part in idc.get("children", []):
                                                    if (
                                                        isinstance(part, dict)
                                                        and part.get("node")
                                                        == "declarator"
                                                    ):
                                                        for t in part.get(
                                                            "children", []
                                                        ):
                                                            if (
                                                                isinstance(t, dict)
                                                                and "token" in t
                                                                and t[
                                                                    "token"
                                                                ].isidentifier()
                                                            ):
                                                                name = t["token"]
                                                    if (
                                                        isinstance(part, dict)
                                                        and "token" in part
                                                        and part["token"].startswith(
                                                            '"'
                                                        )
                                                    ):
                                                        val = part["token"][1:-1]
                                                        lab = None
                                                        for k, v in str_pool.items():
                                                            if v == val:
                                                                lab = k
                                                                break
                                                        if lab is None:
                                                            lab = f"str_{str_count}"
                                                            str_count += 1
                                                            str_pool[lab] = val
                                                            tu["globals"].append(
                                                                {
                                                                    "kind": "string",
                                                                    "name": lab,
                                                                    "value": val,
                                                                }
                                                            )
                                                        init = {
                                                            "type": "string_addr",
                                                            "label": lab,
                                                        }
                                if name:
                                    else_stmts.append(
                                        {"type": "decl", "name": name, "init": init}
                                    )
                            elif else_node.get("node") == "return_stmt":
                                rv = None
                                for cc in else_node.get("children", []):
                                    if isinstance(cc, dict):
                                        rv = expr_from_node(cc)
                                        break
                                else_stmts.append({"type": "return", "value": rv})

                    stmts.append(
                        {
                            "type": "if",
                            "cond": cond,
                            "then": then_stmts,
                            "else": else_stmts,
                        }
                    )
                    continue
                if nd == "return_stmt":
                    # find expr child
                    expr = None
                    for cc in c.get("children", []):
                        if isinstance(cc, dict):
                            expr = expr_from_node(cc)
                            break
                    stmts.append({"type": "return", "value": expr})
                elif nd == "declaration":
                    # local decl
                    # look for init_declarator_list
                    name = None
                    init = None
                    for cc in c.get("children", []):
                        if (
                            isinstance(cc, dict)
                            and cc.get("node") == "init_declarator_list"
                        ):
                            for idc in cc.get("children", []):
                                if (
                                    isinstance(idc, dict)
                                    and idc.get("node") == "init_declarator"
                                ):
                                    # each init_declarator can contain a declarator and/or an initializer
                                    # detect array declarator like NAME '[' NUMBER ']'
                                    for part in idc.get("children", []):
                                        if (
                                            isinstance(part, dict)
                                            and part.get("node") == "declarator"
                                        ):
                                            # scan declarator children for NAME and optional [ NUMBER ]
                                            decl_children = part.get("children", [])
                                            for i, t in enumerate(decl_children):
                                                if (
                                                    isinstance(t, dict)
                                                    and "token" in t
                                                    and t["token"].isidentifier()
                                                ):
                                                    name = t["token"]
                                            # detect array size in declarator: '[' NUMBER ']'
                                            for i, t in enumerate(decl_children):
                                                if (
                                                    isinstance(t, dict)
                                                    and "token" in t
                                                    and t["token"] == "["
                                                ):
                                                    # next token may be a number (prefer annotated int)
                                                    if i + 1 < len(decl_children) and isinstance(
                                                        decl_children[i + 1], dict
                                                    ):
                                                        next_child = decl_children[i + 1]
                                                        if "int" in next_child:
                                                            array_len = int(next_child["int"])
                                                            init = {"type": "array", "size": array_len}
                                                        elif "token" in next_child:
                                                            tok = next_child["token"]
                                                            if isinstance(tok, str) and re.fullmatch(
                                                                r"-?\d+|0x[0-9a-fA-F]+", tok
                                                            ):
                                                                try:
                                                                    array_len = int(tok, 0)
                                                                except Exception:
                                                                    array_len = int(tok)
                                                                init = {"type": "array", "size": array_len}
                                                    break
                                        # initializer tokens that are outside declarator
                                        if isinstance(part, dict) and part.get("node") is None:
                                            # token could be a NUMBER or STRING; prefer annotated int
                                            if "int" in part:
                                                init = {"type": "const", "value": int(part["int"])}
                                            elif "token" in part:
                                                tok = part.get("token")
                                                if isinstance(tok, str) and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", tok):
                                                    try:
                                                        init = {"type": "const", "value": int(tok, 0)}
                                                    except Exception:
                                                        init = {"type": "const", "value": int(tok)}
                                            # string literal initializer
                                        if (
                                            isinstance(part, dict)
                                            and "token" in part
                                            and part["token"].startswith('"')
                                        ):
                                            val = part["token"][1:-1]
                                            # reuse or create label
                                            lab = None
                                            for k, v in str_pool.items():
                                                if v == val:
                                                    lab = k
                                                    break
                                            if lab is None:
                                                lab = f"str_{str_count}"
                                                str_count += 1
                                                str_pool[lab] = val
                                                tu["globals"].append(
                                                    {
                                                        "kind": "string",
                                                        "name": lab,
                                                        "value": val,
                                                    }
                                                )
                                            init = {"type": "string_addr", "label": lab}
                                        if isinstance(part, dict) and part.get("node"):
                                            # equal expr might be represented as a child node
                                            # fallback: try to find a NUMBER token inside
                                            val = find_number_in_node(part)
                                            if val is not None:
                                                init = {"type": "const", "value": val}
                    if name:
                        stmts.append({"type": "decl", "name": name, "init": init})
                elif nd == "expr_stmt":
                    # expression statement — could be call or assignment
                    expr = None
                    for cc in c.get("children", []):
                        if isinstance(cc, dict):
                            expr = expr_from_node(cc)
                            break
                    if expr:
                        if expr.get("type") == "call":
                            stmts.append(
                                {
                                    "type": "call_stmt",
                                    "name": expr.get("name"),
                                    "args": expr.get("args", []),
                                }
                            )
                        elif expr.get("type") == "assign":
                            stmts.append(
                                {
                                    "type": "assign",
                                    "target": expr.get("target"),
                                    "value": expr.get("value"),
                                }
                            )
                        else:
                            # ignore other expr_stmt forms
                            pass
                else:
                    # ignore other statements for now
                    pass
            return stmts

        def find_number_in_node(n):
            if isinstance(n, dict):
                if "int" in n:
                    return n["int"]
                if "token" in n and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", n["token"]):
                    try:
                        return int(n["token"], 0)
                    except Exception:
                        return None
                for c in n.get("children", []):
                    v = find_number_in_node(c)
                    if v is not None:
                        return v
            return None

        def expr_from_node(n):
            # return expression dict: const, var, binop, call, string_addr
            nonlocal str_count
            if not isinstance(n, dict):
                return None
            if "token" in n:
                tok = n["token"]
                # prefer annotated integer value
                if isinstance(n, dict) and "int" in n:
                    return {"type": "const", "value": int(n["int"])}
                if re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", tok):
                    try:
                        return {"type": "const", "value": int(tok, 0)}
                    except Exception:
                        return {"type": "const", "value": int(tok)}
                if tok.startswith('"') and tok.endswith('"'):
                    # literal string -> create or reuse a global label
                    val = tok[1:-1]
                    lab, new_count = _get_or_create_string_label(
                        val, str_pool, str_count, tu
                    )
                    str_count = new_count
                    return {"type": "string_addr", "label": lab}
                if tok.isidentifier():
                    return {"type": "var", "name": tok}
                return None

            node_name = n.get("node")
            if node_name in (
                "additive",
                "multiplicative",
                "relational",
                "equality",
                "shift",
            ):
                # children may be [left, {'token':op}, right, ...]
                children = n.get("children", [])
                if not children:
                    return None
                # reduce binary left-associative
                left = expr_from_node(children[0])
                i = 1
                # ensure we have pairs (op, right)
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
                # child pattern: left, '=' token, right
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
                        return {
                            "type": "assign",
                            "target": left.get("name"),
                            "value": right,
                        }
                return None

            if node_name == "unary":
                # unary may have token '*' for deref etc
                children = n.get("children", [])
                if not children:
                    return None
                first = children[0]
                if (
                    isinstance(first, dict)
                    and "token" in first
                    and first["token"] == "*"
                ):
                    # dereference
                    if len(children) > 1:
                        inner = expr_from_node(children[1])
                        if inner:
                            return {"type": "deref", "expr": inner}
                # other unary ops ignored for now
                return expr_from_node(children[-1])

            if node_name == "postfix":
                # look for call pattern: primary then arg_list
                children = n.get("children", [])
                if not children:
                    return None
                primary = children[0]
                # detect post-increment/decrement tokens
                has_inc = False
                has_dec = False
                for c in children[1:]:
                    if isinstance(c, dict) and "token" in c:
                        if c["token"] == "++":
                            has_inc = True
                        if c["token"] == "--":
                            has_dec = True

                # if any child is arg_list -> call
                for c in children[1:]:
                    if isinstance(c, dict) and c.get("node") == "arg_list":
                        # primary should be NAME token
                        if (
                            isinstance(primary, dict)
                            and "token" in primary
                            and primary["token"].isidentifier()
                        ):
                            args = []
                            for a in c.get("children", []):
                                if isinstance(a, dict):
                                    ev = expr_from_node(a)
                                    if ev:
                                        args.append(ev)
                            return {
                                "type": "call",
                                "name": primary["token"],
                                "args": args,
                            }

                # convert postfix ++/-- into an assignment expression: x = x + 1 or x = x - 1
                # primary may be a nested node (e.g., primary -> NAME token). Resolve it via expr_from_node
                print(
                    f"[frontend] postfix detected primary={primary!r} has_inc={has_inc} has_dec={has_dec}",
                    file=sys.stderr,
                )
                primary_expr = expr_from_node(primary)
                print(
                    f"[frontend] resolved primary_expr={primary_expr!r}",
                    file=sys.stderr,
                )
                if (
                    (has_inc or has_dec)
                    and primary_expr
                    and primary_expr.get("type") == "var"
                ):
                    pname = primary_expr.get("name")
                    op = "+" if has_inc else "-"
                    assign_expr = {
                        "type": "assign",
                        "target": pname,
                        "value": {
                            "type": "binop",
                            "op": op,
                            "left": {"type": "var", "name": pname},
                            "right": {"type": "const", "value": 1},
                        },
                    }
                    print(
                        f"[frontend] postfix -> assign {assign_expr!r}", file=sys.stderr
                    )
                    return assign_expr

                # otherwise fallback to primary
                return expr_from_node(primary)

            # descend into children and try to convert
            for c in n.get("children", []):
                r = expr_from_node(c)
                if r is not None:
                    return r
            return None

        # fix: ensure bounds when combining binary children
        # (handled in expr_from_node below)

        walk(ast)
        return tu


__all__ = ["code_to_translation_unit"]
