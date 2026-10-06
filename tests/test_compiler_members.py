"""Member access regressions at offset and register-lifetime boundaries."""

import io
import unittest
from unittest.mock import patch

# Initialize the compiler/assembler imports in the same order as runtime tests.
import test_compiler_fuzz  # noqa: F401
from emitter import Emitter
from emitter_expr import ExprEmitterError, _emit_member_access
from emitter_stmt import StmtEmitterError, _emit_assign_member_access
from tracked_writer import TrackedWriter


class MemberAccessTests(unittest.TestCase):
    def make_access(self, op, offset):
        emitter = Emitter()
        emitter.var_regs["s"] = "r2"
        emitter.var_types["s"] = "Pair" if op == "." else "Pair_ptr"
        emitter.reg_free.remove("r2")
        emitter.struct_types["Pair"] = {
            "members": [{"name": "value", "offset": offset, "size": 4}],
            "size": offset + 4,
        }
        buffer = io.StringIO()
        writer = TrackedWriter(buffer, "members.rosc")
        writer.set_source_context(7, "s.value")
        emitter.tracked_writer = writer
        node = {
            "type": "member_access",
            "op": op,
            "base": {"type": "var", "name": "s"},
            "member": "value",
        }
        return emitter, writer, buffer, node

    def test_load_and_store_offset_boundaries_preserve_live_base(self):
        for op in (".", "->"):
            for offset in (0, 65535, 65536, 262144):
                for is_store in (False, True):
                    with self.subTest(op=op, offset=offset, is_store=is_store):
                        emitter, writer, buffer, node = self.make_access(op, offset)
                        initial_free = set(emitter.reg_free)
                        if is_store:
                            _emit_assign_member_access(emitter, node, "r1", writer)
                            result = "r1"
                        else:
                            result = _emit_member_access(emitter, node, writer)
                        text = buffer.getvalue()
                        instr = "SW" if is_store else "LW"
                        if offset < 65536:
                            self.assertIn(f"{instr} {result}, r2, {offset}", text)
                            self.assertNotIn("  ADD ", text)
                        else:
                            self.assertIn(f", {offset}    // load immediate", text)
                            self.assertIn("  ADD ", text)
                            self.assertRegex(text, rf"{instr} {result}, r\d+, 0")
                        self.assertEqual(emitter.var_regs, {"s": "r2"})
                        self.assertNotIn("r2", emitter.reg_free)
                        emitter.release_expr_reg(result)
                        self.assertEqual(set(emitter.reg_free), initial_free)
                        self.assertEqual(len(emitter.reg_free), len(initial_free))
                        self.assertTrue(writer.get_mappings())
                        self.assertTrue(
                            all(m["source_line"] == 7 for m in writer.get_mappings())
                        )

    def test_spilled_base_is_restored_for_loads_and_stores(self):
        for op in (".", "->"):
            for is_store in (False, True):
                with self.subTest(op=op, is_store=is_store):
                    emitter, writer, buffer, node = self.make_access(op, 4)
                    emitter._spill_live_var_reg_to_slot("r2", ["s"])
                    if is_store:
                        _emit_assign_member_access(emitter, node, "r1", writer)
                        result = "r1"
                    else:
                        result = _emit_member_access(emitter, node, writer)
                    base_reg = emitter.var_regs["s"]
                    instr = "SW" if is_store else "LW"
                    self.assertIn("restore spilled var s", buffer.getvalue())
                    self.assertIn(f"{instr} {result}, {base_reg}, 4", buffer.getvalue())
                    self.assertNotIn("s", emitter._var_spill_labels)
                    self.assertNotIn(base_reg, emitter.reg_free)

    def test_missing_member_uses_expression_or_statement_error(self):
        for op in (".", "->"):
            for is_store in (False, True):
                with self.subTest(op=op, is_store=is_store):
                    emitter, writer, buffer, node = self.make_access(op, 0)
                    node["member"] = "missing"
                    error = StmtEmitterError if is_store else ExprEmitterError
                    with self.assertRaisesRegex(error, "Member missing not found"):
                        if is_store:
                            _emit_assign_member_access(emitter, node, "r1", writer)
                        else:
                            _emit_member_access(emitter, node, writer)
                    self.assertNotIn("  LW ", buffer.getvalue())
                    self.assertNotIn("  SW ", buffer.getvalue())

    def test_logged_errors_are_also_the_exception_message(self):
        expression_cases = [
            {
                "type": "member_access",
                "op": ".",
                "base": {"type": "const", "value": 1},
                "member": "value",
            },
            {
                "type": "member_access",
                "op": "unsupported",
                "base": {"type": "var", "name": "s"},
                "member": "value",
            },
            {"type": "unop", "op": "not"},
            {"type": "assign", "target": "s", "value": None},
            {
                "type": "binop",
                "op": "lshift",
                "left": None,
                "right": {"type": "const", "value": 1},
            },
        ]
        statement_cases = [
            {"type": "decl", "name": None},
            {"type": "assign", "target": None, "value": {"type": "const", "value": 1}},
            {
                "type": "assign",
                "target": {"type": "member_access"},
                "value": {"type": "const", "value": 1},
            },
        ]
        for cases, method, error in (
            (expression_cases, "emit_expr", ExprEmitterError),
            (statement_cases, "emit_statement", StmtEmitterError),
        ):
            for node in cases:
                with self.subTest(node=node):
                    emitter, writer, _buffer, _target = self.make_access(".", 0)
                    with patch("emitter_expr.logger.error") as log:
                        with self.assertRaises(error) as caught:
                            getattr(emitter, method)(node, writer)
                    log.assert_called_once()
                    self.assertTrue(str(caught.exception))
                    self.assertEqual(str(caught.exception), log.call_args.args[0])

    def test_evaluated_pointer_temporary_is_released(self):
        for is_store in (False, True):
            with self.subTest(is_store=is_store):
                emitter, writer, _buffer, node = self.make_access("->", 65536)
                initial_free = set(emitter.reg_free)
                with patch.object(
                    emitter, "emit_expr", side_effect=lambda *_: emitter.alloc_reg()
                ):
                    if is_store:
                        _emit_assign_member_access(emitter, node, "r1", writer)
                        result = "r1"
                    else:
                        result = _emit_member_access(emitter, node, writer)
                emitter.release_expr_reg(result)
                self.assertEqual(set(emitter.reg_free), initial_free)
                self.assertEqual(len(emitter.reg_free), len(initial_free))

    def test_address_temporaries_are_released_when_emission_fails(self):
        emitter, writer, _buffer, node = self.make_access(".", 65536)
        initial_free = set(emitter.reg_free)
        write = writer.write

        def fail_store(text):
            if text.startswith("  SW "):
                raise OSError("output failed")
            write(text)

        with patch.object(writer, "write", side_effect=fail_store):
            with self.assertRaisesRegex(OSError, "output failed"):
                _emit_assign_member_access(emitter, node, "r1", writer)
        self.assertEqual(set(emitter.reg_free), initial_free)
        self.assertEqual(len(emitter.reg_free), len(initial_free))
