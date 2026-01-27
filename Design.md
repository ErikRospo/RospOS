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

`rd`: destination register (4 bits encoding r0–r15)
`rs`, `rs1`, `rs2`: source registers (4 bits encoding r0–r15)
`imm`: immediate value (16 bits for arithmetic, 12 bits for load/store/branch)
`offset`: memory offset (12 bits, signed)
`*`: unused bits (set to 0)

### Arithmetic & Logic

| Instruction     | Syntax             | Description               | Binary Encoding |
| --------------- | ------------------ | ------------------------- | ---------------- |
| ADD             | `ADD rd, rs1, rs2` | rd = rs1 + rs2            | `0000 0000 | rd | rs1 | rs2` |
| ADDI            | `ADDI rd, rs, imm` | rd = rs + imm             | `0000 0001 | rd | rs | imm`  |
| SUB             | `SUB rd, rs1, rs2` | rd = rs1 - rs2            | `0000 0010 | rd | rs1 | rs2` |
| NEG             | `NEG rd, rs`       | rd = -rs                  | `0000 0011 | rd | rs | 0000` |
| AND             | `AND rd, rs1, rs2` | Bitwise AND               | `0000 0100 | rd | rs1 | rs2` |
| OR              | `OR rd, rs1, rs2`  | Bitwise OR                | `0000 0101 | rd | rs1 | rs2` |
| XOR             | `XOR rd, rs1, rs2` | Bitwise XOR               | `0000 0110 | rd | rs1 | rs2` |
| ANDI            | `ANDI rd, rs, imm` | Bitwise AND immediate     | `0000 0111 | rd | rs | imm`  |
| ORI             | `ORI rd, rs, imm`  | Bitwise OR immediate      | `0000 1000 | rd | rs | imm`  |
| XORI            | `XORI rd, rs, imm` | Bitwise XOR immediate     | `0000 1001 | rd | rs | imm`  |
| NOT             | `NOT rd, rs`       | rd = ~rs                  | `0000 1010 | rd | rs | 0000` |
| SHL             | `SHL rd, rs, imm`  | Logical shift left        | `0000 1011 | rd | rs | imm`  |
| SHR             | `SHR rd, rs, imm`  | Logical shift right       | `0000 1100 | rd | rs | imm`  |
| SAR             | `SAR rd, rs, imm`  | Arithmetic shift right    | `0000 1101 | rd | rs | imm`  |

### Multiply/Divide

| Instruction | Syntax              | Description        | Binary Encoding |
| ----------- | ------------------- | ------------------ | ---------------- |
| MUL         | `MUL rd, rs1, rs2`  | Signed multiply    | `0000 1110 | rd | rs1 | rs2` |
| MULH        | `MULH rd, rs1, rs2` | Optional high bits | `0000 1111 | rd | rs1 | rs2` |
| DIV         | `DIV rd, rs1, rs2`  | Signed division    | `0001 0000 | rd | rs1 | rs2` |
| DIVU        | `DIVU rd, rs1, rs2` | Unsigned division  | `0001 0001 | rd | rs1 | rs2` |
| REM         | `REM rd, rs1, rs2`  | Remainder          | `0001 0010 | rd | rs1 | rs2` |
| REMU        | `REMU rd, rs1, rs2` | Unsigned remainder | `0001 0011 | rd | rs1 | rs2` |

### Load/Store

| Instruction | Syntax              | Notes          | Binary Encoding |
| ----------- | ------------------- | -------------- | ---------------- |
| LB          | `LB rd, offset(rs)` | Load byte      | `0001 0100 | rd | rs | offset` |
| LBU         | `LBU rd, offset(rs)`| Load byte unsigned | `0001 0101 | rd | rs | offset` |
| LH          | `LH rd, offset(rs)` | Load halfword  | `0001 0110 | rd | rs | offset` |
| LHU         | `LHU rd, offset(rs)`| Load halfword unsigned | `0001 0111 | rd | rs | offset` |
| LW          | `LW rd, offset(rs)` | Load word      | `0001 1000 | rd | rs | offset` |
| SB          | `SB rs, offset(rd)` | Store byte     | `0001 1001 | rs | rd | offset` |
| SH          | `SH rs, offset(rd)` | Store halfword | `0001 1010 | rs | rd | offset` |
| SW          | `SW rs, offset(rd)` | Store word     | `0001 1011 | rs | rd | offset` |

### Branch & Jump

| Instruction | Syntax               | Description          | Binary Encoding |
| ----------- | -------------------- | -------------------- | ---------------- |
| BEQ         | `BEQ rs1, rs2, imm`  | Branch if equal      | `0001 1100 | rs1 | rs2 | imm` |
| BNE         | `BNE rs1, rs2, imm`  | Branch if not equal  | `0001 1101 | rs1 | rs2 | imm` |
| BLT         | `BLT rs1, rs2, imm`  | Branch if less than  | `0001 1110 | rs1 | rs2 | imm` |
| BGE         | `BGE rs1, rs2, imm`  | Branch if greater/equal | `0001 1111 | rs1 | rs2 | imm` |
| BLTU        | `BLTU rs1, rs2, imm` | Unsigned less than   | `0010 0000 | rs1 | rs2 | imm` |
| BGEU        | `BGEU rs1, rs2, imm` | Unsigned greater/equal | `0010 0001 | rs1 | rs2 | imm` |
| JAL         | `JAL rd, imm`        | Jump + link (call)   | `0010 0010 | rd | imm` |
| JALR        | `JALR rd, rs, imm`   | Jump register + link | `0010 0011 | rd | rs | imm` |

### System / Privileged

| Instruction | Syntax   | Description          | Binary Encoding |
| ----------- | -------- | -------------------- | ---------------- |
| ECALL       | `ECALL`  | Trap to OS / syscall | `0010 0100 | 0000*` |
| SRET        | `SRET`   | Return from trap     | `0010 0101 | 0000*` |
| EBREAK      | `EBREAK` | Debug / breakpoint   | `0010 0110 | 0000*` |
| NOP         | `NOP`    | NOP                  | `1111 1111 | 0000*`

### Other

All other opcodes should be treated as NOPs, but this behavior should not be relied upon. The only designated NOP is opcode `0xFF`.


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

### Interrupts
* Vector table at `0xFFFF0000`
* Basic interrupt handling:
  * Save registers r1–r13
  * Save PC to r13
  * Jump to handler
* It is up to the caller to restore state and return via `SRET`

### Reset Behavior
* Clear registers r1–r13 to 0
* Stack pointer (r14) initialized to top of RAM (`0x0FFFFFFF`)
* PC set to `0x00000000`
* Execution begins

## Instruction Encoding

* Fixed 32-bit instructions
* 3-operand format where possible: `opcode | rd | rs1 | rs2/imm`
