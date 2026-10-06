"""Shared struct-member resolution and memory-address emission."""

from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, Optional

import abi


@dataclass(frozen=True)
class MemberAccess:
    base_reg: Optional[str]
    struct_type: Optional[str]
    struct_def: Optional[Dict[str, Any]]
    member: Optional[Dict[str, Any]]
    description: str
    address_comment: str

    @property
    def offset(self) -> Optional[int]:
        return self.member.get("offset", 0) if self.member is not None else None


@contextmanager
def resolve_member_access(emitter, node: Dict[str, Any], out):
    """Resolve a validated . or -> node and release its evaluated pointer base.

    Missing type/member/register information is left in the result so callers
    can retain their existing expression and statement diagnostics.
    """
    base = node["base"]
    op = node["op"]
    member_name = node["member"]
    base_reg = emitter.emit_expr(base, out) if op == "->" else None
    try:
        base_name = base.get("name")
        struct_type = (
            emitter.var_types.get(base_name) if base.get("type") == "var" else None
        )
        if op == "->" and struct_type and "_ptr" in struct_type:
            struct_type = struct_type.replace("_ptr", "")

        struct_def = emitter.struct_types.get(struct_type)
        member = next(
            (
                item
                for item in (struct_def or {}).get("members", [])
                if item.get("name") == member_name
            ),
            None,
        )
        if op == "." and member is not None and member.get("offset", 0) is not None:
            base_reg = emitter.var_regs.get(base_name)
            if not base_reg and base_name in getattr(emitter, "_var_spill_labels", {}):
                base_reg = emitter._restore_spilled_var_reg(base_name, out)

        yield MemberAccess(
            base_reg=base_reg,
            struct_type=struct_type,
            struct_def=struct_def,
            member=member,
            description=(
                f"{base_name}.{member_name}" if op == "." else f"ptr->{member_name}"
            ),
            address_comment=f"{base_name} + offset" if op == "." else "ptr + offset",
        )
    finally:
        if op == "->":
            emitter.release_expr_reg(base_reg)


@contextmanager
def member_address(emitter, access: MemberAccess, out, comment: str):
    """Yield a base/offset pair, materializing large offsets only when needed."""
    if access.offset < 2**16:
        yield access.base_reg, access.offset
        return

    offset_reg = emitter.alloc_reg()
    addr_reg = None
    try:
        emitter._load_imm(offset_reg, access.offset, out)
        addr_reg = emitter.alloc_reg()
        out.write(
            f"  ADD {addr_reg}, {access.base_reg}, {offset_reg}    // {comment}\n"
        )
        yield addr_reg, 0
    finally:
        if offset_reg in abi.TEMP_REGS:
            emitter.free_reg(offset_reg)
        if addr_reg in abi.TEMP_REGS:
            emitter.free_reg(addr_reg)
