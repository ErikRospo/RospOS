import argparse
import re
from pathlib import Path

GLYPH_WIDTH = 8
GLYPH_HEIGHT = 8
TABLE_GLYPHS = 128


def bitmap_bits(value, width, height):
    bits = []
    for y in range(height):
        for x in range(width):
            bit_index = y * width + x
            if value & (1 << (width * height - 1 - bit_index)):
                bits.append("1")
            else:
                bits.append("0")
        bits.append("\n")
    return "".join(bits)


def extract_font8x8_basic_and_descriptions(header_path):
    with open(header_path, "r", encoding="utf-8") as f:
        content = f.read()

    decl_index = content.find("char font8x8_basic=")
    if decl_index == -1:
        raise ValueError("font8x8_basic array not found")

    brace_start = content.find("{", decl_index)
    if brace_start == -1:
        raise ValueError("Opening brace for font8x8_basic array not found")

    depth = 0
    brace_end = None
    for i, ch in enumerate(content[brace_start:], start=brace_start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                brace_end = i
                break

    if brace_end is None:
        raise ValueError("Closing brace for font8x8_basic array not found")

    arr = content[brace_start + 1 : brace_end]
    glyphs = re.findall(
        r"\{([^}]+)\}\s*,?\s*(?://\s*U\+([0-9A-Fa-f]{4})(?:\s*\(([^)]*)\))?)?",
        arr,
    )

    font_by_codepoint = {}
    descriptions_by_codepoint = {}
    for glyph_bytes, codepoint_hex, desc in glyphs:
        bytestr = glyph_bytes.split(",")
        clean_bytes = []
        for b in bytestr:
            b = b.strip()
            if "//" in b:
                b = b.split("//", maxsplit=1)[0].strip()
            if not b:
                continue
            try:
                clean_bytes.append(int(b, 16))
            except ValueError:
                continue

        if len(clean_bytes) != 8:
            continue

        if not codepoint_hex:
            continue

        codepoint = int(codepoint_hex, 16)
        font_by_codepoint[codepoint] = clean_bytes
        if desc:
            descriptions_by_codepoint[codepoint] = desc.replace(" ", "_")

    return font_by_codepoint, descriptions_by_codepoint


def write_blob(output_path, font_by_codepoint, table_glyphs=TABLE_GLYPHS):
    with open(output_path, "wb") as f:
        blob = bytearray(table_glyphs * GLYPH_HEIGHT)
        for codepoint, glyph_bytes in font_by_codepoint.items():
            if 0 <= codepoint < table_glyphs:
                start = codepoint * GLYPH_HEIGHT
                blob[start : start + GLYPH_HEIGHT] = bytes(glyph_bytes)
        f.write(blob)


def write_index(index_path, descriptions_by_codepoint):
    with open(index_path, "w", encoding="utf-8") as f:
        for codepoint in sorted(descriptions_by_codepoint):
            desc = descriptions_by_codepoint[codepoint]
            f.write(f"{codepoint:03d} {desc}\n")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate a framebuffer glyph binary blob from font8x8_basic_data.h"
    )
    parser.add_argument(
        "--input",
        default="./font8x8_basic_data.h",
        help="Path to the header containing char font8x8_basic",
    )
    parser.add_argument(
        "--output",
        default="./fb_map_data.bin",
        help="Output binary blob path",
    )
    parser.add_argument(
        "--index-output",
        default="",
        help="Optional text file containing glyph index-to-name mapping",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)

    font_by_codepoint, descriptions_by_codepoint = (
        extract_font8x8_basic_and_descriptions(input_path)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_blob(output_path, font_by_codepoint)

    if args.index_output:
        index_path = Path(args.index_output)
        index_path.parent.mkdir(parents=True, exist_ok=True)
        write_index(index_path, descriptions_by_codepoint)

    print(
        f"Wrote {TABLE_GLYPHS} glyph slots to {output_path} ({TABLE_GLYPHS * 8} bytes), "
        f"filled {len(font_by_codepoint)} codepoints"
    )
    if args.index_output:
        print(f"Wrote glyph index to {args.index_output}")


if __name__ == "__main__":
    main()
