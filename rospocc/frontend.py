"""Tiny frontend to convert preprocessed C-like source into the
translation-unit dict shape expected by `rospocc.emitter`.

This is deliberately small and heuristic-based to bootstrap the
pipeline. It recognizes:
- `int main(...) { ... return <int>; }`
- simple string globals like: `char name[] = "...";`
"""
import re
from typing import Dict, Any


def code_to_translation_unit(input_data) -> Dict[str, Any]:
    """Convert either raw preprocessed code (str) or a parsed AST dict
    (as produced by `parser.tree_to_dict`) into the simple
    `translation_unit` dict expected by the emitter.

    The function attempts AST-driven extraction first; if given a
    string it uses the previous regex-based heuristics.
    """
    tu = {'globals': [], 'functions': []}

    # If input is a dict-like AST, try to extract strings and main/return
    if isinstance(input_data, dict) and 'node' in input_data:
        ast = input_data

        def find_string_literals(n):
            results = []
            if isinstance(n, dict):
                # leaves with tokens are dicts with key 'token'
                if 'token' in n:
                    tok = n['token']
                    if isinstance(tok, str) and tok.startswith('"') and tok.endswith('"'):
                        results.append(tok[1:-1])
                for c in n.get('children', []):
                    results.extend(find_string_literals(c))
            return results

        def find_identifier_before_string(n):
            # Heuristic: look for pattern [identifier, string_token] in children
            if not isinstance(n, dict):
                return None
            ch = n.get('children', [])
            for i in range(len(ch) - 1):
                a, b = ch[i], ch[i + 1]
                if isinstance(a, dict) and 'token' in a and isinstance(b, dict) and 'token' in b:
                    if isinstance(a['token'], str) and a['token'].isidentifier() and isinstance(b['token'], str) and b['token'].startswith('"'):
                        return (a['token'], b['token'][1:-1])
            for c in ch:
                res = find_identifier_before_string(c)
                if res:
                    return res
            return None

        # Collect string globals (very heuristic)
        s = find_identifier_before_string(ast)
        if s:
            name, val = s
            tu['globals'].append({'kind': 'string', 'name': name, 'value': val})

        # Find a numeric return inside the AST
        def find_return_number(n):
            if isinstance(n, dict):
                if n.get('node') and 'return' in n.get('node'):
                    # search children for numeric token
                    for c in n.get('children', []):
                        if isinstance(c, dict) and 'token' in c:
                            tok = c['token']
                            if isinstance(tok, str) and re.fullmatch(r"-?\d+", tok):
                                return int(tok)
                for c in n.get('children', []):
                    res = find_return_number(c)
                    if res is not None:
                        return res
            return None

        ret = find_return_number(ast)
        if ret is None:
            ret = 0
        tu['functions'].append({'name': 'main', 'body': [{'type': 'return', 'value': {'type': 'const', 'value': ret}}]})

        return tu

    # Fallback: treat input_data as raw code string and use regex heuristics
    code = input_data

    # Pool for string literals encountered while parsing functions
    str_pool = {}
    str_count = 0

    # Find simple string globals: char foo[] = "...";
    for m in re.finditer(r"char\s+(?P<name>\w+)\s*\[\s*\]\s*=\s*\"(?P<val>.*?)\"\s*;",
                         code, flags=re.DOTALL):
        tu['globals'].append({'kind': 'string', 'name': m.group('name'), 'value': m.group('val')})

    # Find function definitions (very simple regex-based parser)
    for m in re.finditer(r"(?P<ret>\w+)\s+(?P<name>\w+)\s*\((?P<params>[^)]*)\)\s*\{(?P<body>.*?)\}", code, flags=re.DOTALL):
        name = m.group('name')
        params = m.group('params').strip()
        body = m.group('body')
        param_list = []
        if params:
            for p in params.split(','):
                p = p.strip()
                if not p:
                    continue
                parts = p.split()
                param_list.append(parts[-1])

        stmts = []
        # Process body line-by-line for simple constructs
        for line in body.split(';'):
            line = line.strip()
            if not line:
                continue
            # Remove comments
            line = re.sub(r"//.*$", "", line).strip()

            # int x = 5
            m_decl = re.match(r"int\s+(?P<name>\w+)\s*=\s*(?P<val>-?\d+)$", line)
            if m_decl:
                stmts.append({'type': 'decl', 'name': m_decl.group('name'), 'init': {'type': 'const', 'value': int(m_decl.group('val'))}})
                continue

            # int result = add(x, y)
            m_call_assign = re.match(r"int\s+(?P<name>\w+)\s*=\s*(?P<call>\w+)\((?P<args>.*)\)$", line)
            if m_call_assign:
                args = [a.strip() for a in m_call_assign.group('args').split(',') if a.strip()]
                stmts.append({'type': 'decl', 'name': m_call_assign.group('name'), 'init': {'type': 'call', 'name': m_call_assign.group('call'), 'args': [{'type': 'var', 'name': a} for a in args]}})
                continue

            # assignment from call: result = add(x, y)
            m_call_assign2 = re.match(r"(?P<name>\w+)\s*=\s*(?P<call>\w+)\((?P<args>.*)\)$", line)
            if m_call_assign2:
                args = [a.strip() for a in m_call_assign2.group('args').split(',') if a.strip()]
                stmts.append({'type': 'assign', 'target': m_call_assign2.group('name'), 'value': {'type': 'call', 'name': m_call_assign2.group('call'), 'args': [{'type': 'var', 'name': a} for a in args]}})
                continue

            # function calls like print_string("...")
            m_call = re.match(r"(?P<name>\w+)\((?P<args>.*)\)$", line)
            if m_call:
                fname = m_call.group('name')
                args_raw = m_call.group('args')
                args = []
                if args_raw:
                    # split by commas (naive)
                    for a in [s.strip() for s in args_raw.split(',')]:
                        if a.startswith('"') and a.endswith('"'):
                            # string literal — add to pool
                            l = a[1:-1]
                            lab = f"str_{str_count}"
                            str_count += 1
                            str_pool[lab] = l
                            args.append({'type': 'string_addr', 'label': lab})
                        elif re.fullmatch(r"-?\d+", a):
                            args.append({'type': 'const', 'value': int(a)})
                        else:
                            args.append({'type': 'var', 'name': a})
                stmts.append({'type': 'call_stmt', 'name': fname, 'args': args})
                continue

            # return statements
            m_ret = re.match(r"return\s+(?P<expr>.+)$", line)
            if m_ret:
                expr = m_ret.group('expr').strip()
                # binary add
                m_bin = re.match(r"(?P<a>\w+)\s*\+\s*(?P<b>\w+)$", expr)
                if m_bin:
                    stmts.append({'type': 'return', 'value': {'type': 'binop', 'op': '+', 'left': {'type': 'var', 'name': m_bin.group('a')}, 'right': {'type': 'var', 'name': m_bin.group('b')}}})
                elif re.fullmatch(r"-?\d+", expr):
                    stmts.append({'type': 'return', 'value': {'type': 'const', 'value': int(expr)}})
                else:
                    # return variable
                    stmts.append({'type': 'return', 'value': {'type': 'var', 'name': expr}})
                continue

            # fallback: ignore
            # print unknown lines for inspection
            # stmts.append({'type': 'unknown', 'text': line})

        tu['functions'].append({'name': name, 'params': param_list, 'body': stmts})

    # add pooled strings to globals
    for lab, val in str_pool.items():
        tu['globals'].append({'kind': 'string', 'name': lab, 'value': val})

    return tu


__all__ = ['code_to_translation_unit']
