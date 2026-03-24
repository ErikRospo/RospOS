from __future__ import annotations

import gzip
import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, DefaultDict

from debug_writer import DebugInfoWriter, RegisterAllocation, collect_debug_segments
from encode import encode_ir
from grammar_parser import parse_source, preprocess_includes
from layout import layout_ir
from lower import lower_ir
from optimizer import optimize
from register_alloc_reader import RegisterAllocInfoReader
from transformer import transform_parse_tree_ir

MAGIC = 0x50534F52  # 'ROSP' in little-endian
SEGMENT_FLAG_LOADABLE = 0x00000001
SEGMENT_FLAG_DEBUG = 0x00000002
SEGMENT_FLAG_COMPRESSED = 0x00000004

CompilationStepHandler = Callable[["CompilationState"], None]


@dataclass(frozen=True)
class CompilationFrontend:
    name: str
    extensions: tuple[str, ...]
    preprocess: Callable[[str, str], tuple[list[str], Any]]
    parse: Callable[[str], Any]
    transform: Callable[[Any, Any, bool], tuple[list[Any], Any]]


@dataclass(frozen=True)
class CompilationOptions:
    input_path: Path
    output_path: Path
    optimize: bool
    compress_debug: bool
    compress_bin: bool
    bin_version: int
    rospocc_mapping: bool
    segment_debug: bool
    verbose: bool
    debug_enabled: dict[str, bool]


@dataclass
class CompilationState:
    frontend: CompilationFrontend
    options: CompilationOptions
    source_code: str = ""
    pre_lines: list[str] = field(default_factory=list)
    origin_map: Any = None
    preprocessed_code: str = ""
    parse_tree: Any = None
    ir_list: list[Any] = field(default_factory=list)
    lifted_constants: list[Any] = field(default_factory=list)
    pre_optimization_ir: list[Any] = field(default_factory=list)
    optimization_logs: list[str] = field(default_factory=list)
    addresses: dict[str, int] = field(default_factory=dict)
    segments: list[tuple[int, bytearray]] = field(default_factory=list)
    debug_writers: dict[int, DebugInfoWriter] = field(default_factory=dict)
    debug_segments: list[tuple[int, str]] = field(default_factory=list)
    register_alloc_reader: RegisterAllocInfoReader = field(
        default_factory=RegisterAllocInfoReader
    )

    def artifact_path(self, suffix: str) -> Path:
        return self.options.output_path.with_name(
            f"{self.options.output_path.stem}_{suffix}"
        )

    def output_dir_path(self, filename: str) -> Path:
        return self.options.output_path.parent / filename


class CompilationPipeline:
    def __init__(self):
        self._handlers: DefaultDict[str, list[CompilationStepHandler]] = defaultdict(
            list
        )

    def register_handler(self, step: str, handler: CompilationStepHandler) -> None:
        self._handlers[step].append(handler)

    def emit(self, step: str, state: CompilationState) -> None:
        for handler in self._handlers.get(step, []):
            handler(state)

    def compile(
        self, frontend: CompilationFrontend, options: CompilationOptions
    ) -> CompilationState:
        state = CompilationState(frontend=frontend, options=options)

        with open(options.input_path, "r", encoding="utf-8") as handle:
            state.source_code = handle.read()
        self.emit("source_loaded", state)

        # Try to load register allocation info from companion file
        if options.input_path.suffix == ".ros":
            regalloc_path = options.input_path.with_suffix(".rosc.regalloc")
            if regalloc_path.exists():
                state.register_alloc_reader.load_from_file(str(regalloc_path))

        state.pre_lines, state.origin_map = frontend.preprocess(
            state.source_code, str(options.input_path)
        )
        state.preprocessed_code = "\n".join(state.pre_lines)
        self.emit("preprocessed", state)

        state.parse_tree = frontend.parse(state.preprocessed_code)
        self.emit("parsed", state)

        state.ir_list, state.lifted_constants = frontend.transform(
            state.parse_tree, state.origin_map, options.verbose
        )
        self.emit("transformed", state)

        if options.optimize:
            state.pre_optimization_ir = list(state.ir_list)
            state.ir_list, state.optimization_logs = optimize(state.ir_list)
        self.emit("optimized", state)

        state.ir_list = lower_ir(state.ir_list)
        self.emit("lowered", state)

        state.addresses, state.segments = layout_ir(state.ir_list)
        self.emit("laid_out", state)

        state.debug_writers = collect_debug_segments(state.ir_list)
        self.emit("debug_info_collected", state)

        # Enrich debug info with register allocations if available
        enrich_debug_with_register_allocs(state)

        try:
            state.segments = encode_ir(
                state.ir_list, state.addresses, state.segments, options.verbose
            )
        except Exception as exc:
            raise RuntimeError(f"Error during encoding: {exc}") from exc
        self.emit("encoded", state)

        if options.segment_debug:
            state.debug_segments = build_debug_segments(
                state.segments, state.debug_writers
            )
        self.emit("debug_segments_built", state)

        write_binary(state)
        self.emit("binary_written", state)
        return state


def build_frontend_registry() -> dict[str, CompilationFrontend]:
    frontend = CompilationFrontend(
        name="rospoas",
        extensions=(".ros",),
        preprocess=preprocess_includes,
        parse=parse_source,
        transform=transform_parse_tree_ir,
    )
    return {frontend.name: frontend}


def select_frontend(
    frontends: dict[str, CompilationFrontend], input_path: Path
) -> CompilationFrontend:
    suffix = input_path.suffix.lower()
    for frontend in frontends.values():
        if suffix in frontend.extensions:
            return frontend
    supported = ", ".join(
        sorted(
            extension
            for frontend in frontends.values()
            for extension in frontend.extensions
        )
    )
    raise ValueError(
        f"No compilation frontend registered for '{input_path.suffix}'. Supported extensions: {supported}"
    )


def build_debug_segments(
    segments: list[tuple[int, bytearray]], debug_writers: dict[int, DebugInfoWriter]
) -> list[tuple[int, str]]:
    debug_segments = []
    for segment_address, _segment_data in segments:
        writer = debug_writers.get(segment_address, DebugInfoWriter())
        debug_text = writer.write_debug_segment(segment_address)
        debug_segments.append((segment_address, debug_text))
    return debug_segments


def enrich_debug_with_register_allocs(state: CompilationState) -> None:
    """Attach compiler register-allocation metadata to assembled instruction addresses."""
    if not state.register_alloc_reader.get_all_allocations():
        return

    for _segment_addr, writer in state.debug_writers.items():
        for entry in writer.entries:
            pp_line_raw: Any = entry.get("pp_line", 0)
            try:
                pp_line = int(str(pp_line_raw))
            except Exception:
                pp_line = 0
            if pp_line <= 0:
                continue

            allocs = state.register_alloc_reader.get_allocations_for_line(pp_line)
            if not allocs:
                continue

            addr_raw: Any = entry.get("address", 0)
            try:
                addr = int(str(addr_raw))
            except Exception:
                addr = 0
            for alloc in allocs:
                if alloc.action == "free":
                    continue
                writer.add_register_allocation(
                    addr,
                    RegisterAllocation(
                        register=alloc.register,
                        variable_name=alloc.variable_name,
                        variable_type=alloc.variable_type,
                        var_kind=alloc.var_kind,
                        origin=alloc.origin,
                    ),
                )


def write_binary(state: CompilationState) -> None:
    if state.options.bin_version == 1:
        _write_v1_binary(state)
        return
    if state.options.bin_version == 2:
        _write_v2_binary(state)
        return
    raise ValueError(f"Unsupported binary version: {state.options.bin_version}")


def _write_v1_binary(state: CompilationState) -> None:
    with open(state.options.output_path, "wb") as handle:
        handle.write(struct.pack("<III", MAGIC, 1, len(state.segments)))
        for address, data in state.segments:
            handle.write(struct.pack("<II", address, len(data)))
            handle.write(data)


def _write_v2_binary(state: CompilationState) -> None:
    total_segment_count = len(state.segments) + len(state.debug_segments)
    with open(state.options.output_path, "wb") as handle:
        handle.write(struct.pack("<III", MAGIC, 2, total_segment_count))

        for address, data in state.segments:
            flags = SEGMENT_FLAG_LOADABLE
            if state.options.compress_bin:
                data = gzip.compress(data, mtime=0)
                flags |= SEGMENT_FLAG_COMPRESSED
            handle.write(struct.pack("<III", flags, address, len(data)))
            handle.write(data)

        for parent_address, debug_text in state.debug_segments:
            debug_bytes = debug_text.encode("utf-8")
            flags = SEGMENT_FLAG_DEBUG
            if state.options.compress_debug:
                debug_bytes = gzip.compress(debug_bytes, mtime=0)
                flags |= SEGMENT_FLAG_COMPRESSED
            handle.write(struct.pack("<III", flags, parent_address, len(debug_bytes)))
            handle.write(debug_bytes)
