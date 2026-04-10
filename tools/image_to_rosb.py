#!/usr/bin/env python3
"""Convert images into a full 256x256 RospOS display filling multiple ROSB blocks.

The produced blocks span 256x256 pixels (65536 bytes total):
- Stored in 128 consecutive blocks (512 bytes each)
- Row-major pixel ordering, one byte per pixel (00RRGGBB)

If an existing ROSB is supplied, its blocks are preserved and the generated
image blocks are inserted/replaced starting at the given block id.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Dict, Sequence

try:
    from PIL import Image
except ModuleNotFoundError as exc:  # pragma: no cover
    raise SystemExit(
        "error: Pillow is required. Install with: pip install pillow"
    ) from exc

import rosb_tool

DISPLAY_WIDTH = 256
DISPLAY_HEIGHT = 256
DISPLAY_BYTES = DISPLAY_WIDTH * DISPLAY_HEIGHT
BLOCKS_NEEDED = DISPLAY_BYTES // rosb_tool.BLOCK_SIZE


def _clamp_byte(v: float) -> float:
    if v < 0.0:
        return 0.0
    if v > 255.0:
        return 255.0
    return v


def _quantize_channel(value: int) -> int:
    idx = int(round(value / 85.0))
    idx = max(0, min(3, idx))
    return idx


def _encode_pixel(r: int, g: int, b: int) -> int:
    r2 = _quantize_channel(r)
    g2 = _quantize_channel(g)
    b2 = _quantize_channel(b)
    return (r2 << 4) | (g2 << 2) | b2


def _quantized_rgb(r: float, g: float, b: float) -> tuple[int, int, int]:
    r2 = _quantize_channel(int(round(r)))
    g2 = _quantize_channel(int(round(g)))
    b2 = _quantize_channel(int(round(b)))
    return r2 * 85, g2 * 85, b2 * 85


def image_to_display_bytes(image_path: Path, resize_filter: str, dither: str) -> bytes:
    """Resize image to 256x256, quantize to RospOS palette, return raw pixel data."""
    img = Image.open(image_path).convert("RGB")

    if resize_filter == "nearest":
        pil_filter = Image.Resampling.NEAREST
    elif resize_filter == "bicubic":
        pil_filter = Image.Resampling.BICUBIC
    else:
        pil_filter = Image.Resampling.LANCZOS

    img = img.resize((DISPLAY_WIDTH, DISPLAY_HEIGHT), pil_filter)

    out = bytearray()

    if dither == "none":
        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                pixel = img.getpixel((x, y))
                if not isinstance(pixel, tuple) or len(pixel) < 3:
                    raise ValueError(
                        f"Unexpected pixel format at ({x}, {y}): {pixel!r}"
                    )
                r = int(pixel[0])
                g = int(pixel[1])
                b = int(pixel[2])
                out.append(_encode_pixel(r, g, b))
    else:
        work: list[list[float]] = []
        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                pixel = img.getpixel((x, y))
                if not isinstance(pixel, tuple) or len(pixel) < 3:
                    raise ValueError(
                        f"Unexpected pixel format at ({x}, {y}): {pixel!r}"
                    )
                work.append([float(pixel[0]), float(pixel[1]), float(pixel[2])])

        for y in range(DISPLAY_HEIGHT):
            for x in range(DISPLAY_WIDTH):
                idx = y * DISPLAY_WIDTH + x
                old_r, old_g, old_b = work[idx]
                new_r, new_g, new_b = _quantized_rgb(old_r, old_g, old_b)
                out.append(_encode_pixel(int(new_r), int(new_g), int(new_b)))

                err_r = old_r - new_r
                err_g = old_g - new_g
                err_b = old_b - new_b

                # Floyd-Steinberg error diffusion.
                if x + 1 < DISPLAY_WIDTH:
                    n = idx + 1
                    work[n][0] = _clamp_byte(work[n][0] + (err_r * 7.0 / 16.0))
                    work[n][1] = _clamp_byte(work[n][1] + (err_g * 7.0 / 16.0))
                    work[n][2] = _clamp_byte(work[n][2] + (err_b * 7.0 / 16.0))
                if y + 1 < DISPLAY_HEIGHT:
                    if x > 0:
                        n = idx + DISPLAY_WIDTH - 1
                        work[n][0] = _clamp_byte(work[n][0] + (err_r * 3.0 / 16.0))
                        work[n][1] = _clamp_byte(work[n][1] + (err_g * 3.0 / 16.0))
                        work[n][2] = _clamp_byte(work[n][2] + (err_b * 3.0 / 16.0))

                    n = idx + DISPLAY_WIDTH
                    work[n][0] = _clamp_byte(work[n][0] + (err_r * 5.0 / 16.0))
                    work[n][1] = _clamp_byte(work[n][1] + (err_g * 5.0 / 16.0))
                    work[n][2] = _clamp_byte(work[n][2] + (err_b * 5.0 / 16.0))

                    if x + 1 < DISPLAY_WIDTH:
                        n = idx + DISPLAY_WIDTH + 1
                        work[n][0] = _clamp_byte(work[n][0] + (err_r * 1.0 / 16.0))
                        work[n][1] = _clamp_byte(work[n][1] + (err_g * 1.0 / 16.0))
                        work[n][2] = _clamp_byte(work[n][2] + (err_b * 1.0 / 16.0))

    if len(out) != DISPLAY_BYTES:
        raise ValueError(
            f"Internal error: produced {len(out)} bytes, expected {DISPLAY_BYTES}"
        )

    return bytes(out)


def _split_into_blocks(data: bytes) -> list[bytes]:
    """Split display data into 512-byte blocks, padding last block if needed."""
    blocks: list[bytes] = []
    for i in range(0, len(data), rosb_tool.BLOCK_SIZE):
        block = data[i : i + rosb_tool.BLOCK_SIZE]
        if len(block) < rosb_tool.BLOCK_SIZE:
            block = block + bytes(rosb_tool.BLOCK_SIZE - len(block))
        blocks.append(block)
    return blocks


def _read_existing_rosb(path: Path) -> Dict[int, bytes]:
    with path.open("rb") as f:
        f.seek(0, 2)
        file_size = f.tell()
        f.seek(0)

        header = rosb_tool._read_header(f)
        if header.magic != rosb_tool.MAGIC:
            raise ValueError("Invalid ROSB magic")
        if header.version != rosb_tool.VERSION:
            raise ValueError(f"Unsupported ROSB version: {header.version}")

        entries = rosb_tool._read_index(f, header, file_size)

        blocks: Dict[int, bytes] = {}
        for entry in entries:
            record = rosb_tool._read_record_at(f, entry.record_offset)
            if record.block_id != entry.block_id:
                raise ValueError(
                    f"Index mismatch for block {entry.block_id}: record has {record.block_id}"
                )
            blocks[entry.block_id] = rosb_tool._decode_block_payload(record)

    return blocks


def _encode_records_for_write(
    blocks: Dict[int, bytes], compress_mode: str
) -> list[tuple[int, int, bytes]]:
    records: list[tuple[int, int, bytes]] = []
    for block_id in sorted(blocks.keys()):
        block = blocks[block_id]
        if len(block) != rosb_tool.BLOCK_SIZE:
            raise ValueError(
                f"Block {block_id} is {len(block)} bytes; expected {rosb_tool.BLOCK_SIZE}"
            )
        flags, payload = rosb_tool._encode_block_payload(block, compress_mode)
        records.append((block_id, flags, payload))
    return records


def _write_rosb(output_path: Path, records: list[tuple[int, int, bytes]]) -> None:
    with output_path.open("wb") as f:
        rosb_tool._write_header(f, block_count=0, index_offset=0)

        index_entries: list[rosb_tool.IndexEntry] = []
        for block_id, flags, payload in records:
            record_offset = f.tell()
            f.write(
                rosb_tool.struct.pack(
                    rosb_tool.RECORD_HEADER_FMT, block_id, flags, len(payload)
                )
            )
            f.write(payload)
            index_entries.append(
                rosb_tool.IndexEntry(block_id=block_id, record_offset=record_offset)
            )

        index_offset = f.tell()
        f.write(rosb_tool.struct.pack(rosb_tool.INDEX_COUNT_FMT, len(index_entries)))
        for entry in index_entries:
            f.write(
                rosb_tool.struct.pack(
                    rosb_tool.INDEX_ENTRY_FMT, entry.block_id, entry.record_offset
                )
            )

        f.seek(0)
        rosb_tool._write_header(
            f, block_count=len(index_entries), index_offset=index_offset
        )


def run(args: argparse.Namespace) -> int:
    src_image = Path(args.image)
    out_rosb = Path(args.output)

    if not src_image.exists():
        raise ValueError(f"Input image not found: {src_image}")

    display_data = image_to_display_bytes(src_image, args.resize_filter, args.dither)
    image_blocks = _split_into_blocks(display_data)

    existing_blocks: Dict[int, bytes] = {}
    base_info = "new"
    if out_rosb.exists():
        existing_blocks = _read_existing_rosb(out_rosb)
        base_info = f"existing={out_rosb}"

    start_block_id = args.start_block_id
    for i, block_data in enumerate(image_blocks):
        existing_blocks[start_block_id + i] = block_data

    records = _encode_records_for_write(existing_blocks, args.compress)
    _write_rosb(out_rosb, records)

    used_colors = len(set(display_data))
    print(
        f"Wrote ROSB: {out_rosb} | {base_info} | start_block_id={start_block_id} "
        f"blocks_used={len(image_blocks)} pixels={DISPLAY_WIDTH}x{DISPLAY_HEIGHT} "
        f"unique_colors={used_colors} blocks_total={len(records)}"
    )
    return 0


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Convert an image to a full 256x256 RospOS display filling 128 ROSB blocks"
        )
    )
    parser.add_argument("image", help="Input image file")
    parser.add_argument("output", help="Output ROSB file")
    parser.add_argument(
        "--start-block-id",
        type=lambda v: int(v, 0),
        default=256,
        help="Starting block ID for the image blocks (default: 256)",
    )
    parser.add_argument(
        "--compress",
        choices=("auto", "always", "never"),
        default="auto",
        help="Compression mode for ROSB blocks (default: auto)",
    )
    parser.add_argument(
        "--resize-filter",
        choices=("lanczos", "bicubic", "nearest"),
        default="lanczos",
        help="Resampling filter before quantization (default: lanczos)",
    )
    parser.add_argument(
        "--dither",
        choices=("none", "floyd-steinberg"),
        default="none",
        help="Dithering mode for palette quantization (default: none)",
    )
    return parser


def main(argv: Sequence[str]) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)

    try:
        return int(run(args))
    except Exception as exc:  # pylint: disable=broad-except
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
