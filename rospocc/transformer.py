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


__all__ = ["ASTTransformer", "transform_tree"]
