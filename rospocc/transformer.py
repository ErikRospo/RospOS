import re
from typing import Any

from lark import Token, Transformer, Tree
from transformer_tu import TranslationUnitTransformer


class ASTTransformer(Transformer):

    def __default_token__(self, token: Token):
        tok = str(token)
        out: dict[str, Any] = {"token": tok}
        if re.fullmatch(r"0x[0-9a-fA-F]+|\d+", tok):
            try:
                out["int"] = int(tok, 0)
            except Exception:
                pass
        if tok.startswith('"') and tok.endswith('"') and len(tok) >= 2:
            out["str_val"] = tok[1:-1]
        if tok == "true":
            out["bool"] = True
        if tok == "false":
            out["bool"] = False
        if tok == "nullptr":
            out["null"] = True
        return out

    def __default__(self, data, children, meta):  # type: ignore[override]
        node = {"node": data, "children": children}

        import sys

        if meta and hasattr(meta, "line"):
            node["_line"] = meta.line
            print(f"DEBUG transformer: {data} -> line {meta.line}", file=sys.stderr)

        if data == "primary" and len(children) == 1:
            child = children[0]
            if isinstance(child, dict) and "_line" in node and "_line" not in child:
                child["_line"] = node["_line"]
            return child

        if data == "start" and len(children) == 1:
            return children[0]

        return node


def transform_tree(tree: Tree):
    """Transform a Lark `Tree` into the condensed dict form.

    Returns the transformed dict or the token-dict for Token inputs.
    """
    if isinstance(tree, Tree):
        return ASTTransformer().transform(tree)
    return tree


def transform_to_translation_unit(input_data: Tree) -> dict:
    ast = (
        transform_tree(input_data)
        if isinstance(input_data, (Tree, Token))
        else input_data
    )
    return TranslationUnitTransformer().transform(ast)


__all__ = ["ASTTransformer", "transform_tree", "transform_to_translation_unit"]
