"""Vector relocation and terminal error-handler ABI regressions."""

import os
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_compiler_fuzz import _compile_silently
from test_assembler_fuzz import (
    encode_ir,
    layout_ir,
    lower_ir,
    parse_source,
    transform_parse_tree_ir,
)
from emitter import EmitterError
from optimizer import optimize


def assemble_with_symbols(source, optimized):
    ir, _ = transform_parse_tree_ir(parse_source(source))
    if optimized:
        ir, _ = optimize(ir)
    ir = lower_ir(ir)
    addresses, segments = layout_ir(ir)
    return addresses, encode_ir(ir, addresses, segments)


def read_word(segments, address):
    for base, data in segments:
        offset = address - base
        if 0 <= offset <= len(data) - 4:
            return int.from_bytes(data[offset : offset + 4], "big")
    raise AssertionError(f"No word at {address:#x}")


class CompilerVectorTests(unittest.TestCase):
    def compile(self, source):
        with tempfile.TemporaryDirectory() as tmp:
            output, _, _, _ = _compile_silently(
                source, Path(tmp) / "program.ros", "program.rosc"
            )
            return output.read_text(encoding="utf-8")

    def test_error_vector_is_absolute_and_buffers_stay_below_vectors(self):
        handler = "void _err_handler() { __break(); } "
        main = "char buffer[16]; int main() { return 0; } "
        for source in (handler + main, main + handler):
            assembly = self.compile(source)
            # Exercise a full-width function address, independently of function order.
            assembly = assembly.replace(".SEG 0x00000000", ".SEG 0x12340", 1)
            for optimized in (False, True):
                with self.subTest(handler_first=source.startswith("void"), optimized=optimized):
                    addresses, segments = assemble_with_symbols(assembly, optimized)
                    self.assertEqual(read_word(segments, 0xFFFFFFF8), addresses["_err_handler"])
                    self.assertGreater(addresses["_err_handler"], 0xFFFF)
                    self.assertEqual(read_word(segments, 0xFFFFFFFC), 0)
                    self.assertLess(addresses["buffer"] + 16, 0xFFFFFFF8)

    def test_missing_handler_emits_zero_and_still_assembles(self):
        assembly = self.compile("int main() { return 42; }")
        for optimized in (False, True):
            _, segments = assemble_with_symbols(assembly, optimized)
            self.assertEqual(read_word(segments, 0xFFFFFFF8), 0)
            self.assertEqual(read_word(segments, 0xFFFFFFFC), 0)

    def test_inline_handler_is_rejected(self):
        with self.assertRaisesRegex(EmitterError, "_err_handler must not be inline"):
            self.compile("inline void _err_handler() { __break(); } int main() { return 0; }")

    def test_handler_pops_documented_frame_while_calling_logging_helpers(self):
        harness = os.environ.get("ROSPOS_VM_FUZZ_HARNESS")
        if not harness:
            self.skipTest("run through make test to build the VM harness")
        source = (
            "int log_word(int value) { return value; } "
            "int _err_handler() { int code = @r1; int pc = __pop(); "
            "int checksum = log_word(pc); "
            "for (int i = 1; i <= 15; i++) { "
            "int saved = __pop(); checksum = checksum + log_word(saved); } "
            "return checksum + code; } int main() { return 0; }"
        )
        assembly = self.compile(source)
        # Simulate fault entry without depending on VM error dispatch.
        entry = ["LLI r15, 0x200000"]
        values = list(range(0x1001, 0x1010))
        for value in reversed(values):
            entry.extend([f"LLI r1, {value}", "PUSH r1"])
        pc, code = 0x12345678, 0x1005F
        entry.extend([
            f"LLI r1, {pc}", "PUSH r1", f"LLI r1, {code}",
            "LLI r14, 0xFFFFFFF8", "LW r14, r14, 0", "RET",
        ])
        assembly = assembly.replace("  JMP main\n", "\n".join(entry) + "\n", 1)
        for optimized in (False, True):
            with self.subTest(optimized=optimized):
                _, segments = assemble_with_symbols(assembly, optimized)
                image = bytearray(struct.pack(">I", len(segments)))
                for address, content in segments:
                    image.extend(struct.pack(">II", address, len(content)))
                    image.extend(content)
                result = subprocess.run(
                    [harness, "--run-image", "10000"], input=image,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                )
                self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                self.assertEqual(int(result.stdout.decode().strip().split()[-1]), pc + sum(values) + code)

    def test_handler_fallthrough_and_bare_pop_terminate_without_returning(self):
        assembly = self.compile("void _err_handler() { __pop(); } int main() { return 0; }")
        handler = assembly.split(".FUNC _err_handler:\n", 1)[1].split(".FUNC main:", 1)[0]
        self.assertIn("POP r1", handler)
        self.assertNotIn("PUSH r14", handler)
        self.assertNotIn("POP r14", handler)
        self.assertNotIn("RET", handler)
        self.assertIn("BREAK", handler)
        assemble_with_symbols(assembly, False)

    def test_vm_faults_enter_compiled_handler_through_vector(self):
        harness = os.environ.get("ROSPOS_VM_FUZZ_HARNESS")
        if not harness:
            self.skipTest("run through make test to build the VM harness")
        source = (
            "int log_word(int value) { return value; } "
            "int _err_handler() { int code = @r1; int pc = __pop(); "
            "int checksum = log_word(pc); "
            "for (int i = 1; i <= 15; i++) { "
            "int saved = __pop(); checksum = checksum + log_word(saved); } "
            "return checksum + code; } int main() { return 0; }"
        )
        compiled = self.compile(source)
        registers = [0x1000 + reg for reg in range(1, 15)] + [0x200000]
        registers[3] = 0  # r4 is the zero divisor.
        entry = [f"LLI r{reg}, {value}" for reg, value in enumerate(registers, 1)]
        # Numeric .DATA is a byte blob; this spells the invalid word 0x5F000000.
        faults = [(".DATA 0x0000005F", 0x1005F), ("DIV r8, r3, r4", 0x20C34)]
        for fault, code in faults:
            assembly = compiled.replace(
                "  JMP main\n", "\n".join(entry + ["fault_site:", fault]) + "\n", 1
            )
            for optimized in (False, True):
                with self.subTest(fault=fault, optimized=optimized):
                    addresses, segments = assemble_with_symbols(assembly, optimized)
                    image = bytearray(struct.pack(">I", len(segments)))
                    for address, content in segments:
                        image.extend(struct.pack(">II", address, len(content)))
                        image.extend(content)
                    result = subprocess.run(
                        [harness, "--run-image", "10000"], input=image,
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr.decode(errors="replace"))
                    expected = addresses["fault_site"] + sum(registers) + code
                    self.assertEqual(int(result.stdout.decode().strip().split()[-1]), expected)
