#!/usr/bin/env python3
"""Display the RospOS framebuffer palette.

Pixel encoding matches VM display format: 00RRGGBB (2 bits per channel).
This means 256 byte values map onto 64 unique colors.

Examples:
  python tools/show_palette.py
  python tools/show_palette.py --mode bytes
  python tools/show_palette.py --cell-size 40 --show-labels
"""

from __future__ import annotations

import argparse
import tkinter as tk
from dataclasses import dataclass


@dataclass(frozen=True)
class Swatch:
    value: int
    r: int
    g: int
    b: int

    @property
    def hex_color(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"


def decode_rosp_color(value: int) -> tuple[int, int, int]:
    """Decode 00RRGGBB into 8-bit RGB channels."""
    r = ((value >> 4) & 0x03) * 85
    g = ((value >> 2) & 0x03) * 85
    b = (value & 0x03) * 85
    return r, g, b


def build_unique_palette() -> list[Swatch]:
    swatches: list[Swatch] = []
    for r2 in range(4):
        for g2 in range(4):
            for b2 in range(4):
                value = (r2 << 4) | (g2 << 2) | b2
                r, g, b = decode_rosp_color(value)
                swatches.append(Swatch(value=value, r=r, g=g, b=b))
    return swatches


def build_all_byte_values() -> list[Swatch]:
    swatches: list[Swatch] = []
    for value in range(256):
        r, g, b = decode_rosp_color(value)
        swatches.append(Swatch(value=value, r=r, g=g, b=b))
    return swatches


def draw_palette(swatches: list[Swatch], columns: int, cell_size: int, show_labels: bool, title: str) -> None:
    rows = (len(swatches) + columns - 1) // columns
    label_height = 18 if show_labels else 0

    width = columns * cell_size
    height = rows * (cell_size + label_height)

    root = tk.Tk()
    root.title(title)
    canvas = tk.Canvas(root, width=width, height=height, highlightthickness=0)
    canvas.pack()

    for idx, swatch in enumerate(swatches):
        row = idx // columns
        col = idx % columns
        x0 = col * cell_size
        y0 = row * (cell_size + label_height)
        x1 = x0 + cell_size
        y1 = y0 + cell_size

        canvas.create_rectangle(x0, y0, x1, y1, fill=swatch.hex_color, outline="#222")
        if show_labels:
            canvas.create_text(
                x0 + (cell_size // 2),
                y1 + (label_height // 2),
                text=f"{swatch.value:02X}",
                fill="#111",
                font=("TkDefaultFont", 9),
            )

    root.resizable(False, False)
    root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show the RospOS display palette")
    parser.add_argument(
        "--mode",
        choices=["unique", "bytes"],
        default="unique",
        help="Show 64 unique colors or all 256 byte values (default: unique)",
    )
    parser.add_argument(
        "--cell-size",
        type=int,
        default=36,
        help="Cell size in pixels (default: 36)",
    )
    parser.add_argument(
        "--show-labels",
        action="store_true",
        help="Label each swatch with its byte value",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.mode == "unique":
        swatches = build_unique_palette()
        columns = 8
        title = "RospOS Palette (64 unique colors from 00RRGGBB)"
    else:
        swatches = build_all_byte_values()
        columns = 16
        title = "RospOS Palette (all 256 byte values, includes duplicates)"

    draw_palette(
        swatches=swatches,
        columns=columns,
        cell_size=max(10, args.cell_size),
        show_labels=args.show_labels,
        title=title,
    )


if __name__ == "__main__":
    main()
