import sys
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st
from lark.exceptions import UnexpectedInput
import fuzz_settings  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "rospoas"))

from encode import encode_ir
from errors import AssemblerError
from grammar_parser import parse_source
from layout import layout_ir
from lower import lower_ir
from transformer import transform_parse_tree_ir


def _assemble(source):
    tree = parse_source(source)
    ir, _constants = transform_parse_tree_ir(tree)
    ir = lower_ir(ir)
    addresses, segments = layout_ir(ir)
    return encode_ir(ir, addresses, segments)


class AssemblerFuzzTests(unittest.TestCase):
    @settings()
    @given(
        register=st.integers(min_value=0, max_value=15),
        immediate=st.sampled_from([-32768, -1, 0, 1, 32767, 65535]),
    )
    def test_instruction_immediate_edges_encode(self, register, immediate):
        encoded = _assemble(f".SEG 0x1000\nADDI r{register}, r0, {immediate}\n")
        self.assertTrue(encoded)
        expected = (0x1 << 28) | (register << 20) | (immediate & 0xFFFF)
        self.assertEqual(encoded[0][1], expected.to_bytes(4, "big"))

    @settings()
    @given(space=st.integers(min_value=0, max_value=7), data=st.integers(0, 255))
    def test_data_and_space_boundaries(self, space, data):
        segments = _assemble(f".SEG 0x2000\n.DATA {data}\n.SPACE {space}\nADDI r1, r0, {data}\n")
        self.assertTrue(segments)
        self.assertEqual(segments[0], (0x2000, bytearray(data.to_bytes(4, "little"))))
        expected = (0x1 << 28) | (1 << 20) | data
        instruction_bytes = expected.to_bytes(4, "big")
        code = next((address, content) for address, content in segments if content.endswith(instruction_bytes))
        instruction_address = (0x2000 + 4 + space + 3) & ~3
        self.assertEqual(code[0] + len(code[1]) - 4, instruction_address)

    @settings()
    @given(target_index=st.integers(min_value=1, max_value=8))
    def test_branch_label_resolves_to_exact_word_offset(self, target_index):
        filler = "\n".join("ADDI r3, r0, 0" for _ in range(target_index - 1))
        source = f".SEG 0x3000\nBEQ r0, r0, target\n{filler}\ntarget:\nADDI r4, r0, 7\n"
        segments = _assemble(source)
        first_word = int.from_bytes(segments[0][1][:4], "big")
        self.assertEqual(first_word, (0x3 << 28) | target_index)

    @settings()
    @given(name=st.text(alphabet="abcdefghijklmnopqrstuvwxyz", min_size=1, max_size=8))
    def test_undefined_labels_are_rejected_cleanly(self, name):
        with self.assertRaises((UnexpectedInput, AssemblerError)):
            _assemble(f".SEG 0x1000\nJMP missing_{name}\n")

    @settings()
    @given(bad=st.text(max_size=80))
    def test_arbitrary_assembly_parsing_is_bounded(self, bad):
        try:
            parse_source(bad)
        except (UnexpectedInput, AssemblerError):
            pass
