import re

from lark import Token


def copy_line(from_node, to_dict):
    """Copy _line metadata from source node to target dict."""
    if isinstance(from_node, dict) and "_line" in from_node:
        to_dict["_line"] = from_node["_line"]
    return to_dict


def find_number_in_node(node):
    if isinstance(node, dict):
        if "int" in node:
            return node["int"]
        if "token" in node and re.fullmatch(r"-?\d+|0x[0-9a-fA-F]+", node["token"]):
            try:
                return int(node["token"], 0)
            except Exception:
                return None
        for child in node.get("children", []):
            value = find_number_in_node(child)
            if value is not None:
                return value
    return None


def find_identifier(node):
    """Recursively find the first identifier token in a node."""
    if isinstance(node, dict):
        if (
            "token" in node
            and isinstance(node["token"], str)
            and node["token"].isidentifier()
        ):
            return node["token"]
        for child in node.get("children", []):
            result = find_identifier(child)
            if result is not None:
                return result
    return None


def node_name(value):
    """Normalize AST node names that may arrive as Lark Tokens."""
    if isinstance(value, Token):
        return str(value)
    return value
