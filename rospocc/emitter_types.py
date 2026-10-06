"""Type-hint queries shared by expression and statement emission."""


def is_char_ptr_expr(emitter, expr):
    if not isinstance(expr, dict):
        return False

    et = expr.get("type")
    if et == "var":
        return emitter.var_types.get(expr.get("name")) == "char_ptr"

    if et == "binop" and expr.get("op") in ("plus", "minus"):
        return is_char_ptr_expr(emitter, expr.get("left")) or is_char_ptr_expr(
            emitter, expr.get("right")
        )

    return False
