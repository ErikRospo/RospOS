# Copilot Instructions for RospOS Codebase

Welcome to the RospOS project! This document provides essential guidance for AI coding agents to be productive in this codebase. It outlines the architecture, workflows, conventions, and integration points specific to this project.

## Project Overview

RospOS is a multi-component system with the following major parts:

1. **`rospoas/`**: Contains the code for parsing, transforming, and compiling RospOS Assembly (ROS) code. Key files include:
   - `grammar_parser.py`: Defines the grammar for parsing ROS code.
   - `transformer.py`: Handles AST transformations.
   - `lower.py`: Lowers high-level constructs to low-level instructions.
    - `rospoas.lark`: Lark grammar file defining the syntax of RospOS Assembly.
   - `compile.py`: Coordinates the compilation process.

2. **`rospos/`**: Contains the RospOS Assembly (ROS) source files and build artifacts. Key files include:
   - `main.ros`: The main entry point for the ROS program.
   - `build/`: Stores intermediate and final build outputs.

3. **`rospovm/`**: Implements the RospOS Virtual Machine (VM) in C++. Key files include:
   - `RospOSVM.cpp`: The main VM implementation.
   - `InstructionDecoder.cpp`: Decodes and executes instructions.
   - `Makefile`: Defines the build process for the VM.


## Project-Specific Conventions

- **File Extensions**:
  - `.ros`: RospOS Assembly source files.
  - `.rosp`: Compiled RospOS binary files.

- **Code Organization**:
  - Python modules in `rospoas/` follow a clear pipeline: parsing → transformation → compilation.
  - C++ files in `rospovm/` are modular, with each file handling a specific VM component (e.g., `Memory.cpp` for VM memory management).

## Integration Points

- **Python-C++ Boundary**:
  The Python assembler (`rospoas/`) generates outputs consumed by the C++ VM (`rospovm/`). Ensure compatibility between the generated `.ros` files and the VM's instruction decoder.

- **External Dependencies**:
  - Python: Install dependencies listed in `rospoas/requirements.txt`.
  - C++: Requires `make` and a C++ compiler (e.g., `g++`).

## Examples

- **Adding a New Pseudoinstruction**:
  1. Update the grammar in `rospoas/rospoas.lark`.
  2. Modify `transformer.py` to either expand the pseudoinstruction into existing instructions or handle it as a new instruction.
  3. If handling as a new pseudoinstruction, update `lower.py` to convert it into a valid instruction sequence.

- **Debugging a Compilation Error**:
  1. Check the logs in `rospos/build/rospos_debug_parse.txt`.
  2. Trace the error back to the relevant Python module in `rospoas/`.

## Notes

- Follow the existing modular structure when adding new components.
- Ensure all changes are tested in both the Python and C++ parts of the project.
The venv is in ./rospoas/venv/bin/activate, source that then cd into rospocc and run the file. Keep imports as they are, e.g. from abi import foo, rather than from rospocc.abi or from rospocc import abi, etc. 
For further questions, refer to the source files or ask for clarification.