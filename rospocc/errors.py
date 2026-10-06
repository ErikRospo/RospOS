
from typing import Any


class CompilerError(Exception):
    """Base class for compiler errors."""


class EmitterError(CompilerError):
    pass
class ExprEmitterError(EmitterError):
    pass
class StmtEmitterError(EmitterError):
    pass

def fmt_node(node: Any) -> str:
    """Return a short human-readable representation of a node or object.

    This is used to embed helpful context into error messages without
    dumping large structures.
    """
    try:
        # For legacy dict-shaped nodes, include type/name if present
        if isinstance(node, dict):
            # If the node contains source info, include it
            src = node.get("src") if isinstance(node, dict) else None
            if isinstance(src, dict) and src.get("file"):
                src_str = f"{src.get('file')}:{src.get('line')}"
            else:
                src_str = None
            t = node.get("type")
            name = node.get("name") or node.get("d") or node.get("reg")
            if t and name is not None:
                base = f"{{type={t}, name={name}}}"
                return f"{base} @ {src_str}" if src_str else base
            if t:
                base = f"{{type={t}}}"
                return f"{base} @ {src_str}" if src_str else base
            return f"{str(node)} @ {src_str}" if src_str else str(node)
        # For dataclasses from ir.py, attempt to show key attributes
        if hasattr(node, "name"):
            return f"<{node.__class__.__name__} name={getattr(node, 'name', None)}>"
        if hasattr(node, "type") and hasattr(node, "name"):
            return f"<{node.__class__.__name__} type={node.type} name={node.name}>"
        return str(node)
    except Exception:
        return repr(node)