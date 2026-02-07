"""Custom exceptions and helpers for rospoas error reporting.

Provide structured exception types for different failure modes and
helpers to format node/context information for clearer messages.
"""
from typing import Any


class AssemblerError(Exception):
    """Base class for assembler errors."""


class ParseError(AssemblerError):
    pass


class TransformError(AssemblerError):
    pass


class PreprocessError(AssemblerError):
    pass


class LayoutError(AssemblerError):
    pass


class EncodeError(AssemblerError):
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
