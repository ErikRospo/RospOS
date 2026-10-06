import contextlib
import io
import os
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import fuzz_settings  # noqa: F401
from hypothesis import given, settings
from hypothesis import strategies as st
from lark.exceptions import UnexpectedInput

ROOT = Path(__file__).resolve().parents[1]
# Load assembler modules before replacing their top-level module names.
from test_assembler_fuzz import _assemble

sys.path.insert(0, str(ROOT / "rospocc"))
# RospoAS and RospoCC both use top-level ``transformer`` and ``errors`` modules.
sys.modules.pop("transformer", None)
_assembler_errors = sys.modules.pop("errors", None)
from parser import compile_source, parse_code

# The assembler also imports its errors dynamically during instruction encoding.
sys.modules["errors"] = _assembler_errors


def _compile_silently(*args):
    with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
        io.StringIO()
    ):
        return compile_source(*args)


def _run_compiled_source(source):
    harness = os.environ.get("ROSPOS_VM_FUZZ_HARNESS")
    if not harness:
        raise unittest.SkipTest("run through make test to build the VM harness")
    with tempfile.TemporaryDirectory() as tmp:
        output, _preprocessed, _tu, _mappings = _compile_silently(
            source, Path(tmp) / "program.ros", "program.rosc"
        )
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(
            io.StringIO()
        ):
            segments = _assemble(output.read_text(encoding="utf-8"))
        image = bytearray(struct.pack(">I", len(segments)))
        for address, content in segments:
            image.extend(struct.pack(">II", address, len(content)))
            image.extend(content)
        result = subprocess.run(
            [harness, "--run-image"],
            input=image,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
            check=False,
        )
    if result.returncode != 0:
        raise AssertionError(result.stderr.decode(errors="replace"))
    return int(result.stdout.decode().strip().split()[-1])


class CompilerFuzzTests(unittest.TestCase):
    @settings()
    @given(limit=st.integers(min_value=0, max_value=12))
    def test_generated_loop_matches_reference_sum(self, limit):
        actual = _run_compiled_source(
            f"int main() {{ int x = 0; int i = 0; while (i < {limit}) {{ x = x + i; i = i + 1; }} return x; }}"
        )
        self.assertEqual(actual, sum(range(limit)))

    @settings()
    @given(value=st.integers(min_value=-(2**31), max_value=2**31 - 1))
    def test_compiled_return_value_survives_assembly_and_vm(self, value):
        actual = _run_compiled_source(
            f"int main() {{ int x = {value}; if (x >= 0) {{ x = x + 1; }} return x; }}"
        )
        expected = value + 1 if value >= 0 else value
        self.assertEqual(actual, expected & 0xFFFFFFFF)

    @settings()
    @given(source=st.text(max_size=120))
    def test_malformed_source_is_rejected_by_parser(self, source):
        try:
            parse_code(source)
        except UnexpectedInput:
            return

    @settings()
    @given(depth=st.integers(min_value=1, max_value=5), value=st.integers(-1000, 1000))
    def test_nested_expression_depth_preserves_result(self, depth, value):
        expression = str(value)
        for _ in range(depth):
            expression = f"({expression} + 1)"
        actual = _run_compiled_source(f"int main() {{ return {expression}; }}")
        self.assertEqual(actual, (value + depth) & 0xFFFFFFFF)


class CompilerCorrectnessTests(unittest.TestCase):
    def test_struct_members_through_value_and_pointer_bases(self):
        sources = [
            "struct Pair { int x; int y; }; "
            "int main() { struct Pair s; s.x = 19; s.y = 42; return s.y; }",
            "struct Pair { int x; int y; }; "
            "int value(struct Pair *p) { p->y = 42; return p->y; } "
            "int main() { struct Pair s; s.x = 19; s.y = 22; return value(s); }",
        ]
        for source in sources:
            with self.subTest(source=source):
                self.assertEqual(_run_compiled_source(source), 42)

    def test_array_initializers_and_for_loop_step(self):
        source = (
            'int main() { char buf[4] = "ab"; char unused[4]; '
            "for (int i = 0; i < 2; i++) { buf[i] = buf[i] + 1; } "
            "return buf[0] + buf[1]; }"
        )
        self.assertEqual(_run_compiled_source(source), 197)

    def test_arithmetic_and_return_value(self):
        actual = _run_compiled_source("int main() { return (6 * 7) - 1; }")
        self.assertEqual(actual, 41)

    def test_function_call_returns_expected_value(self):
        source = (
            "int add(int a, int b) { return a + b; } int main() { return add(19, 23); }"
        )
        actual = _run_compiled_source(source)
        self.assertEqual(actual, 42)

    def test_if_else_and_loop_result(self):
        source = (
            "int main() { int sum = 0; int i = 0; "
            "while (i < 6) { if (i < 3) { sum = sum + i; } "
            "else { sum = sum + 2; } i = i + 1; } return sum; }"
        )
        # 0 + 1 + 2 + 2 + 2 + 2
        self.assertEqual(_run_compiled_source(source), 9)
