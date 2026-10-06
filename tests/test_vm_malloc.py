"""Exercise the real RospOS allocator through RospoCC, RospoAS, and rospovm.

Run with ``make test``. The current allocator aligns to four bytes and reuses
whole free blocks; splitting and coalescing are deliberately not required.
Invalid pointers and double frees are outside the supported contract.
"""

import itertools
import os
import random
import unittest
from pathlib import Path

from test_compiler_fuzz import _run_compiled_source

ROOT = Path(__file__).resolve().parents[1]
MAX_STEPS = 5_000_000

# Use byte buffers for bookkeeping: RospoCC currently indexes all pointers by
# byte offsets, so int/pointer arrays would introduce unrelated compiler failures.
SLOT_HELPERS = """
    int read_slot(char *table, int slot) {
        int *p = (int *)(table + slot * 4);
        return *p;
    }
    void write_slot(char *table, int slot, int value) {
        int *p = (int *)(table + slot * 4);
        *p = value;
    }
"""


@unittest.skipUnless(
    os.environ.get("ROSPOS_VM_FUZZ_HARNESS"),
    "run through `make test` to build the VM harness",
)
class MallocFreeCorrectnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the production library rather than maintaining an allocator copy.
        cls.stdlib = (ROOT / "rospos/lib/stdlib.rosc").read_text(encoding="utf-8")

    def assert_program(self, body, *, declarations=""):
        source = (
            self.stdlib
            + "\n"
            + SLOT_HELPERS
            + declarations
            + "\nint main() { init_heap();\n"
            + body
            + "\nreturn 0; }\n"
        )
        self.assertEqual(
            _run_compiled_source(source, max_steps=MAX_STEPS),
            0,
            "guest program returned a failing check number",
        )

    def test_first_user_allocation_succeeds(self):
        self.assert_program(
            "char *p = malloc(4); if (!p) return 1; p[0] = 42; if (p[0] != 42) return 2; free(p);"
        )

    def test_nonpositive_sizes_return_null_without_consuming_heap(self):
        for size in (0, -1, -4, -16384, -2147483648):
            with self.subTest(size=size):
                self.assert_program(
                    f"int used; used = __heap_used; if (malloc({size}) != 0) return 1; if (__heap_used != used) return 2;"
                )

    def test_null_free_leaves_heap_and_live_payload_unchanged(self):
        self.assert_program("""
            free(0);
            char *p = malloc(8);
            if (!p) return 1;
            p[0] = 17; p[7] = 93;
            int used; used = __heap_used;
            free(0); free(0);
            if (__heap_used != used) return 2;
            if (p[0] != 17 || p[7] != 93) return 3;
            free(p);
        """)

    def test_allocations_are_aligned_and_fully_writable(self):
        for size in (1, 2, 3, 4, 5, 7, 8, 15, 16, 17, 63, 64, 65, 255, 256, 257, 1023):
            with self.subTest(size=size):
                self.assert_program(f"""
                    char *p = malloc({size});
                    if (!p) return 1;
                    if (((int)p & 3) != 0) return 2;
                    if (p < __heap_area || p + {size} > __heap_area + 16384) return 3;
                    for (int i = 0; i < {size}; i++) p[i] = (i * 37 + 11) & 127;
                    for (int i = 0; i < {size}; i++) {{
                        if (p[i] != ((i * 37 + 11) & 127)) return 4;
                    }}
                    free(p);
                """)

    def test_live_allocations_do_not_overlap_or_corrupt_each_other(self):
        self.assert_program("""
            char *a = malloc(7); char *b = malloc(13); char *c = malloc(31);
            if (!a || !b || !c) return 1;
            if (a < b + 13 && b < a + 7) return 2;
            if (a < c + 31 && c < a + 7) return 3;
            if (b < c + 31 && c < b + 13) return 4;
            for (int i = 0; i < 7; i++) a[i] = 21;
            for (int i = 0; i < 13; i++) b[i] = 42;
            for (int i = 0; i < 31; i++) c[i] = 63;
            for (int i = 0; i < 7; i++) if (a[i] != 21) return 5;
            for (int i = 0; i < 13; i++) if (b[i] != 42) return 6;
            for (int i = 0; i < 31; i++) if (c[i] != 63) return 7;
            free(b); free(a); free(c);
        """)

    def test_payload_preserves_all_byte_values(self):
        self.assert_program("""
            char *p = malloc(256);
            if (!p) return 1;
            for (int i = 0; i < 256; i++) p[i] = i;
            for (int i = 0; i < 256; i++) if ((p[i] & 255) != i) return 2;
            free(p);
        """)

    def test_integer_and_struct_payloads_support_typed_access(self):
        self.assert_program(
            """
            int *values = malloc(16);
            struct Pair *pair = malloc(sizeof(struct Pair));
            if (!values || !pair) return 1;
            write_slot((char *)values, 0, 305419896);
            write_slot((char *)values, 1, -7);
            write_slot((char *)values, 2, 0);
            write_slot((char *)values, 3, 2147483647);
            pair->x = 19; pair->y = 23;
            if (read_slot((char *)values, 0) != 305419896 || read_slot((char *)values, 1) != -7) return 2;
            if (read_slot((char *)values, 2) != 0 || read_slot((char *)values, 3) != 2147483647) return 3;
            if (pair->x + pair->y != 42) return 4;
            free(values); free(pair);
        """,
            declarations="struct Pair { int x; int y; };",
        )

    def test_free_reuses_exact_or_smaller_block_without_heap_growth(self):
        for size in (1, 4, 17, 64):
            with self.subTest(size=size):
                self.assert_program(f"""
                    char *p = malloc(64);
                    if (!p) return 1;
                    int used; used = __heap_used;
                    free(p);
                    char *q = malloc({size});
                    if (q != p) return 2;
                    if (__heap_used != used) return 3;
                    q[0] = 19; q[{size - 1}] = 23;
                    if (q[{size - 1}] != 23) return 4;
                    free(q);
                """)

    def test_reuse_respects_rounded_payload_capacity(self):
        self.assert_program("""
            char *p = malloc(5);
            if (!p) return 1;
            int used; used = __heap_used;
            free(p);
            char *q = malloc(8);
            if (q != p || __heap_used != used) return 2;
            for (int i = 0; i < 8; i++) q[i] = i + 40;
            for (int i = 0; i < 8; i++) if (q[i] != i + 40) return 3;
            free(q);
        """)

    def test_too_small_free_block_is_skipped(self):
        self.assert_program("""
            char *p = malloc(8);
            if (!p) return 1;
            free(p);
            char *q = malloc(12);
            if (!q || q == p) return 2;
            q[0] = 73; q[11] = 91;
            char *r = malloc(8);
            if (r != p) return 3;
            for (int i = 0; i < 8; i++) r[i] = 42;
            if (q[0] != 73 || q[11] != 91) return 4;
            free(r); free(q);
        """)

    def test_free_head_middle_and_tail_blocks_are_reachable(self):
        for index, name in enumerate(("a", "b", "c")):
            with self.subTest(index=index):
                checks = "\n".join(
                    f"if ({other}[0] != {20 + i} || {other}[31] != {60 + i}) return 3;"
                    for i, other in enumerate(("a", "b", "c"))
                    if i != index
                )
                self.assert_program(f"""
                    char *a = malloc(32); char *b = malloc(32); char *c = malloc(32);
                    if (!a || !b || !c) return 1;
                    a[0] = 20; a[31] = 60; b[0] = 21; b[31] = 61; c[0] = 22; c[31] = 62;
                    int used; used = __heap_used;
                    free({name});
                    char *q = malloc(32);
                    if (q != {name} || __heap_used != used) return 2;
                    q[0] = 99; q[31] = 100;
                    {checks}
                    free(a); free(b); free(c);
                """)

    def test_free_list_search_skips_live_and_undersized_blocks(self):
        self.assert_program("""
            char *large = malloc(64); char *live = malloc(32); char *small = malloc(8);
            if (!large || !live || !small) return 1;
            live[0] = 42; live[31] = 73;
            free(large); free(small);
            int used; used = __heap_used;
            char *q = malloc(48);
            if (q != large || __heap_used != used) return 2;
            char *r = malloc(8);
            if (r != small || q == r) return 3;
            q[0] = 11; q[47] = 12; r[0] = 13; r[7] = 14;
            if (live[0] != 42 || live[31] != 73) return 4;
            free(q); free(r); free(live);
        """)

    def test_reused_block_becomes_live_and_cannot_be_allocated_twice(self):
        self.assert_program("""
            char *p = malloc(32);
            if (!p) return 1;
            free(p);
            char *q = malloc(32); char *r = malloc(32);
            if (q != p || !r || q == r) return 2;
            q[0] = 42; r[0] = 73;
            if (q[0] != 42 || r[0] != 73) return 3;
            free(q); free(r);
        """)

    def test_repeated_allocate_free_cycles_do_not_leak_heap(self):
        self.assert_program("""
            char *p = malloc(64);
            if (!p) return 1;
            int used; used = __heap_used;
            free(p);
            for (int cycle = 0; cycle < 200; cycle++) {
                char *q = malloc(64);
                if (q != p) return 2;
                for (int i = 0; i < 64; i++) q[i] = (cycle + i) & 127;
                for (int i = 0; i < 64; i++) if (q[i] != ((cycle + i) & 127)) return 3;
                free(q);
                if (__heap_used != used) return 4;
            }
        """)

    def test_all_free_orders_preserve_reusability(self):
        for order in itertools.permutations(range(3)):
            with self.subTest(order=order):
                frees = "\n".join(
                    f"free((void *)read_slot(blocks, {index}));" for index in order
                )
                self.assert_program(
                    """
                    for (int i = 0; i < 3; i++) {
                        char *p = malloc(32);
                        write_slot(blocks, i, (int)p);
                        if (!read_slot(blocks, i)) return 1;
                    }
                    int used; used = __heap_used;
                """
                    + frees
                    + """
                    char *a = malloc(32); char *b = malloc(32); char *c = malloc(32);
                    if (!a || !b || !c) return 2;
                    if (a == b || a == c || b == c) return 3;
                    if (__heap_used != used) return 4;
                    free(a); free(b); free(c);
                """,
                    declarations="char blocks[12];",
                )

    def test_exact_remaining_capacity_and_one_byte_over_boundary(self):
        for excess in (0, 1, 4):
            with self.subTest(excess=excess):
                self.assert_program(f"""
                    int used; used = __heap_used;
                    int capacity = 16384 - used - sizeof(struct malloc_header);
                    if (capacity <= 0) return 1;
                    char *p = malloc(capacity + {excess});
                    if ({excess} != 0) {{
                        if (p != 0 || __heap_used != used) return 2;
                        p = malloc(capacity);
                    }}
                    if (!p || __heap_used != 16384) return 3;
                    p[0] = 42; p[capacity - 1] = 73;
                    if (p[0] != 42 || p[capacity - 1] != 73) return 4;
                    if (malloc(1) != 0 || __heap_used != 16384) return 5;
                    free(p);
                    char *q = malloc(capacity);
                    if (q != p || __heap_used != 16384) return 6;
                    free(q);
                """)

    def test_oversized_requests_fail_without_poisoning_later_allocations(self):
        for size in (
            16384,
            16385,
            65536,
            2147483644,
            2147483645,
            2147483646,
            2147483647,
        ):
            with self.subTest(size=size):
                self.assert_program(f"""
                    int used; used = __heap_used;
                    if (malloc({size}) != 0) return 1;
                    if (__heap_used != used) return 2;
                    char *p = malloc(16);
                    if (!p) return 3;
                    p[0] = 42; p[15] = 73;
                    if (p[0] != 42 || p[15] != 73) return 4;
                    free(p);
                """)

    def test_exhaustion_preserves_live_data_and_free_recovers_capacity(self):
        self.assert_program(
            """
            int count = 0; int exhausted = 0;
            while (count < 80 && !exhausted) {
                char *p = malloc(256);
                if (!p) { exhausted = 1; }
                else {
                    write_slot(blocks, count, (int)p);
                    for (int i = 0; i < 256; i++) p[i] = (count + i) & 127;
                    count = count + 1;
                }
            }
            if (count == 0 || count == 80) return 1;
            int used; used = __heap_used;
            if (malloc(256) != 0 || __heap_used != used) return 2;
            for (int slot = 0; slot < count; slot++) {
                char *p = (char *)read_slot(blocks, slot);
                for (int i = 0; i < 256; i++) {
                    if (p[i] != ((slot + i) & 127)) return 3;
                }
            }
            free((void *)read_slot(blocks, count / 2));
            char *q = malloc(256);
            if ((int)q != read_slot(blocks, count / 2) || __heap_used != used) return 4;
            if (malloc(256) != 0) return 5;
            for (int slot = 0; slot < count; slot++) free((void *)read_slot(blocks, slot));
        """,
            declarations="char blocks[320];",
        )

    def test_reinitializing_heap_restores_capacity(self):
        self.assert_program("""
            int initial; initial = __heap_used;
            char *p = malloc(1024);
            if (!p || __heap_used <= initial) return 1;
            init_heap();
            if (__heap_used != initial) return 2;
            char *q = malloc(1024);
            if (!q || q != p) return 3;
            q[0] = 42; q[1023] = 73;
            if (q[0] != 42 || q[1023] != 73) return 4;
            free(q);
        """)

    def test_deterministic_mixed_allocations_preserve_every_live_payload(self):
        # Generate only valid frees; the Python model records each live size and
        # pattern independently of the allocator and verifies every byte.
        declarations = """
            char blocks[32];
            int verify_block(char *p, int size, int pattern) {
                if (p < __heap_area || p + size > __heap_area + 16384) return 1;
                for (int i = 0; i < size; i++) {
                    if (p[i] != ((i + pattern) & 127)) return 2;
                }
                return 0;
            }
        """
        for seed in (0, 17, 2026):
            with self.subTest(seed=seed):
                rng = random.Random(seed)
                live = {}
                operations = []
                for step in range(100):
                    empty = [slot for slot in range(8) if slot not in live]
                    if live and (not empty or rng.random() < 0.45):
                        slot = rng.choice(sorted(live))
                        operations.append(
                            f"q = (char *)read_slot(blocks, {slot}); free(q);"
                        )
                        del live[slot]
                    else:
                        slot = rng.choice(empty)
                        size = rng.choice((1, 3, 4, 5, 7, 16, 31, 64, 127))
                        pattern = rng.randrange(1, 128)
                        operations.append(f"""
                            p = (char *)malloc({size});
                            if (!p) return {step * 10 + 1};
                            if (((int)p & 3) != 0) return {step * 10 + 2};
                        """)
                        for other, (other_size, _) in sorted(live.items()):
                            operations.append(f"""
                                q = (char *)read_slot(blocks, {other});
                                if (p < q + {other_size} && q < p + {size}) return {step * 10 + 3};
                            """)
                        live[slot] = (size, pattern)
                        operations.append(f"""
                            write_slot(blocks, {slot}, (int)p);
                            for (int i = 0; i < {size}; i++) p[i] = (i + {pattern}) & 127;
                        """)
                    for other, (size, pattern) in sorted(live.items()):
                        operations.append(f"""
                            q = (char *)read_slot(blocks, {other});
                            if (verify_block(q, {size}, {pattern}) != 0) return {step * 10 + 4};
                        """)
                operations.extend(
                    f"q = (char *)read_slot(blocks, {slot}); free(q);"
                    for slot in sorted(live)
                )
                self.assert_program(
                    "char *p; char *q;\n" + "\n".join(operations),
                    declarations=declarations,
                )

    def test_instruction_budget_exhaustion_is_a_failure(self):
        with self.assertRaisesRegex(AssertionError, "did not terminate at BREAK"):
            _run_compiled_source(
                "int main() { while (1) {} return 0; }", max_steps=1000
            )


if __name__ == "__main__":
    unittest.main()
