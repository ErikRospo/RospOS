from pathlib import Path

from transformer_context import TranslationUnitContext
from transformer_expr import ExpressionTransformer
from transformer_stmt import StatementTransformer
from transformer_utils import decode_string_token, find_identifier, node_name


class TranslationUnitTransformer:
    def __init__(self, source_file=None):
        self.ctx = TranslationUnitContext()
        if source_file:
            self.ctx.source_file = str(source_file)
        self.expr = ExpressionTransformer(self.ctx)
        self.stmt = StatementTransformer(self.ctx, self.expr)

    def transform(self, ast):
        self._walk(ast)
        return self.ctx.tu

    def _walk(self, node):
        res = []
        if not isinstance(node, dict):
            return res

        node_type = node.get("node")
        if node_type in ("translation_unit", "start"):
            for child in node.get("children", []):
                res.extend(self._walk(child))
            return res

        if node_type == "function_def":
            return self._handle_function_def(node)

        if node_type == "struct_decl":
            return self._handle_struct_decl(node)

        if node_type == "declaration":
            return self._handle_global_declaration(node)

        for child in node.get("children", []):
            res.extend(self._walk(child) or [])
        return res

    def _handle_function_def(self, node):
        children = node.get("children", [])
        name = None
        params = []
        param_types = {}
        return_type = None
        body_node = None
        is_inline = False

        for child in children:
            # Check for inline keyword (token with value "inline")
            if isinstance(child, dict) and child.get("token") == "inline":
                is_inline = True
            if isinstance(child, dict) and child.get("node") == "type_specifier":
                print("type_specifier children:", child.get("children", []))
                for type_child in child.get("children", []):
                    if isinstance(type_child, dict) and "node" in type_child:
                        return_type = node_name(type_child["node"])
            if isinstance(child, dict) and child.get("node") == "declarator":
                ident = find_identifier(child)
                if ident:
                    name = ident
            if isinstance(child, dict) and child.get("node") == "param_list":
                parsed_params, parsed_param_types = self._parse_param_list(child)
                params.extend(parsed_params)
                param_types.update(parsed_param_types)
            if isinstance(child, dict) and child.get("node") == "compound_stmt":
                body_node = child

        body = self.stmt.compound_to_stmts(body_node) if body_node else []

        fn = {"name": name or "fn", "params": params, "body": body}
        if param_types:
            fn["param_types"] = param_types
        if return_type:
            fn["return_type"] = return_type
        if is_inline:
            fn["inline"] = True
        fn["_line"] = node.get("_line")
        self.ctx.tu["functions"].append(fn)
        return [None]

    def _parse_param_list(self, param_list_node):
        params = []
        param_types = {}

        for param in param_list_node.get("children", []):
            if not (isinstance(param, dict) and param.get("node") == "param"):
                continue

            pname = None
            ptype = None
            pointer_seen = False

            for part in param.get("children", []):
                if isinstance(part, dict) and part.get("node") == "declarator":
                    for child in part.get("children", []):
                        if (
                            isinstance(child, dict)
                            and "token" in child
                            and child["token"].isidentifier()
                        ):
                            pname = child["token"]
                            break
                    if pname is None:
                        pname = find_identifier(part)

                    if pname:
                        for decl_child in part.get("children", []):
                            if (
                                isinstance(decl_child, dict)
                                and node_name(decl_child.get("node")) == "pointer"
                            ):
                                pointer_seen = True
                                break

            for part in param.get("children", []):
                if isinstance(part, dict) and part.get("node") == "type_specifier":
                    base_type = None
                    for type_child in part.get("children", []):
                        if isinstance(type_child, dict):
                            if "node" in type_child:
                                node_val = node_name(type_child["node"])
                                if node_val == "pointer":
                                    pointer_seen = True
                                elif isinstance(node_val, str):
                                    base_type = node_val
                            elif (
                                "token" in type_child
                                and type_child["token"].isidentifier()
                            ):
                                base_type = type_child["token"]

                    if base_type is not None:
                        if pointer_seen:
                            if base_type == "char":
                                ptype = "char_ptr"
                            elif base_type == "int":
                                ptype = "int_ptr"
                            else:
                                ptype = f"{base_type}_ptr"
                        else:
                            ptype = base_type
                    elif pointer_seen:
                        ptype = "pointer"

            if pname:
                params.append(pname)
                if ptype:
                    param_types[pname] = ptype

        return params, param_types

    def _parse_type_specifier(self, type_node):
        base_type = None
        pointer_count = 0

        if not isinstance(type_node, dict):
            return base_type, pointer_count

        for child in type_node.get("children", []):
            if isinstance(child, dict):
                if "node" in child:
                    node_val = node_name(child.get("node"))
                    if node_val == "pointer":
                        pointer_count += 1
                    elif isinstance(node_val, str):
                        base_type = node_val
                elif "token" in child and child["token"].isidentifier():
                    base_type = child["token"]

        return base_type, pointer_count

    def _count_declarator_pointers(self, declarator_node):
        count = 0
        if not isinstance(declarator_node, dict):
            return count

        for child in declarator_node.get("children", []):
            if isinstance(child, dict):
                if node_name(child.get("node")) == "pointer":
                    count += 1
                elif child.get("node") == "declarator":
                    count += self._count_declarator_pointers(child)

        return count

    def _extract_string_literal(self, node):
        if not isinstance(node, dict):
            return None

        token = node.get("token")
        if isinstance(token, str) and token.startswith('"') and token.endswith('"'):
            return decode_string_token(token)

        for child in node.get("children", []):
            value = self._extract_string_literal(child)
            if value is not None:
                return value

        return None

    def _extract_embed_path(self, node):
        if not isinstance(node, dict):
            return None

        if node.get("node") == "postfix":
            children = node.get("children", [])
            if children:
                primary = children[0]
                if (
                    isinstance(primary, dict)
                    and isinstance(primary.get("token"), str)
                    and primary["token"] in ("__embed", "__blob")
                ):
                    print(f"Found potential embed call: {primary['token']} at line {node.get('_line')}")
                    for suffix in children[1:]:
                        if not (
                            isinstance(suffix, dict)
                            and suffix.get("node") == "call_suffix"
                        ):
                            continue
                        for call_child in suffix.get("children", []):
                            if not (
                                isinstance(call_child, dict)
                                and call_child.get("node") == "arg_list"
                            ):
                                continue
                            args = [
                                arg
                                for arg in call_child.get("children", [])
                                if isinstance(arg, dict)
                            ]
                            if not args:
                                return None
                            return self._extract_string_literal(args[0])

        for child in node.get("children", []):
            value = self._extract_embed_path(child)
            if value is not None:
                return value

        return None

    def _handle_struct_decl(self, node):
        children = node.get("children", [])
        struct_name = None
        typedef_name = None
        members = []
        is_typedef = False

        for child in children:
            if isinstance(child, dict) and "token" in child:
                token = child["token"]
                if token == "typedef":
                    is_typedef = True
                elif token.isidentifier():
                    if struct_name is None:
                        struct_name = token
                    else:
                        typedef_name = token
            elif isinstance(child, dict) and child.get("node") == "struct_member":
                member_type = None
                member_names = []
                for member_child in child.get("children", []):
                    if (
                        isinstance(member_child, dict)
                        and member_child.get("node") == "type_specifier"
                    ):
                        for type_child in member_child.get("children", []):
                            if isinstance(type_child, dict):
                                if "node" in type_child:
                                    member_type = type_child["node"]
                                elif (
                                    "token" in type_child
                                    and type_child["token"].isidentifier()
                                ):
                                    member_type = type_child["token"]
                    elif (
                        isinstance(member_child, dict)
                        and member_child.get("node") == "init_declarator_list"
                    ):
                        for init_decl in member_child.get("children", []):
                            if isinstance(init_decl, dict):
                                name = find_identifier(init_decl)
                                if name:
                                    member_names.append(name)

                if member_type and member_names:
                    for name in member_names:
                        members.append({"name": name, "type": member_type})

        final_name = typedef_name if is_typedef and typedef_name else struct_name

        if final_name and members:
            offset = 0
            for member in members:
                member["offset"] = offset
                member["size"] = 4
                offset += 4

            self.ctx.tu["types"].append(
                {
                    "kind": "struct",
                    "name": final_name,
                    "members": members,
                    "size": offset,
                }
            )
        return []

    def _handle_global_declaration(self, node):
        children = node.get("children", [])
        t_spec = None
        t_pointer_count = 0
        init_list = None
        is_inline = False
        
        for child in children:
            # Check for inline keyword (token with value "inline")
            if isinstance(child, dict) and child.get("token") == "inline":
                is_inline = True
            if isinstance(child, dict) and child.get("node") == "type_specifier":
                t_spec, t_pointer_count = self._parse_type_specifier(child)
            if isinstance(child, dict) and child.get("node") == "init_declarator_list":
                init_list = child

        if not init_list:
            return []

        for init in init_list.get("children", []):
            if not (isinstance(init, dict) and init.get("node") == "init_declarator"):
                continue

            decl_children = init.get("children", [])
            name = None
            declarator_node = None
            init_node = None

            for decl_child in decl_children:
                if isinstance(decl_child, dict) and decl_child.get("node") == "declarator":
                    declarator_node = decl_child
                    ident = find_identifier(decl_child)
                    if ident:
                        name = ident
                elif isinstance(decl_child, dict) and init_node is None:
                    init_node = decl_child

            if not name or init_node is None:
                continue

            decl_pointer_count = self._count_declarator_pointers(declarator_node)
            total_pointer_count = t_pointer_count + decl_pointer_count

            embed_path = self._extract_embed_path(init_node)
            if embed_path is not None:
                print(f"Embedding blob for global '{name}' from path: {embed_path}")
                path_obj = Path(embed_path)
                if not path_obj.is_absolute():
                    path_obj = self.ctx.source_dir / path_obj
                path_obj = path_obj.resolve()

                if not path_obj.exists():
                    raise FileNotFoundError(
                        f"Embedded blob for global '{name}' not found: {path_obj}"
                    )

                blob_bytes = path_obj.read_bytes()
                self.ctx.tu["globals"].append(
                    {
                        "kind": "blob",
                        "name": name,
                        "value": blob_bytes,
                        "size": len(blob_bytes),
                        "source_path": str(path_obj),
                        "inline": is_inline,
                    }
                )
                continue

            if t_spec == "char" and total_pointer_count == 0:
                str_value = self._extract_string_literal(init_node)
                if str_value is not None:
                    global_entry = {"kind": "string", "name": name, "value": str_value}
                    if is_inline:
                        global_entry["inline"] = True
                    self.ctx.tu["globals"].append(global_entry)
                    continue
            
            # Handle inline constant variables (int, char, etc.)
            if is_inline and total_pointer_count == 0:
                const_value = self._extract_const_value(init_node)
                if const_value is not None:
                    global_entry = {
                        "kind": "inline_const",
                        "name": name,
                        "value": const_value,
                        "type": t_spec,
                        "inline": True,
                    }
                    self.ctx.tu["globals"].append(global_entry)
                    continue
        return []
    
    def _extract_const_value(self, node):
        """Extract a compile-time constant value from an expression node."""
        if not isinstance(node, dict):
            return None
        
        # Check for simple numeric constant
        if "token" in node:
            token = node.get("token")
            if isinstance(token, str):
                # Try to parse as integer
                try:
                    return int(token, 0)
                except ValueError:
                    pass
        
        # Recursively check children
        for child in node.get("children", []):
            value = self._extract_const_value(child)
            if value is not None:
                return value
        
        return None
