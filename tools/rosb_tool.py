#!/usr/bin/env python3
"""Convert between flat .bin images and ROSB block-device files.

ROSB format (current VM implementation):
- header:
  - magic       u32  ("ROSB" -> 0x42534F52)
  - version     u32  (1)
  - block_count u32
  - index_off   u64
- records (variable count):
  - block_id    u32
  - flags       u32  (bit 0 = compressed)
  - size        u32  (payload bytes)
  - payload     bytes
- index section at index_off:
  - count       u32
  - entries[count]:
    - block_id    u32
    - rec_offset  u64

All integers are little-endian.
"""

from __future__ import annotations

import argparse
import bisect
import gzip
import math
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, List, Sequence, Tuple

MAGIC = 0x42534F52
VERSION = 1

BLOCK_SIZE = 512
COMPRESS_FLAG = 1 << 0

HEADER_FMT = "<IIIQ"
HEADER_SIZE = struct.calcsize(HEADER_FMT)
RECORD_HEADER_FMT = "<III"
RECORD_HEADER_SIZE = struct.calcsize(RECORD_HEADER_FMT)
INDEX_COUNT_FMT = "<I"
INDEX_ENTRY_FMT = "<IQ"
INDEX_ENTRY_SIZE = struct.calcsize(INDEX_ENTRY_FMT)


@dataclass(frozen=True)
class Header:
    magic: int
    version: int
    block_count: int
    index_offset: int


@dataclass(frozen=True)
class IndexEntry:
    block_id: int
    record_offset: int


@dataclass(frozen=True)
class BlockRecord:
    block_id: int
    flags: int
    payload: bytes


def _read_exact(f: BinaryIO, n: int) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise ValueError(f"Unexpected EOF while reading {n} bytes")
    return data


def _read_header(f: BinaryIO) -> Header:
    raw = _read_exact(f, HEADER_SIZE)
    magic, version, block_count, index_offset = struct.unpack(HEADER_FMT, raw)
    return Header(
        magic=magic, version=version, block_count=block_count, index_offset=index_offset
    )


def _write_header(f: BinaryIO, block_count: int, index_offset: int) -> None:
    f.write(struct.pack(HEADER_FMT, MAGIC, VERSION, block_count, index_offset))


def _read_index(f: BinaryIO, header: Header, file_size: int) -> List[IndexEntry]:
    if header.index_offset >= file_size:
        raise ValueError("ROSB index offset is outside file")

    f.seek(header.index_offset)
    count_raw = _read_exact(f, struct.calcsize(INDEX_COUNT_FMT))
    (count,) = struct.unpack(INDEX_COUNT_FMT, count_raw)

    entries: List[IndexEntry] = []
    for _ in range(count):
        raw = _read_exact(f, INDEX_ENTRY_SIZE)
        block_id, record_offset = struct.unpack(INDEX_ENTRY_FMT, raw)
        if record_offset + RECORD_HEADER_SIZE > file_size:
            raise ValueError(
                f"Invalid record offset {record_offset} for block {block_id}"
            )
        entries.append(IndexEntry(block_id=block_id, record_offset=record_offset))

    entries.sort(key=lambda e: e.block_id)

    dedup: List[IndexEntry] = []
    for entry in entries:
        if dedup and dedup[-1].block_id == entry.block_id:
            dedup[-1] = entry
        else:
            dedup.append(entry)

    return dedup


def _read_record_at(f: BinaryIO, record_offset: int) -> BlockRecord:
    f.seek(record_offset)
    raw = _read_exact(f, RECORD_HEADER_SIZE)
    block_id, flags, payload_size = struct.unpack(RECORD_HEADER_FMT, raw)
    if payload_size == 0:
        raise ValueError(f"Record at offset {record_offset} has empty payload")
    payload = _read_exact(f, payload_size)
    return BlockRecord(block_id=block_id, flags=flags, payload=payload)


def _decode_block_payload(record: BlockRecord) -> bytes:
    if record.flags & COMPRESS_FLAG:
        try:
            data = gzip.decompress(record.payload)
        except (OSError, EOFError) as exc:
            raise ValueError(
                f"Failed to decompress block {record.block_id}: {exc}"
            ) from exc
    else:
        data = record.payload

    if len(data) != BLOCK_SIZE:
        raise ValueError(
            f"Block {record.block_id} resolved to {len(data)} bytes, expected {BLOCK_SIZE}"
        )
    return data


def _encode_block_payload(block: bytes, mode: str) -> Tuple[int, bytes]:
    if len(block) != BLOCK_SIZE:
        raise ValueError(
            f"Internal error: block size is {len(block)}, expected {BLOCK_SIZE}"
        )

    if mode == "never":
        return 0, block

    compressed = gzip.compress(block)

    if mode == "always":
        return COMPRESS_FLAG, compressed

    if len(compressed) < len(
        block
    ):  # If mode==auto, only compress if strictly saves space
        return COMPRESS_FLAG, compressed
    return 0, block


def _find_entry(entries: Sequence[IndexEntry], block_id: int) -> IndexEntry | None:
    ids = [e.block_id for e in entries]
    idx = bisect.bisect_left(ids, block_id)
    if idx >= len(entries) or entries[idx].block_id != block_id:
        return None
    return entries[idx]


def _use_color(mode: str) -> bool:
    if mode == "always":
        return True
    if mode == "never":
        return False
    # mode == "auto"
    return sys.stdout.isatty() and "NO_COLOR" not in __import__("os").environ


def _color(text: str, code: str, enabled: bool) -> str:
    if not enabled:
        return text
    return f"\033[{code}m{text}\033[0m"


def _hexdump_c_lines(
    data: bytes, base_offset: int = 0, color: bool = False
) -> List[str]:
    lines: List[str] = []
    for i in range(0, len(data), 16):
        chunk = data[i : i + 16]
        hex_cells = [f"{b:02x}" for b in chunk]

        left = " ".join(hex_cells[:8])
        right = " ".join(hex_cells[8:])
        # Match hexdump -C style grouping around 8-byte boundary.
        hex_part = f"{left:<23}  {right:<23}"

        ascii_part = "".join(chr(b) if 32 <= b <= 126 else "." for b in chunk)
        ascii_part = f"{ascii_part:<16}"

        offset_text = _color(f"{base_offset + i:08x}", "36", color)
        hex_text = _color(hex_part, "32", color)
        ascii_text = _color(f"|{ascii_part}|", "33", color)
        lines.append(f"{offset_text}  {hex_text}  {ascii_text}")

    lines.append(_color(f"{base_offset + len(data):08x}", "36", color))
    return lines


def bin_to_rosb(args: argparse.Namespace) -> int:
    src = Path(args.input)
    dst = Path(args.output)

    data = src.read_bytes()
    block_count = 0 if len(data) == 0 else math.ceil(len(data) / BLOCK_SIZE)

    records: List[Tuple[int, int, bytes]] = []
    for i in range(block_count):
        block_id = args.start_block_id + i
        start = i * BLOCK_SIZE
        chunk = data[start : start + BLOCK_SIZE]
        if len(chunk) < BLOCK_SIZE:
            chunk = chunk + bytes(BLOCK_SIZE - len(chunk))
        flags, payload = _encode_block_payload(chunk, args.compress)
        records.append((block_id, flags, payload))

    with dst.open("wb") as f:
        _write_header(f, block_count=0, index_offset=0)

        index_entries: List[IndexEntry] = []
        for block_id, flags, payload in records:
            record_offset = f.tell()
            f.write(struct.pack(RECORD_HEADER_FMT, block_id, flags, len(payload)))
            f.write(payload)
            index_entries.append(
                IndexEntry(block_id=block_id, record_offset=record_offset)
            )

        index_offset = f.tell()
        f.write(struct.pack(INDEX_COUNT_FMT, len(index_entries)))
        for entry in index_entries:
            f.write(struct.pack(INDEX_ENTRY_FMT, entry.block_id, entry.record_offset))

        f.seek(0)
        _write_header(f, block_count=len(index_entries), index_offset=index_offset)

    print(
        f"Wrote ROSB: {dst} | bytes={len(data)} blocks={len(index_entries)} "
        f"start_block_id={args.start_block_id}"
    )
    return 0


def rosb_to_bin(args: argparse.Namespace) -> int:
    src = Path(args.input)
    dst = Path(args.output)

    with src.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)

        header = _read_header(f)
        if header.magic != MAGIC:
            raise ValueError("Invalid ROSB magic")
        if header.version != VERSION:
            raise ValueError(f"Unsupported ROSB version: {header.version}")

        entries = _read_index(f, header, file_size)

        if not entries:
            dst.write_bytes(b"")
            print(f"Wrote BIN: {dst} | source had no blocks")
            return 0

        if args.start_block_id is None:
            start_block_id = entries[0].block_id
        else:
            start_block_id = args.start_block_id

        if args.block_count is None:
            max_block_id = entries[-1].block_id
            block_count = (
                (max_block_id - start_block_id + 1)
                if max_block_id >= start_block_id
                else 0
            )
        else:
            block_count = args.block_count

        if block_count < 0:
            raise ValueError("block_count must be >= 0")

        out = bytearray()
        for i in range(block_count):
            block_id = start_block_id + i
            entry = _find_entry(entries, block_id)
            if entry is None:
                out.extend(b"\x00" * BLOCK_SIZE)
                continue

            record = _read_record_at(f, entry.record_offset)
            if record.block_id != block_id:
                raise ValueError(
                    f"Index mismatch for block {block_id}: record contains {record.block_id}"
                )
            block_data = _decode_block_payload(record)
            out.extend(block_data)

    if args.trim_trailing_zeros:
        while out and out[-1] == 0:
            out.pop()

    dst.write_bytes(bytes(out))

    print(
        f"Wrote BIN: {dst} | bytes={len(out)} blocks={block_count} "
        f"start_block_id={start_block_id}"
    )
    return 0


def rosb_list(args: argparse.Namespace) -> int:
    src = Path(args.input)
    color = _use_color(args.color)

    key = lambda s: _color(s, "1;34", color)
    warn = lambda s: _color(s, "1;33", color)
    err = lambda s: _color(s, "1;31", color)
    ok = lambda s: _color(s, "1;32", color)

    with src.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)
        print(f"{key('file')}={src}")
        print(f"{key('header')}:")

        header = _read_header(f)
        if header.magic != MAGIC:
            print(err(f"Invalid ROSB magic: 0x{header.magic:08X}"))
            raise ValueError("Invalid ROSB magic")
        print(f"  magic=0x{header.magic:08X}")
        if header.version != VERSION:
            print(err(f"Unsupported ROSB version: {header.version}"))
            raise ValueError(f"Unsupported ROSB version: {header.version}")
        print(f"  version={header.version}")
        print(f"  block_count={header.block_count}")
        print(f"  file_size={file_size}")
        print(f"  index_offset={header.index_offset}")

        # Read raw index first so we can show duplicate/unsorted details as stored on disk.
        if header.index_offset >= file_size:
            raise ValueError("Corrupt ROSB: index offset is outside file")

        f.seek(header.index_offset)
        count_raw = _read_exact(f, struct.calcsize(INDEX_COUNT_FMT))
        (raw_index_count,) = struct.unpack(INDEX_COUNT_FMT, count_raw)

        raw_entries: List[IndexEntry] = []
        for _ in range(raw_index_count):
            raw = _read_exact(f, INDEX_ENTRY_SIZE)
            block_id, record_offset = struct.unpack(INDEX_ENTRY_FMT, raw)
            raw_entries.append(
                IndexEntry(block_id=block_id, record_offset=record_offset)
            )

        dedup_entries = _read_index(f, header, file_size)

        unique_ids = {entry.block_id for entry in raw_entries}
        print(f"{key('index')}:")
        print(f"  raw_count={len(raw_entries)}")
        print(f"  unique_block_ids={len(unique_ids)}")
        print(f"  dedup_count={len(dedup_entries)}")
        print(
            f"  sorted_by_block_id={raw_entries == sorted(raw_entries, key=lambda e: e.block_id)}"
        )
        print(f"  has_duplicate_ids={len(unique_ids) != len(raw_entries)}")

        if header.block_count != len(raw_entries):
            print(
                f"  {warn('warning')}=header.block_count does not match raw index count "
                f"({header.block_count} != {len(raw_entries)})"
            )

        if not raw_entries:
            print("records: (none)")
            return 0

        print(f"{key('records')}:")
        for idx, entry in enumerate(raw_entries):
            record = _read_record_at(f, entry.record_offset)
            payload_size = len(record.payload)
            compressed = bool(record.flags & COMPRESS_FLAG)

            issues: List[str] = []
            decompressed_size: int | None = None

            if compressed:
                try:
                    decompressed_size = len(gzip.decompress(record.payload))
                    if decompressed_size != BLOCK_SIZE:
                        issues.append("decompressed_size_invalid=true")
                except (OSError, EOFError) as exc:
                    issues.append(f"decompress_error={exc!s}")
            else:
                if payload_size != BLOCK_SIZE:
                    issues.append("payload_size_invalid=true")

            if record.block_id != entry.block_id:
                issues.append("index_mismatch=true")

            dump_data = b""
            base_offset = 0
            hexdump_source = ""
            if args.show_data:
                base_offset = entry.block_id * BLOCK_SIZE

                if compressed:
                    try:
                        dump_data = _decode_block_payload(record)
                        hexdump_source = "decompressed"
                    except ValueError as exc:
                        # Fall back to raw payload if decompression fails.
                        dump_data = record.payload
                        hexdump_source = "raw"
                        issues.append(f"decompress_error={exc!s}")
                else:
                    dump_data = record.payload
                    hexdump_source = "raw"

            print(f"  [{idx}]")
            print(f"    block_id={entry.block_id}")
            print(f"    record_offset={entry.record_offset}")
            print(f"    record_block_id={record.block_id}")
            print(f"    flags=0x{record.flags:08X}")
            print(f"    compressed={compressed}")
            print(f"    payload_size={payload_size}")
            if decompressed_size is not None:
                print(f"    decompressed_size={decompressed_size}")
            if args.show_data:
                print(f"    hexdump_source={hexdump_source}")
            if issues:
                for issue in issues:
                    print(f"    {warn(issue)}")
            else:
                print(f"    {ok('status=ok')}")

            if args.show_data:
                for dump_line in _hexdump_c_lines(
                    dump_data, base_offset=base_offset, color=color
                ):
                    print(f"    {dump_line}")

    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Convert between flat .bin and ROSB block-device files"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    to_rosb = sub.add_parser(
        "br",
        aliases=["bin-to-rosb", "bin2rosb"],
        help="Convert a flat .bin image to ROSB",
    )
    to_rosb.add_argument("input", help="Input .bin file")
    to_rosb.add_argument("output", help="Output .rosb file")
    to_rosb.add_argument(
        "--start-block-id",
        type=lambda v: int(v, 0),
        default=0,
        help="Block ID assigned to the first 512-byte block (default: 0)",
    )
    to_rosb.add_argument(
        "--compress",
        choices=("auto", "always", "never"),
        default="auto",
        help="Compression mode for each block (default: auto)",
    )
    to_rosb.set_defaults(func=bin_to_rosb)

    to_bin = sub.add_parser(
        "rb",
        aliases=["rosb-to-bin", "rosb2bin"],
        help="Convert ROSB to a flat .bin image",
    )
    to_bin.add_argument("input", help="Input .rosb file")
    to_bin.add_argument("output", help="Output .bin file")
    to_bin.add_argument(
        "--start-block-id",
        type=lambda v: int(v, 0),
        default=None,
        help="First block ID to export (default: first ID present in index)",
    )
    to_bin.add_argument(
        "--block-count",
        type=int,
        default=None,
        help="Number of blocks to export (default: through highest ID in index)",
    )
    to_bin.add_argument(
        "--trim-trailing-zeros",
        action="store_true",
        help="Trim trailing zero bytes from exported BIN",
    )
    to_bin.set_defaults(func=rosb_to_bin)

    list_info = sub.add_parser(
        "ls",
        aliases=["list", "info", "inspect"],
        help="List ROSB metadata and per-record details",
    )
    list_info.add_argument(
        "--show-data",
        action="store_true",
        help="Show hex dump of each record's payload (warning: may be large)",
    )
    list_info.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="Colorize output (default: auto)",
    )
    list_info.add_argument("input", help="Input .rosb file")
    list_info.set_defaults(func=rosb_list)

    return parser


def main(argv: Sequence[str]) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    try:
        return int(args.func(args))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
