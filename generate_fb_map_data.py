v = [
    0x00000000,
    0x08021084,
    0x0000294A,
    0x15F52BEA,
    0x08FA38BE,
    0x33A22E60,
    0x2E94D8A6,
    0x00001084,
    0x10421088,
    0x04421082,
    0x00A23880,
    0x00471000,
    0x04420000,
    0x00070000,
    0x0C600000,
    0x02222200,
    0x1D3AD72E,
    0x3E4214C4,
    0x3E22222E,
    0x1D18320F,
    0x210FC888,
    0x1D183C3F,
    0x1D17844C,
    0x0222221F,
    0x1D18BA2E,
    0x210F463E,
    0x0C6018C0,
    0x04401000,
    0x10411100,
    0x00E03800,
    0x04441040,
    0x0802322E,
    0x3C1EF62E,
    0x231FC544,
    0x1F18BE2F,
    0x3C10862E,
    0x1F18C62F,
    0x3E10BC3F,
    0x0210BC3F,
    0x1D1C843E,
    0x2318FE31,
    0x3E42109F,
    0x0C94211F,
    0x23149D31,
    0x3E108421,
    0x231AD6BB,
    0x239CD671,
    0x1D18C62E,
    0x0217C62F,
    0x30EAC62E,
    0x2297C62F,
    0x1D141A2E,
    0x0842109F,
    0x1D18C631,
    0x08454631,
    0x375AD631,
    0x22A21151,
    0x08421151,
    0x3E22221F,
    0x1842108C,
    0x20820820,
    0x0C421086,
    0x00004544,
    0xBE000000,
    0x00000082,
    0x1C97B000,
    0x0E949C21,
    0x1C10B800,
    0x1C94B908,
    0x3C1FC5C0,
    0x42211C4C,
    0x4E87252E,
    0x12949C21,
    0x0C210040,
    0x8C421004,
    0x12519521,
    0x0C210842,
    0x235AAC00,
    0x12949C00,
    0x0C949800,
    0x4213A526,
    0x7087252E,
    0x02149800,
    0x0E837000,
    0x0C213C42,
    0x0E94A400,
    0x0464A400,
    0x155AC400,
    0x36426C00,
    0x4E872529,
    0x1E223C00,
    0x1843188C,
    0x08421084,
    0x0C463086,
    0x0006D800,
]
import string

descriptions = [
    "SPACE",
    "EXCLAM",
    "QUOTE",
    "HASH",
    "DOLLAR",
    "PERCENT",
    "AMPERSAND",
    "APOSTROPHE",
    "PARENLEFT",
    "PARENRIGHT",
    "ASTERISK",
    "PLUS",
    "COMMA",
    "HYPHEN",
    "PERIOD",
    "SLASH",
]
descriptions += [str(i) for i in range(10)]
descriptions += ["COLON", "SEMICOLON", "LESS", "EQUAL", "GREATER", "QUESTION", "AT"]
descriptions += list(string.ascii_uppercase)
descriptions += [
    "BRACKETLEFT",
    "BACKSLASH",
    "BRACKETRIGHT",
    "CARET",
    "UNDERSCORE",
    "BACKTICK",
]
descriptions += list(string.ascii_lowercase)
descriptions += ["BRACELEFT", "BAR", "BRACERIGHT", "TILDE"]
glyph_width = 5
glyph_height = 6


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

for i, desc in enumerate(descriptions):
    val = v[i]
    # Reverse the bits of the value to match the desired orientation
    # reversed_val = int(format(val, "030b")[::-1], 2)
    # Generate the bitmap representation
    bitmap = print_bitmap(val, glyph_width, glyph_height)

    # Format the bitmap for display
    formatted_bitmap = (
        bitmap.replace("\n", "\n//").replace("0", "  ").replace("1", "##")
    )

    # Flatten the bitmap for data representation
    flattened_bitmap = bitmap.replace("\n", "")
    bm_val=int(flattened_bitmap,2) <<2
    bm_hex=format(bm_val,'0{}X'.format(8))
    print(f"FB_DATA_{desc}:\n.DATA 0x{bm_hex}  // Glyph: {desc}")
    print(f"//{formatted_bitmap}")
    print()
