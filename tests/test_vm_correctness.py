import os
import struct
import subprocess
import unittest

from hypothesis import settings
import fuzz_settings  # noqa: F401


HARNESS = os.environ.get("ROSPOS_VM_FUZZ_HARNESS")
BREAK = 0x51000000


def _i(subop, rd, rs1, immediate):
    return (1 << 28) | (subop << 24) | (rd << 20) | (rs1 << 16) | (immediate & 0xFFFF)


def _r(subop, rd, rs1, rs2):
    return (subop << 24) | (rd << 20) | (rs1 << 16) | (rs2 << 12)


def _load_store(subop, rd, base, offset=0):
    return (2 << 28) | (subop << 24) | (rd << 20) | (base << 16) | (offset & 0xFFFF)


@unittest.skipUnless(HARNESS, "run through `make test` to build the VM harness")
class VmCorrectnessTests(unittest.TestCase):
    def run_words(self, *words):
        program = b"".join(struct.pack(">I", word) for word in words)
        result = subprocess.run(
            [HARNESS], input=program, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        lines = result.stdout.decode().strip().splitlines()
        return lines[-1]

    def assert_register(self, output, index, expected):
        self.assertIn(f"r{index}={expected & 0xFFFFFFFF}", output)

    def test_add_and_zero_register(self):
        output = self.run_words(
            _i(0, 0, 0, 99),
            _i(0, 2, 0, 20),
            _i(0, 3, 0, 22),
            _r(0, 4, 2, 3),
            BREAK,
        )
        self.assertTrue(output.startswith("ok "))
        self.assert_register(output, 0, 0)
        self.assert_register(output, 2, 20)
        self.assert_register(output, 3, 22)
        self.assert_register(output, 4, 42)

    def test_taken_and_not_taken_branches(self):
        output = self.run_words(
            _i(0, 1, 0, 7),
            _i(0, 2, 0, 7),
            (3 << 28) | (1 << 20) | (2 << 16) | 2,  # BEQ skips r3 assignment.
            _i(0, 3, 0, 99),
            (3 << 28) | (1 << 24) | (1 << 20) | (2 << 16) | 2,  # BNE not taken.
            _i(0, 4, 0, 11),
            _i(0, 5, 0, 12),
            BREAK,
        )
        self.assert_register(output, 3, 0)
        self.assert_register(output, 4, 11)
        self.assert_register(output, 5, 12)

    def test_load_store_endianness_and_sign_extension(self):
        output = self.run_words(
            _i(0, 1, 0, 0x100),
            _i(2, 2, 0, 0x80FF),  # ORI zero extends the immediate.
            _load_store(7, 2, 1),
            _load_store(0, 3, 1, 2),
            _load_store(1, 4, 1, 2),
            _load_store(2, 5, 1, 2),
            _load_store(3, 6, 1, 2),
            _load_store(4, 7, 1),
            BREAK,
        )
        self.assert_register(output, 3, -128)
        self.assert_register(output, 4, 128)
        self.assert_register(output, 5, -32513)
        self.assert_register(output, 6, 0x80FF)
        self.assert_register(output, 7, 0x80FF)

    def test_word_load_past_ram_end_is_rejected(self):
        output = self.run_words(
            _i(0, 1, 0, -1),
            _load_store(4, 2, 1),
            BREAK,
        )
        self.assertTrue(output.startswith("rejected "), output)

    def test_last_ram_word_is_accessible(self):
        output = self.run_words(
            _i(0, 1, 0, -4),
            _i(0, 2, 0, 1234),
            _load_store(7, 2, 1),
            _load_store(4, 3, 1),
            BREAK,
        )
        self.assert_register(output, 3, 1234)

    def test_halfword_access_crossing_address_space_end_is_rejected(self):
        for operation in (_load_store(2, 2, 1), _load_store(6, 2, 1)):
            with self.subTest(operation=operation):
                output = self.run_words(_i(0, 1, 0, -1), operation, BREAK)
                self.assertTrue(output.startswith("rejected "), output)


if __name__ == "__main__":
    unittest.main()
