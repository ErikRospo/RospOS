# Copilot Instructions for RospOS Codebase

Welcome to the RospOS project! This document provides essential guidance for AI coding agents to be productive in this codebase. It outlines the architecture, workflows, conventions, and integration points specific to this project.

## Project Overview

RospOS is a complete compiler and virtual machine system with the following major components:

1. **`rospocc/`**: C-like language compiler that translates `.rosc` (C-style) source files into `.ros` assembly. This is the frontend that allows developers to write in higher-level C-like syntax. Key files include:
   - `parser.py`: Entry point that parses `.rosc` files and outputs `.ros`.
   - `transformer_tu.py`, `transformer_stmt.py`, `transformer_expr.py`: AST transformation stages.
   - `emitter.py`: Main code generator that orchestrates ROS emission.
   - `register_allocator.py`: Handles register allocation for compiled code.
   - `abi.py`: ABI definitions (calling conventions, register assignments).
   - `rosc.lark`: Lark grammar defining C-like syntax.

2. **`rospoas/`**: RospOS Assembler—the backend that takes `.ros` assembly and generates `.rosp` binary files. Implements the full 8-stage compilation pipeline: preprocess → parse → transform → optimize → lower → layout → encode → binary. Key files include:
   - `compile.py`: Entry point and CLI parser.
   - `compilation_pipeline.py`: Core pipeline orchestration and frontend registry.
   - `grammar_parser.py`: Parses `.ros` files using Lark.
   - `transformer.py`: Converts parse trees to Intermediate Representation (IR).
   - `optimizer.py`: IR optimization passes.
   - `lower.py`: Expands pseudo-instructions into concrete instruction sequences.
   - `layout.py`: Single-pass address computation and segment allocation.
   - `encode.py`: Bytecode generation and immediate resolution.
   - `debug_writer.py`: Generates debug segments and register allocation metadata.
   - `ir.py`: IR type definitions (Instruction, Immediate variants, Directive, Relocation).
   - `maps.py`: Instruction encoding maps (opcode tables, register maps).
   - `rospoas.lark`: Grammar defining RospOS Assembly syntax.

3. **`rospos/`**: Application source code directory containing the program being compiled. Key files include:
   - `main.rosc`: Main entry point (C-like syntax).
   - `lib/`: Standard library (stdio.rosc, display.rosc, stdlib.rosc).
   - `build/`: Intermediate and final compilation artifacts (intermediate assembly, binaries, debug info).

4. **`rospovm/`**: RospOS Virtual Machine implementation in C++. Executes compiled `.rosp` binaries with two frontend options (Qt GUI and headless CLI). Key backend components include:
   - `RospOSVM.cpp/h`: Main VM class with execution loop, state snapshots for debugging.
   - `InstructionDecoder.cpp/h`: Decodes and executes RospOS instructions.
   - `Memory.cpp/h`: 32-bit address space memory management.
   - `Register.cpp/h`: 16-register file management.
   - `Binary.cpp/h`: Binary loader and debug info parser.
   - `Display.cpp/h`, `TTY.cpp/h`: Display and terminal I/O (ECALL system calls).
   - `DebugParser.cpp/h`: Parses debug segments from binaries.
   - `Logger.cpp/h`: Execution logging and instruction tracing.
   - `BlockDevice.cpp/h`: Block device I/O simulation.
   - `CMakeLists.txt`: CMake build configuration.


## Project-Specific Conventions

- **File Extensions**:
  - `.rosc`: C-like source files (input to rospocc compiler).
  - `.ros`: RospOS Assembly source files (output of rospocc, input to rospoas).
  - `.rosp`: Compiled RospOS binary files (output of rospoas, input to rospovm).
  - `.rosc.debug`: Sidecar file containing source location and debug metadata from rospocc.
  - `.rosc.regalloc`: Sidecar file containing register allocation information from rospocc.

- **Code Organization**:
  - Python compilation pipeline follows clear stages: rospocc (frontend) → rospoas (backend with 8-stage pipeline, each with specialized modules).
  - C++ VM is modular with each component handling a specific responsibility (Memory, Register, Display, I/O, etc.).
  - Each major stage in rospoas has its own module (optimize.py, lower.py, layout.py, encode.py, etc.).

- **Binary Format**:
  - Binaries include magic header `0x50534F52` ('ROSP'), version field, and multiple segments (code, data, debug, relocation).
  - Supports compression (`--compress-debug`, `--compress-bin`) using gzip for reduced file sizes.
  - Four compilation variants are typically generated:
    - `.rosp`: Full binary with uncompressed debug info.  
    - `_debc.rosp`: Binary with compressed debug info.
    - `_binc.rosp`: Compressed binary with uncompressed debug info.
    - `_c.rosp`: Both binary and debug info compressed.

## Integration Points

### Compilation Pipeline Flow
```
.rosc (C-like source)
    ↓ rospocc/parser.py
.ros (Assembly) + .rosc.debug + .rosc.regalloc (sidecar metadata)
    ↓ rospoas/compile.py (8-stage pipeline)
    ├─ Preprocess: Handle includes and origin mapping
    ├─ Parse: Lark grammar → parse tree
    ├─ Transform: Parse tree → IR
    ├─ Optimize: Dead move elimination, jump optimization, etc.
    ├─ Lower: Expand pseudo-instructions to concrete sequences
    ├─ Layout: Single-pass address computation and segment allocation
    ├─ Encode: Resolve immediates and generate bytecode
    └─ Binary: Write .rosp with debug segments and optional compression
    ↓
.rosp (Binary) + debug segments
    ↓ rospovm (C++ VM)
VM execution (Qt GUI or headless CLI)
```

### Python-C++ Boundary
The Python assembler (`rospoas/`) generates binary outputs consumed by the C++ VM (`rospovm/`). Key compatibility requirements:
- Instruction encoding in `rospoas/maps.py` must match decoding in `rospovm/backend/InstructionDecoder.cpp`.
- Binary version field (set via `--bin-version`) must be compatible with VM's loader.
- Debug segment format generated by `rospoas/debug_writer.py` must be parseable by `rospovm/backend/DebugParser.cpp`.

### rospocc to rospoas Integration
- `rospocc/parser.py` emits `.ros` files that are valid inputs to `rospoas/compile.py`.
- Sidecar files (`.rosc.debug`, `.rosc.regalloc`) carry metadata used by:
  - `rospoas/register_alloc_reader.py`: Reads register allocations.
  - `rospoas/debug_writer.py`: Enriches debug segments with source location info.
- This allows the VM to show source-level debugging information during execution.

### ABI and Calling Conventions
Defined in `rospocc/abi.py`:
- Argument registers: `r1`, `r2`, `r3`, `r4`
- Return register: `r1`
- Link register: `r14`
- Stack pointer: `r15`
- Temporary registers: `r2`–`r13` (allocatable)

### External Dependencies
- Python: Install dependencies listed in `rospoas/requirements.txt`.
- C++: Requires CMake, make, and a C++ compiler (e.g., `g++`).
- Qt: Required only for GUI frontend (`rospovm_qt`); headless VM has no GUI dependency.

## Usage Examples and Common Tasks

### Building and Running the Project
```bash
# Use the main Makefile
make parse              # Compile .rosc → .ros (rospocc frontend)
make compile            # Compile .ros → .rosp binaries (rospoas backend, generates 4 variants)
make frontend_cmake     # Configure CMake for VM
make frontend           # Build Qt GUI VM
make vm_headless        # Build headless CLI VM
make run                # Run with GUI
make run_headless       # Run CLI version
make build              # Full pipeline (parse, compile, build VM)
```

### Adding a New Built-in Function
1. Define intrinsic in `rospocc/emitter_intrinsics.py`.
2. Add parsing rules to `rospocc/rosc.lark` if new syntax is needed.
3. Emit appropriate ROS instructions from `rospocc/emitter_expr.py` or `emitter_stmt.py`.
4. Test compilation with `make parse`.
5. Verify execution with `make run_headless`.

### Adding a New Pseudoinstruction or Instruction Type
1. Update grammar in `rospoas/rospoas.lark` to add parsing rules.
2. Modify `rospoas/transformer.py` to handle in IR transformation.
3. If pseudoinstruction, add lowering logic in `rospoas/lower.py` to expand into concrete instructions.
4. Update encoding maps in `rospoas/maps.py` to define opcode and operand layout.
5. Update `rospovm/backend/InstructionDecoder.cpp` to decode and execute the instruction.
6. Test with `make compile` and `make run_headless`.

### Debugging a Compilation Error
1. Check Python compiler output in the terminal.
2. Review intermediate artifacts in `rospos/build/`:
   - `rospos_parse.txt`: Parser output and AST
   - `rospos_ir.txt`: IR after transformation
   - `rospos_debug_before_opt.txt`: IR before optimization
   - `rospos_debug_after_opt.txt`: IR after optimization
   - `rospos_debug_opt_log.txt`: Optimization pass details
   - `rospos_layout.txt`: Memory layout and address assignments
   - `rospos_mapping.txt`: Instruction encoding details
3. Trace error back to relevant module (rospocc or rospoas stages).
4. For C source errors, check `.rosc.debug` sidecar for source line info.

### Debugging Runtime Execution
1. Build with `make build` to enable debug info in binary.
2. Run with `make run` (Qt GUI) for interactive debugging:
   - Step through instructions
   - Inspect memory and registers
   - View source-level locations (from .rosc.debug)
3. Or use `make run_headless` with logger output to trace execution.
4. Review `rospovm/backend/Logger.cpp` for execution tracing capabilities.

### Modifying the ISA (Instruction Set)
1. Add instruction definition to `rospoas/maps.py`:
   - Define opcode value
   - Specify instruction type (R, I, L, B, J, S)
   - Add to instruction tables
2. Ensure rospocc can generate the instruction if needed.
3. Implement execution in `rospovm/backend/InstructionDecoder.cpp`.
4. Update `rospoas.lark` if assembly syntax changes.
5. Test coverage: compile a test program using the instruction, verify execution.

### Understanding Register Allocation
- `rospocc/register_allocator.py`: Allocates C variables to registers.
- Output stored in `.rosc.regalloc` sidecar file.
- `rospoas/register_alloc_reader.py`: Reads allocation metadata for debug info enrichment.
- ABI defines which registers are available for allocation (r2–r13).
- Registers r14 (link), r15 (stack pointer), r0 (zero) are reserved.

## Working with the Codebase

### Python Environment Setup
```bash
cd rospoas
source venv/bin/activate  # Activate virtual environment
cd ../rospocc
# Now ready to run rospocc/parser.py or rospoas/compile.py
```

### Import Conventions
Follow the existing pattern of **relative imports**:
```python
# Correct (within rospocc/):
from abi import ABI_INFO
from emitter import Emitter

# Incorrect - avoid these:
from rospocc.abi import ABI_INFO  # Don't use full module paths
from rospocc import abi

# Same applies in rospoas/:
from ir import Instruction
from maps import OPCODE_MAP
```

### Key Debugging Artifacts
All compilation artifacts are written to `rospos/build/`:
- **AST and IR dumps**: `rospos_ast.json`, `tu.json`, `rospos_ir.txt`
- **Optimization logs**: `debug_before_opt.txt`, `debug_after_opt.txt`, `debug_opt_log.txt`
- **Layout information**: `rospos_layout.txt` (memory addresses and segments)
- **Encoding details**: `rospos_mapping.txt` (instruction encodings)
- **Parse trees**: `rospos_parse.txt`, `rospos_preprocessed.ros`
- **Register allocation**: `rospos.rosc.regalloc` (sidecar)
- **Debug metadata**: `rospos.rosc.debug` (sidecar), `rospos_debug_segments.txt`
- **Binary variants**: 
  - `rospos.rosp` (full)
  - `rospos_debc.rosp` (compressed debug)
  - `rospos_binc.rosp` (compressed binary)
  - `rospos_c.rosp` (both compressed)

### Testing Changes
After modifying rospocc or rospoas:
```bash
make parse              # Test rospocc frontend
make compile            # Test rospoas backend
make run_headless       # Test VM execution
```

For isolated testing of specific modules, use:
```bash
cd rospoas
python compile.py --help          # See all CLI options
python compile.py --input <file>  # Compile directly

cd ../rospocc
python parser.py --help           # See compiler options
python parser.py --input <file>   # Parse C source
```

### Instruction Encoding
The full ISA is defined in `rospoas/maps.py`:
- **6 instruction types**: R-type (register), I-type (immediate), L-type (load/store), B-type (branch), J-type (jump), S-type (system)
- **16-bit instructions** with variable operand widths depending on type
- Each type has specific opcode allocation and operand field definitions
- Verify encoding in `rospos_mapping.txt` output after compilation

### Test Coverage
- Use `tests/test_pipeline.py` to test the full compilation pipeline
- Add test cases for new features or instructions
- Ensure both rospocc and rospoas stages are tested separately when possible

## Notes

- Follow the existing modular structure when adding new components.
- Ensure all changes are tested in both the Python and C++ parts of the project.
- The venv is in `./rospoas/venv/bin/activate`; source it before running Python code.
- Keep imports as documented above (relative form, not full module paths).
- All compilation output goes to `rospos/build/`; review artifacts there for debugging.
- The VM supports interactive step-through debugging via the Qt GUI frontend.
- For further questions, refer to the source files or ask for clarification.
- In general, do not run python scripts directly from the command line; use the provided Makefile targets to ensure proper environment setup and artifact management.