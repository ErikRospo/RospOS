from dataclasses import dataclass
from typing import List, Optional, Union


# Immediate kinds
@dataclass(frozen=True)
class ImmValue:
    value: int


@dataclass(frozen=True)
class ImmLabel:
    name: str


@dataclass(frozen=True)
class ImmLabelPart:
    label: str
    part: str  # 'high' or 'low'


@dataclass(frozen=True)
class ImmLifted:
    name: str
    value: int


Immediate = Union[ImmValue, ImmLabel, ImmLabelPart, ImmLifted]


# Relocation entry: points to an instruction index and a field to patch
@dataclass
class Relocation:
    instr_index: int
    field: str  # e.g. 'imm'
    kind: str  # e.g. 'label', 'label_part', 'lifted'
    name: str


# Instruction dataclass (single uniform representation)
@dataclass
class Instruction:
    type: str  # 'r','i','l','b','j','s','p','a','d'
    name: str
    rd: Optional[int] = None
    rs1: Optional[int] = None
    rs2: Optional[int] = None
    imm: Optional[Immediate] = None
    # keep the original legacy dict for easy debugging/gradual migration
    legacy: Optional[dict] = None

    def copy_with(self, **kwargs) -> "Instruction":
        data = dict(
            type=self.type,
            name=self.name,
            rd=self.rd,
            rs1=self.rs1,
            rs2=self.rs2,
            imm=self.imm,
            legacy=self.legacy,
        )
        data.update(kwargs)
        return Instruction(**data)


@dataclass
class LabelDecl:
    name: str


@dataclass
class Directive:
    name: str
    imm: Optional[Immediate] = None
    length: Optional[int] = None


@dataclass
class Segment:
    addr: int
    data: bytearray


# Helper converters (from the legacy dict-shaped AST to typed IR)
def _imm_from_legacy(imm):
    if imm is None:
        return None
    if isinstance(imm, dict):
        if "value" in imm:
            return ImmValue(int(imm["value"]))
        if "name" in imm:
            return ImmLabel(imm["name"])
        if "label" in imm and "part" in imm:
            return ImmLabelPart(imm["label"], imm["part"])
        # lifted constants produced by transformer use type=='li'
        if imm.get("type") == "li":
            return ImmLifted(imm.get("name"), int(imm.get("value")))
        # fallback: attempt to coerce numeric-like
        try:
            return ImmValue(int(imm))
        except Exception:
            return imm
    # plain int
    if isinstance(imm, int):
        return ImmValue(imm)
    return imm


def instr_from_legacy(d: dict) -> Union[Instruction, LabelDecl, Directive]:
    t = d.get("type")
    if t == "a":
        return LabelDecl(name=d.get("name"))
    if t == "d":
        imm = _imm_from_legacy(d.get("imm"))
        return Directive(name=d.get("name"), imm=imm, length=d.get("len"))
    # instruction
    imm = _imm_from_legacy(d.get("imm"))
    # Some legacy nodes (e.g. `lli` pseudos) use the key 'reg' for the
    # destination register. Accept that for compatibility.
    rd_val = d.get("rd") if d.get("rd") is not None else d.get("reg")
    return Instruction(
        type=d.get("type"),
        name=d.get("name"),
        rd=rd_val,
        rs1=d.get("rs1"),
        rs2=d.get("rs2"),
        imm=imm,
        legacy=d,
    )


def instr_list_from_legacy(
    ast: List[dict],
) -> List[Union[Instruction, LabelDecl, Directive]]:
    return [instr_from_legacy(i) for i in ast]
