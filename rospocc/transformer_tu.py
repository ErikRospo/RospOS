from transformer_context import TranslationUnitContext
from transformer_expr import ExpressionTransformer
from transformer_stmt import StatementTransformer
from transformer_utils import find_identifier, node_name


class TranslationUnitTransformer:
    def __init__(self):
        self.ctx = TranslationUnitContext()
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

        for child in children:
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
        init_list = None
        for child in children:
            if isinstance(child, dict) and child.get("node") == "type_specifier":
                for type_child in child.get("children", []):
                    if isinstance(type_child, dict) and "token" in type_child:
                        t_spec = type_child["token"]
            if isinstance(child, dict) and child.get("node") == "init_declarator_list":
                init_list = child
        if t_spec == "char" and init_list:
            for init in init_list.get("children", []):
                if isinstance(init, dict) and init.get("node") == "init_declarator":
                    decl_children = init.get("children", [])
                    name = None
                    val = None
                    for decl_child in decl_children:
                        if (
                            isinstance(decl_child, dict)
                            and decl_child.get("node") == "declarator"
                        ):
                            ident = find_identifier(decl_child)
                            if ident:
                                name = ident
                        if (
                            isinstance(decl_child, dict)
                            and "token" in decl_child
                            and decl_child["token"].startswith('"')
                        ):
                            val = decl_child["token"][1:-1]
                    if name and val is not None:
                        self.ctx.tu["globals"].append(
                            {"kind": "string", "name": name, "value": val}
                        )
        return []
