Plan: Emit .ros From C AST

TL;DR — Emit readable .ros from the C AST and feed it to the existing assembler. Create a small emitter in `rospocc/` that walks AST nodes (function_def, declarations, statements, expressions) and emits .ros directives/instructions that match examples (see [rospos/main.ros](../rospos/main.ros) and [rospos/tty.ros](../rospos/tty.ros)). Use a simple ABI (as specified) and a function-prologue stack-frame allocation. Start minimal (locals, control flow, calls, globals, strings) and iterate with tests that assemble via `rospoas/compile.py`.

Steps
1. Create emitter scaffolding: add `rospocc/emitter.py` with entry `emit_translation_unit(ast, out_path)` and helper functions `emit_function_def`, `emit_global_declaration`, `emit_statement`, `emit_expr`, `gen_label`.
2. Add ABI constants: create `rospocc/abi.py` exporting `ARG_REGS`, `RETURN_REG`, `LINK_REG`, `SP_REG`, `CALLER_SAVED`, `CALLEE_SAVED`, `TEMP_REG` based on the ABI (r1-r4 args; r1 return; r14 LR; r15 SP; caller/callee sets).
3. Implement function emission in emitter:
   - Emit `.FUNC NAME:` label and optional `.SEG`/`.DATA` for globals.
   - Emit prologue: compute frame size, `ADDI sp, sp, -frame_size`, save `callee-saved` used via `PUSH` pseudos or `SW`.
   - Emit body by lowering AST statements to sequences of .ros instructions (use simple register allocation — free list over registers r2..r12; spill with `PUSH`/`POP` when exhausted).
   - Emit epilogue: restore saved regs, `ADDI sp, sp, frame_size`, then `RET` (ensure return value in r1).
4. Expression & statement lowering:
   - Binary/arithmetic: map to `ADD/ADDI/SUB/MUL/` etc. Use immediate ops when small constants; use `LLI` pseudo for 32-bit immediates or label addresses.
   - Loads/stores/arrays: compute address into a register then `LB/LW/SB/SW`.
   - Control flow: generate unique labels for loop/if boundaries and use `BEQ/BNE/BLT/BGE` appropriately.
   - Calls: place args into `ARG_REGS`, emit `CALL label` pseudo (assembler lowers CALL to jalr and sets r14).
5. Globals & constants:
   - Emit `.SEG` and `.DATA/.STR/.SPACE` for global declarations and string literals. Give each string a generated label and use that label where needed.
6. Integration and tests:
   - Emit `.ros` to `rospocc/out/generated.ros`.
   - Assemble with `rospoas/compile.py` to produce `.rosp` and run on VM binary in `rospovm/` or unit tests.
7. Optional: later replace textual emission with a direct emitter into `rospoas.ir` objects if you want tighter integration (`rospocc/emitter_ir.py`).

Verification
- Emit a small test (e.g., `print_string`, `read_char`, `main`) from the AST to `rospocc/out/generated.ros` and assemble:

```bash
python3 -m rospocc.emitter   # or: python3 rospocc/emitter.py out/ast.txt out/generated.ros
python3 rospoas/compile.py rospocc/out/generated.ros -o rospocc/out/generated.rosp
# Optionally run VM (adjust path to built rospovm binary)
./rospovm/rospovm rospocc/out/generated.rosp
```

Decisions
- Emit textual .ros (feeds existing assembler) — chosen for fastest integration.
- ABI chosen from your input: `r1-r4` args (overflow to stack), `r1` return, `r14` link register, `r15` SP, callee-saved `r8-r12`, caller-saved `r1-r7,r13`.
- Local allocation: function prologue frame (`ADDI sp, sp, -N`) to cover locals and alignment; use push/pop spills only for temporaries when needed.

Next actions
- Implement `rospocc/emitter.py` skeleton and `rospocc/abi.py`.
- Add simple test that emits `main` from the existing AST and assembles it.

Notes
- This plan assumes emitting textual `.ros` is acceptable so existing `rospoas` pipeline can be reused. If you prefer a direct-IR emitter, we can implement `rospocc/emitter_ir.py` instead.
