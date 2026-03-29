from __future__ import annotations

import json
from typing import Any

from compilation_pipeline import CompilationPipeline, CompilationState
from ir import Directive, ImmLabel, ImmLabelPart, ImmLifted, ImmValue
from ir import Instruction as IRInstruction
from ir import LabelDecl
from utility import _imm_to_int


def register_debug_handlers(pipeline: CompilationPipeline) -> None:
    pipeline.register_handler("preprocessed", _write_preprocessed)
    pipeline.register_handler("parsed", _write_parse_tree)
    pipeline.register_handler("optimized", _write_optimization_artifacts)
    pipeline.register_handler("lowered", _write_ir_and_ast)
    pipeline.register_handler("laid_out", _write_layout)
    pipeline.register_handler("encoded", _write_mapping)
    pipeline.register_handler("debug_segments_built", _write_debug_segments)


def _write_preprocessed(state: CompilationState) -> None:
    if not state.options.debug_enabled["preprocessed"]:
        return
    _write_text(state.artifact_path("preprocessed.ros"), state.preprocessed_code)


def _write_parse_tree(state: CompilationState) -> None:
    if not state.options.debug_enabled["parse"]:
        return
    _write_text(state.artifact_path("parse.txt"), str(state.parse_tree.pretty()))


def _write_optimization_artifacts(state: CompilationState) -> None:
    if not state.options.optimize:
        return
    _write_ir_list(
        state.output_dir_path("debug_before_opt.txt"), state.pre_optimization_ir
    )
    _write_ir_list(state.output_dir_path("debug_after_opt.txt"), state.ir_list)
    _write_ir_assembly(state.output_dir_path("debug_after_opt.ros"), state.ir_list)
    log_text = (
        "\n".join(state.optimization_logs)
        if state.optimization_logs
        else "No optimization transforms applied."
    )
    _write_text(state.output_dir_path("debug_opt_log.txt"), log_text + "\n")


def _write_ir_and_ast(state: CompilationState) -> None:
    if state.options.debug_enabled["ir"]:
        _write_ir_list(state.artifact_path("ir.txt"), state.ir_list)
    if state.options.debug_enabled["ast"]:
        with open(state.artifact_path("ast.json"), "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "ir": state.ir_list,
                    "lifted_constants": state.lifted_constants,
                },
                handle,
                indent=4,
                default=str,
            )


def _write_layout(state: CompilationState) -> None:
    if not state.options.debug_enabled["layout"]:
        return
    lines = ["Segments:"]
    for segment_address, segment_data in state.segments:
        lines.append(f"0x{segment_address:08X} size={len(segment_data)}")
    lines.append("")
    lines.append("Labels:")
    for label, address in sorted(state.addresses.items(), key=lambda kv: kv[1]):
        lines.append(f"{label} -> 0x{address:08X}")
    _write_text(state.artifact_path("layout.txt"), "\n".join(lines) + "\n")


def _write_mapping(state: CompilationState) -> None:
    if not state.options.debug_enabled["mapping"]:
        return
    with open(state.artifact_path("mapping.txt"), "w", encoding="utf-8") as handle:
        handle.write("Node mapping:\n")
        current_segment = None
        current_cursor = 0
        for index, node in enumerate(state.ir_list):
            if isinstance(node, Directive) and node.name == "seg":
                segment_address = _imm_to_int(node.imm)
                if segment_address is None:
                    segment_address = 0
                current_segment = segment_address
                current_cursor = 0
                handle.write(f"SEGMENT {hex(current_segment)}\n")
                continue

            if current_segment is None:
                current_segment = 0

            if isinstance(node, LabelDecl):
                address = state.addresses.get(
                    node.name, current_segment + current_cursor
                )
                handle.write(
                    f"LABEL {node.name} -> {hex(address)} src={_format_src(node)}\n"
                )
                current_cursor = max(current_cursor, address - current_segment)
                continue

            if isinstance(node, Directive) and node.name == "data":
                size = _data_size(node)
                handle.write(
                    f"DATA @ {hex(current_segment + current_cursor)} size {size}: {node.imm} src={_format_src(node)}\n"
                )
                current_cursor += size
                continue

            if isinstance(node, IRInstruction):
                align = (4 - (current_cursor % 4)) % 4
                if align:
                    current_cursor += align
                handle.write(
                    "INSTR idx={idx:05d} @ {addr:08x} name={name} rd={rd} rs1={rs1} rs2={rs2} imm={imm} raw={raw} src={src}\n".format(
                        idx=index,
                        addr=current_segment + current_cursor,
                        name=node.name,
                        rd=_display_operand(node.rd),
                        rs1=_display_operand(node.rs1),
                        rs2=_display_operand(node.rs2),
                        imm=_display_operand(node.imm),
                        raw=node,
                        src=_format_instruction_src(node),
                    )
                )
                current_cursor += 4
                continue

            handle.write(f"UNKNOWN NODE {node}\n")


def _write_debug_segments(state: CompilationState) -> None:
    if not state.options.debug_enabled["segments"] or not state.debug_segments:
        return
    with open(
        state.artifact_path("debug_segments.txt"), "w", encoding="utf-8"
    ) as handle:
        for segment_address, debug_text in state.debug_segments:
            handle.write(f"=== SEGMENT 0x{segment_address:08X} ===\n")
            handle.write(debug_text)
            handle.write("\n")


def _write_text(path, text: str) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def _write_ir_list(path, ir_list: list[Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        for node in ir_list:
            handle.write(str(node) + "\n")


def _write_ir_assembly(path, ir_list: list[Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        previous_kind = None
        previous_node=None
        for node in ir_list:
            line = _ir_node_to_assembly(node)
            if line is None:
                continue
            current_kind = _ir_node_kind(node)
            if (
                previous_kind in {"label", "directive"}
                or (isinstance(previous_node, IRInstruction) and previous_node.name.upper() in {"JMP"})
            ):
                handle.write("\n")
            handle.write(line + "\n")
            previous_kind = current_kind
            previous_node = node


def _ir_node_kind(node: Any) -> str:
    if isinstance(node, LabelDecl):
        return "label"
    if isinstance(node, Directive):
        return "directive"
    if isinstance(node, IRInstruction):
        return "instruction"
    return "other"


def _ir_node_to_assembly(node: Any) -> str | None:
    if isinstance(node, LabelDecl):
        return f"{node.name}:"

    if isinstance(node, Directive):
        return _directive_to_assembly(node)

    if isinstance(node, IRInstruction):
        return _instruction_to_assembly(node)

    return None


def _directive_to_assembly(node: Directive) -> str:
    name = str(node.name).upper()

    if name == "SEG":
        return f".SEG {_immediate_to_assembly(node.imm)}"

    if name == "SPACE":
        if node.length is not None:
            return f".SPACE {int(node.length)}"
        return f".SPACE {_immediate_to_assembly(node.imm)}"

    if name == "DATA":
        if isinstance(node.imm, bytes):
            hex_bytes = " ".join(f"0x{byte:02X}" for byte in node.imm)
            return f".DATA {hex_bytes}"
        return f".DATA {_immediate_to_assembly(node.imm)}"

    if node.imm is not None:
        return f".{name} {_immediate_to_assembly(node.imm)}"
    return f".{name}"


def _instruction_to_assembly(node: IRInstruction) -> str:
    mnemonic = str(node.name).upper()
    t = node.type
    indent = "  "

    if t == "s":
        return f"{indent}{mnemonic}"

    if t == "r":
        return (
            f"{indent}"
            f"{mnemonic} {_register_to_assembly(node.rd)}, "
            f"{_register_to_assembly(node.rs1)}, {_register_to_assembly(node.rs2)}"
        )

    if t in {"i", "l", "b"}:
        return (
            f"{indent}"
            f"{mnemonic} {_register_to_assembly(node.rd)}, "
            f"{_register_to_assembly(node.rs1)}, {_immediate_to_assembly(node.imm)}"
        )

    if t == "j":
        rs1 = node.rs1 if node.rs1 is not None else 0
        return (
            f"{indent}"
            f"{mnemonic} {_register_to_assembly(node.rd)}, "
            f"{_register_to_assembly(rs1)}, {_immediate_to_assembly(node.imm)}"
        )

    if t == "p":
        if mnemonic in {"PUSH", "POP"}:
            return f"{indent}{mnemonic} {_register_to_assembly(_imm_to_int(node.imm))}"
        if mnemonic == "RET":
            return f"{indent}{mnemonic}"
        if mnemonic == "JMP":
            return f"{indent}{mnemonic} {_immediate_to_assembly(node.imm)}"
        if mnemonic == "LLI":
            return f"{indent}{mnemonic} {_register_to_assembly(node.rd)}, {_immediate_to_assembly(node.imm)}"

    parts: list[str] = []
    if node.rd is not None:
        parts.append(_register_to_assembly(node.rd))
    if node.rs1 is not None:
        parts.append(_register_to_assembly(node.rs1))
    if node.rs2 is not None:
        parts.append(_register_to_assembly(node.rs2))
    if node.imm is not None:
        parts.append(_immediate_to_assembly(node.imm))
    return f"{indent}{mnemonic} {', '.join(parts)}" if parts else f"{indent}{mnemonic}"


def _register_to_assembly(reg: Any) -> str:
    if reg is None:
        return "r0"
    return f"r{int(reg)}"


def _immediate_to_assembly(imm: Any) -> str:
    if imm is None:
        return "0"
    if isinstance(imm, ImmValue):
        return str(int(imm.value))
    if isinstance(imm, ImmLabel):
        return imm.name
    if isinstance(imm, ImmLabelPart):
        return f"{imm.label}_{imm.part}"
    if isinstance(imm, ImmLifted):
        return str(int(imm.value))
    if isinstance(imm, bytes):
        return " ".join(f"0x{byte:02X}" for byte in imm)
    try:
        return str(int(imm))
    except Exception:
        return str(imm)


def _format_src(node) -> str:
    src = getattr(node, "src", None)
    if isinstance(src, dict) and src.get("file"):
        return f"{src.get('file')}:{src.get('line')}"
    return "<unknown>"


def _format_instruction_src(node: IRInstruction) -> str:
    legacy = getattr(node, "legacy", None)
    src = legacy.get("src") if isinstance(legacy, dict) else None
    if src is None:
        src = getattr(node, "src", None)
    if isinstance(src, dict) and src.get("file"):
        return f"{src.get('file')}:{src.get('line')}"
    return "<unknown>"


def _display_operand(value):
    if isinstance(value, ImmValue):
        return _imm_to_int(value)
    return value


def _data_size(node: Directive) -> int:
    if node.length is not None:
        size = int(node.length)
    else:
        immediate = _imm_to_int(node.imm)
        if immediate is not None:
            size = (immediate.bit_length() // 8) + 1
        else:
            size = 4
    return max(4, size)
