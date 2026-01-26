# RospOS 32-bit RISC CPU ISA

Goal:
* 32-bit RISC CPU ISA
* Small OS atop ISA (*RospOS*)
* `sh`-like shell
* `bc`-like calculator
* `nano`-like text editor

* `Audio`: SID-like synth
* `Display`: 128×128 monochrome framebuffer
* `TTY`: terminal interface

Design principles:

* Orthogonal instruction set
* Load/store architecture (RISC)
* Simple, fixed-size 32-bit instructions
* Memory-mapped I/O for hardware devices


## Register File

| Register | Purpose              | Notes                          |
| -------- | -------------------- | ------------------------------ |
| r0       | Constant 0           | Always reads 0, writes ignored |
| r1–r13   | General purpose      | Used freely by programs        |
| r14      | Stack pointer (SP)   | Stack grows downward           |
| r15      | Program counter (PC) | Automatically updated          |

* ABI convention:
  * Caller-saved: r1–r7
  * Callee-saved: r8–r13


## Instruction Set

### Arithmetic & Logic

| Instruction     | Syntax             | Description               |
| --------------- | ------------------ | ------------------------- |
| ADD             | `ADD rd, rs1, rs2` | rd = rs1 + rs2            |
| ADDI            | `ADDI rd, rs, imm` | rd = rs + imm             |
| SUB             | `SUB rd, rs1, rs2` | rd = rs1 - rs2            |
| NEG             | `NEG rd, rs`       | rd = -rs                  |
| AND, OR, XOR    | `AND rd, rs1, rs2` | Bitwise operations        |
| ANDI, ORI, XORI | `ANDI rd, rs, imm` | Immediate versions        |
| NOT             | `NOT rd, rs`       | rd = ~rs                  |
| SHL, SHR, SAR   | `SHL rd, rs, imm`  | Logical/arithmetic shifts |

### Multiply/Divide

| Instruction | Syntax              | Description        |
| ----------- | ------------------- | ------------------ |
| MUL         | `MUL rd, rs1, rs2`  | Signed multiply    |
| MULH        | `MULH rd, rs1, rs2` | Optional high bits |
| DIV         | `DIV rd, rs1, rs2`  | Signed division    |
| DIVU        | `DIVU rd, rs1, rs2` | Unsigned division  |
| REM/REMU    | `REM rd, rs1, rs2`  | Remainder          |


### Load/Store

| Instruction | Syntax              | Notes          |
| ----------- | ------------------- | -------------- |
| LB, LBU     | `LB rd, offset(rs)` | Load byte      |
| LH, LHU     | `LH rd, offset(rs)` | Load halfword  |
| LW          | `LW rd, offset(rs)` | Load word      |
| SB          | `SB rs, offset(rd)` | Store byte     |
| SH          | `SH rs, offset(rd)` | Store halfword |
| SW          | `SW rs, offset(rd)` | Store word     |

* Addressing: `base + signed immediate`
* Unaligned: trap, possibly allow interupt?


### Branch & Jump

| Instruction | Syntax               | Description          |
| ----------- | -------------------- | -------------------- |
| BEQ         | `BEQ rs1, rs2, imm`  | Branch if equal      |
| BNE         | `BNE rs1, rs2, imm`  | Branch if not equal  |
| BLT/BGE     | `BLT rs1, rs2, imm`  | Signed comparisons   |
| BLTU/BGEU   | `BLTU rs1, rs2, imm` | Unsigned comparisons |
| JAL         | `JAL rd, imm`        | Jump + link (call)   |
| JALR        | `JALR rd, rs, imm`   | Jump register + link |

* Branches: relative to PC
* JAL/JALR: return address written to `rd`


### System / Privileged

| Instruction | Syntax   | Description          |
| ----------- | -------- | -------------------- |
| ECALL       | `ECALL`  | Trap to OS / syscall |
| SRET        | `SRET`   | Return from trap     |
| EBREAK      | `EBREAK` | Debug / breakpoint   |


## Memory Map

| Address Range         | Purpose                    | Size / Notes                           |
| --------------------- | -------------------------- | -------------------------------------- |
| 0x00000000–0x0FFFFFFF | RAM                        | Program + stack + heap                 |
| 0x10000000–0x1000FFFF | TTY                        | Read input / write output              |
| 0x20000000–0x20000FFF | Display (128×128 2-bit)    | 4096 bytes linear framebuffer          |
| 0x30000000–0x3000FFFF | Audio (SID-like)           | freq, waveform, volume, gate registers |
| 0xFFFF0000–0xFFFFFFFF | Kernel / interrupt vectors | Reserved                               |


## Calling Convention (ABI)

* Stack grows downward (`r14` = SP)
* Function call:
  * Arguments: r1–r4 (or stack if >4)
  * Return: r1
* Caller saves: r1–r7
* Callee saves: r8–r13
* Return: `RET = JALR r0, r1, 0`


##  I/O / Virtual Hardware Design

### TTY

* Memory-mapped at `0x10000000`
* Write byte → output
* Read byte → blocking input

### Display

* 128×128*2 bits = 4096 bytes at `0x20000000`
* Simple framebuffer: 2 bits per pixel (BLACK, DARK GREY, LIGHT GREY, WHITE), linear layout
* Optional: dirty flag for partial refresh

### Audio

* Memory-mapped registers:
  * Frequency
  * Waveform
  * Volume
  * Gate (on/off)
* Simple write-only interface


## Instruction Encoding

* Fixed 32-bit instructions
* 3-operand format where possible: `opcode | rd | rs1 | rs2/imm`
