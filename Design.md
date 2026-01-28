# RospOS 32-bit RISC CPU ISA

Goal:
* 32-bit RISC CPU ISA
* Small OS atop ISA (*RospOS*)
* `sh`-like shell
* `bc`-like calculator
* `nano`-like text editor

* `Audio`: SID-like synth
* `Display`: 128×128 2-bit framebuffer
* `TTY`: terminal interface

Design principles:

* Orthogonal instruction set
* Load/store architecture (RISC)
* Simple, fixed-size 32-bit instructions
* Memory-mapped I/O for hardware devices

For register file, see [Calling Convention (ABI)](#calling-convention-abi).

## Instruction Encoding

Each instruction is 32 bits wide and follows a fixed format. The binary encoding is divided into fields as follows:

Major Opcode Legend (bits [31:28]):
* 0000 = R-type arithmetic (register)
* 0001 = I-type arithmetic/logical (immediate)
* 0010 = Load/Store
* 0011 = Branch
* 0100 = Jump
* 0101 = System / privileged
* 1111 = NOP / special



### R-Type Arithmetic / Logical (register)

Bit fields:

| 31-28 | 27-24 | 23-20 | 19-16 | 15-12 | 11-0          |
|-------|-------|-------|-------|-------|---------------|
| opcode| sub-op|   rd  |  rs1  |  rs2  |   unused      |


| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| ADD         | 0000         | 0000       | rd = rs1 + rs2                       |
| SUB         | 0000         | 0001       | rd = rs1 - rs2                       |
| AND         | 0000         | 0010       | rd = rs1 & rs2                       |
| OR          | 0000         | 0011       | rd = rs1 | rs2                       |
| XOR         | 0000         | 0100       | rd = rs1 ^ rs2                       |
| MUL         | 0000         | 0101       | rd = rs1 * rs2 (low 32 bits)         |
| MULH        | 0000         | 0110       | rd = high 32 bits of rs1 * rs2       |
| NEG         | 0000         | 0111       | rd = -rs1                            |
| NOT         | 0000         | 1000       | rd = ~rs1                            |
| SHL         | 0000         | 1001       | rd = rs1 << (rs2 & 31)               |
| SHR         | 0000         | 1010       | rd = logical shift right             |
| SAR         | 0000         | 1011       | rd = arithmetic shift right          |
| DIV         | 0000         | 1100       | rd = rs1 / rs2 (signed)              |
| DIVU        | 0000         | 1101       | rd = rs1 / rs2 (unsigned)            |
| REM         | 0000         | 1110       | rd = rs1 % rs2 (signed)              |
| REMU        | 0000         | 1111       | rd = rs1 % rs2 (unsigned)            |

### I-Type Arithmetic / Logical (immediate)

Bit fields:

| 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
|-------|-------|-------|-------|--------------------------|
| opcode| sub-op|   rd  |  rs   | immediate (16-bit value) |


| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| ADDI        | 0001         | 0000       | rd = rs + sign-extended imm          |
| ANDI        | 0001         | 0001       | rd = rs & sign-extended imm          |
| ORI         | 0001         | 0010       | rd = rs | sign-extended imm          |
| XORI        | 0001         | 0011       | rd = rs ^ sign-extended imm          |
| SHLI        | 0001         | 0100       | rd = rs << (imm & 31)                |
| SHRI        | 0001         | 0101       | rd = logical shift right by imm      |
| SARI        | 0001         | 0110       | rd = arithmetic shift right by imm   |

### Load / Store (I-Type)
Bit fields:
| 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
|-------|-------|-------|-------|--------------------------|
| opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|

| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| LB          | 0010         | 0000       | rd = sign-extended byte from rs + offset |
| LBU         | 0010         | 0001       | rd = zero-extended byte from rs + offset |
| LH          | 0010         | 0010       | rd = sign-extended halfword from rs + offset |
| LHU         | 0010         | 0011       | rd = zero-extended halfword from rs + offset |
| LW          | 0010         | 0100       | rd = word from rs + offset |
| SB          | 0010         | 0101       | store low byte rd → rs + offset |
| SH          | 0010         | 0110       | store halfword rd → rs + offset |
| SW          | 0010         | 0111       | store word rd → rs + offset |

### Branch (B-Type)

Bit fields:

| 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
|-------|-------|-------|-------|--------------------------|
| opcode| sub-op|  rs1  |  rs2  | immediate (16-bit offset)|

| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| BEQ         | 0011         | 0000       | branch if rs1 == rs2
| BNE         | 0011         | 0001       | branch if rs1 != rs2
| BLT         | 0011         | 0010       | branch if rs1 < rs2 (signed)
| BGE         | 0011         | 0011       | branch if rs1 >= rs2 (signed)
| BLTU        | 0011         | 0100       | branch if rs1 < rs2 (unsigned)
| BGEU        | 0011         | 0101       | branch if rs1 >= rs2 (unsigned)

### Jump

Bit fields:

| 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
|-------|-------|-------|-------|--------------------------|
| opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|

| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| JAL         | 0100         | 0000       | jump PC-relative, rd = return address|
| JALR        | 0100         | 0001       | jump to rs + imm, rd = return address|

### System / Privileged

Bit fields:

| 31-28 | 27-24 | 23-0                             |
|-------|-------|----------------------------------|
| opcode| sub-op|   unused                         |


| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| ECALL       | 0101         | 0000       | environment call / syscall           |
| SRET        | 0101         | 0001       | return from syscall / supervisor mode|
| BREAK       | 0101         | 0010       | breakpoint / debug trap              |

### NOP / Special

Bit fields:

| 31-28 | 27-24 | 23-0                     |
|-------|-------|--------------------------|
| opcode| sub-op|        unused            |

| Instruction | Major Opcode | Sub-Opcode | Description                          |
|-------------|--------------|------------|--------------------------------------|
| NOP         | 1111         | 0000       | no operation                         |

Any opcode/sub-opcode combinations not listed above are reserved/invalid.
Executing an invalid instruction SHOULD be a NOP, but MUST NOT be relied upon. 

## Memory Map

| Address Range         | Purpose                    | Size / Notes                           |
| --------------------- | -------------------------- | -------------------------------------- |
| 0x00000000–0x0FFFFFFF | RAM                        | Program + stack + heap                 |
| 0x10000000–0x1000FFFF | TTY                        | Read input / write output              |
| 0x20000000–0x20000FFF | Display (128×128 2-bit)    | 4096 bytes linear framebuffer          |
| 0x30000000–0x3000FFFF | Audio (SID-like)           | freq, waveform, volume, gate registers |
| 0xFFFF0000–0xFFFFFFFF | Kernel / interrupt vectors | Reserved                               |


## Calling Convention (ABI)

r0   = hardwired zero
r1   = return value
r2–r5 = arg0–arg3
r6–r9 = caller-saved
r10–r12 = callee-saved
r13 = frame pointer
r14 = link register (return address)
r15 = stack pointer

Stack pointer is initialized to top of RAM (`0x0FFFFFFF`) on reset. Stack grows downward. 8-byte alignment.

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

### Reset Behavior
* Clear registers to 0
* Stack pointer (r15) initialized to top of RAM (`0x0FFFFFFF`)
* PC set to `0xFFFF0000` (start of kernel space)
* Execution begins