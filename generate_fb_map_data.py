

glyph_width = 8
glyph_height = 8


def print_bitmap(value, width, height):
    row = ""
    for y in range(height):
        for x in range(width):
            bit_index = y * width + x
            if value & (1 << (width * height - 1 - bit_index)):
                row += "1"
            else:
                row += "0"
        row += "\n"
    return row


print("// Framebuffer Font Data")
print("// Generated from azmr's 5x6 font (https://github.com/azmr/blit-fonts)")
print(
    "// Using custom script to convert to RospOS framebuffer format and assembly data"
)

print("BASE_FB_ADDR:")

import sys

# Expecting a C array named font8x8_basic[128][8] in this file (as above)
import re

def extract_font8x8_basic_and_descriptions():
    # Read the C array from this file
    with open("./font8x8_basic_data.h", 'r') as f:
        content = f.read()
    # Find the array
    m = re.search(r'char font8x8_basic\s*\[128\]\[8\]\s*=\s*\{(.*?)\};', content, re.DOTALL)
    if not m:
        raise Exception("font8x8_basic array not found")
    arr = m.group(1)
    # Find all glyphs and their descriptions
    glyphs = re.findall(r'\{([^}]+)\}\s*,\s*//\s*U\+([0-9A-F]{4})\s*\(([^)]+)\)', arr)
    font = []
    descriptions = []
    for glyph_bytes, codepoint, desc in glyphs:
        bytestr = glyph_bytes.split(',')
        clean_bytes = []
        for b in bytestr:
            b = b.strip()
            if '//' in b:
                b = b.split('//')[0].strip()
            if b:
                try:
                    clean_bytes.append(int(b, 16))
                except ValueError:
                    continue
        if len(clean_bytes) != 8:
            continue
        font.append(clean_bytes)
        # Normalize description for label
        label = desc.replace(' ', '_')
        descriptions.append(label)
    return font, descriptions

font8x8, descriptions = extract_font8x8_basic_and_descriptions()

for i, (glyph_bytes, desc) in enumerate(zip(font8x8, descriptions)):
    # Combine 8 bytes into a 64-bit integer
    val = 0
    for b in glyph_bytes:
        val = (val << 8) | b
    bitmap = print_bitmap(val, glyph_width, glyph_height)
    formatted_bitmap = (
        bitmap.replace("\n", "\n//").replace("0", "  ").replace("1", "##")
    )
    flattened_bitmap = bitmap.replace("\n", "")
    flattened_bitmap=flattened_bitmap
    bm_val = int(flattened_bitmap, 2)
    bm_hex = format(bm_val, '016X')
    print(f"FB_DATA_{desc}:\n.DATA 0x{bm_hex}  // Glyph: {desc}")
    print(f"//{formatted_bitmap}")
    print()
