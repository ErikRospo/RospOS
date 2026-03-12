def _imm_to_int(imm):
    if imm is None:
        return None
    if hasattr(imm, "value"):
        try:
            return int(imm.value)
        except Exception:
            pass
    try:
        return int(imm)
    except Exception:
        return None


def _debug_flags_from_node(node):
    flags = 0
    if getattr(node, "is_pseudo_expanded", False):
        flags |= 1 << 0
    if getattr(node, "is_from_rospocc", False):
        flags |= 1 << 1
    if getattr(node, "is_optimized", False):
        flags |= 1 << 2

    depth = int(getattr(node, "expansion_depth", 0) or 0)
    depth = max(0, min(depth, 31))
    flags |= depth << 3
    return flags


def _node_original_text(node):
    src = getattr(node, "src", None)
    if isinstance(src, dict) and src.get("original_text"):
        return src.get("original_text")
    return str(node)

