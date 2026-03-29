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
import math
import struct
import sys
import zlib
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
    return Header(magic=magic, version=version, block_count=block_count, index_offset=index_offset)


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
            raise ValueError(f"Invalid record offset {record_offset} for block {block_id}")
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
            data = zlib.decompress(record.payload)
        except zlib.error as exc:
            raise ValueError(f"Failed to decompress block {record.block_id}: {exc}") from exc
    else:
        data = record.payload

    if len(data) != BLOCK_SIZE:
        raise ValueError(
            f"Block {record.block_id} resolved to {len(data)} bytes, expected {BLOCK_SIZE}"
        )
    return data


def _encode_block_payload(block: bytes, mode: str) -> Tuple[int, bytes]:
    if len(block) != BLOCK_SIZE:
        raise ValueError(f"Internal error: block size is {len(block)}, expected {BLOCK_SIZE}")

    if mode == "never":
        return 0, block

    compressed = zlib.compress(block)

    if mode == "always":
        return COMPRESS_FLAG, compressed

    if len(compressed) < len(block): # If mode==auto, only compress if strictly saves space
        return COMPRESS_FLAG, compressed
    return 0, block


def _find_entry(entries: Sequence[IndexEntry], block_id: int) -> IndexEntry | None:
    ids = [e.block_id for e in entries]
    idx = bisect.bisect_left(ids, block_id)
    if idx >= len(entries) or entries[idx].block_id != block_id:
        return None
    return entries[idx]


def bin_to_rosb(args: argparse.Namespace) -> int:
    src = Path(args.input)
    dst = Path(args.output)

    data = src.read_bytes()
    block_count = 0 if len(data) == 0 else math.ceil(len(data) / BLOCK_SIZE)

    records: List[Tuple[int, int, bytes]] = []
    for i in range(block_count):
        block_id = args.start_block_id + i
        start = i * BLOCK_SIZE
        chunk = data[start:start + BLOCK_SIZE]
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
            index_entries.append(IndexEntry(block_id=block_id, record_offset=record_offset))

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
            block_count = (max_block_id - start_block_id + 1) if max_block_id >= start_block_id else 0
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


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert between flat .bin and ROSB block-device files")
    sub = parser.add_subparsers(dest="command", required=True)

    to_rosb = sub.add_parser("br",aliases=["bin-to-rosb","bin2rosb"], help="Convert a flat .bin image to ROSB")
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

    to_bin = sub.add_parser("rb", aliases=["rosb-to-bin","rosb2bin"], help="Convert ROSB to a flat .bin image")
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
