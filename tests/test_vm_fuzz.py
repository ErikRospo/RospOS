import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from hypothesis import given, settings, strategies as st
import fuzz_settings  # noqa: F401


HARNESS = os.environ.get("ROSPOS_VM_FUZZ_HARNESS")


@st.composite
def _binary_loader_cases(draw):
    version = draw(st.sampled_from([1, 2, 3, 0xFFFFFFFF]))
    count = draw(st.integers(min_value=0, max_value=3))
    data = bytearray(struct.pack("<III", 0x50534F52, version, count))
    for _ in range(count):
        address = draw(st.sampled_from([0, 4, 0xFFFFFFFC, 0xFFFFFFFF]))
        size = draw(st.integers(min_value=0, max_value=128))
        payload = draw(st.binary(max_size=128))
        if version == 1:
            data.extend(struct.pack("<II", address, size))
        elif version == 2:
            flags = draw(st.integers(min_value=0, max_value=7))
            data.extend(struct.pack("<III", flags, address, size))
        data.extend(payload[:size])
    return bytes(data)


@unittest.skipUnless(HARNESS, "run through `make test` to build the VM harness")
class VmFuzzTests(unittest.TestCase):
    @settings()
    @given(immediate=st.sampled_from([-32768, -1, 0, 1, 32767, 65535]))
    def test_addi_semantics_at_immediate_edges(self, immediate):
        instruction = (0x1 << 28) | (1 << 20) | (immediate & 0xFFFF)
        program = struct.pack(">II", instruction, 0x51000000)
        result = subprocess.run(
            [HARNESS], input=program, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        signed_immediate = immediate if immediate <= 0x7FFF else immediate - 0x10000
        self.assertEqual(int(result.stdout.decode().strip().split()[-1]), signed_immediate & 0xFFFFFFFF)

    @settings()
    @given(data=st.one_of(st.binary(max_size=128), _binary_loader_cases()))
    def test_malformed_binary_loader_inputs(self, data):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "fuzz.rosp"
            path.write_bytes(data)
            result = subprocess.run(
                [HARNESS, "--binary-file", str(path)], stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, timeout=5, check=False,
            )
        self.assertEqual(result.returncode, 0)
        self.assertTrue(b"accepted" in result.stdout or b"rejected " in result.stdout)

    @settings()
    @given(words=st.lists(st.integers(min_value=0, max_value=0xFFFFFFFF), min_size=1, max_size=16))
    def test_bounded_instruction_sequences(self, words):
        program = b"".join(struct.pack(">I", word) for word in words)
        result = subprocess.run(
            [HARNESS], input=program, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=5, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
        self.assertTrue(result.stdout.startswith((b"ok ", b"rejected ")))


if __name__ == "__main__":
    unittest.main()
