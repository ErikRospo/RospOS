# Instruction Encoding

Each instruction is 32 bits wide and follows a fixed format within each major opcode. The binary encoding is divided into fields as follows:

Major Opcode Legend (bits [31:28]):

- 0000 = R-type arithmetic (register)
- 0001 = I-type arithmetic/logical (immediate)
- 0010 = Load/Store
- 0011 = Branch
- 0100 = Jump
- 0101 = System / privileged
- 1111 = NOP / special

## R-Type Arithmetic / Logical (register)

| 31-28  | 27-24  | 23-20 | 19-16 | 15-12 | 11-0   |
| ------ | ------ | ----- | ----- | ----- | ------ |
| opcode | sub-op | rd    | rs1   | rs2   | unused |

| Instruction | Major Opcode | Sub-Opcode | Description                     |
| ----------- | ------------ | ---------- | ------------------------------- |
| ADD         | 0000         | 0000       | rd = rs1 + rs2                  |
| SUB         | 0000         | 0001       | rd = rs1 - rs2                  |
| AND         | 0000         | 0010       | rd = rs1 & rs2                  |
| OR          | 0000         | 0011       | rd = rs1 \| rs2                 |
| XOR         | 0000         | 0100       | rd = rs1 ^ rs2                  |
| MUL         | 0000         | 0101       | rd = rs1 \* rs2 (low 32 bits)   |
| MULH        | 0000         | 0110       | rd = high 32 bits of rs1 \* rs2 |
| NEG         | 0000         | 0111       | rd = -rs1                       |
| NOT         | 0000         | 1000       | rd = ~rs1                       |
| SHL         | 0000         | 1001       | rd = rs1 << (rs2 & 31)          |
| SHR         | 0000         | 1010       | rd = logical shift right        |
| SAR         | 0000         | 1011       | rd = arithmetic shift right     |
| DIV         | 0000         | 1100       | rd = rs1 / rs2 (signed)         |
| DIVU        | 0000         | 1101       | rd = rs1 / rs2 (unsigned)       |
| REM         | 0000         | 1110       | rd = rs1 % rs2 (signed)         |
| REMU        | 0000         | 1111       | rd = rs1 % rs2 (unsigned)       |

Division by zero behavior: sets rd to all 1s (`0xFFFFFFFF`).
Arithmetic operations (ADD, SUB, MUL, DIV, etc.) use two's complement representation for signed numbers.

## I-Type Arithmetic / Logical (immediate)

| 31-28  | 27-24  | 23-20 | 19-16 | 15-0                     |
| ------ | ------ | ----- | ----- | ------------------------ |
| opcode | sub-op | rd    | rs    | immediate (16-bit value) |

| Instruction | Major Opcode | Sub-Opcode | Description                        |
| ----------- | ------------ | ---------- | ---------------------------------- | ------------------- |
| ADDI        | 0001         | 0000       | rd = rs + _sign_-extended imm      |
| ANDI        | 0001         | 0001       | rd = rs & _zero_-extended imm      |
| ORI         | 0001         | 0010       | rd = rs                            | _zero_-extended imm |
| XORI        | 0001         | 0011       | rd = rs ^ _zero_-extended imm      |
| SHLI        | 0001         | 0100       | rd = rs << (imm & 31)              |
| SHRI        | 0001         | 0101       | rd = logical shift right by imm    |
| SARI        | 0001         | 0110       | rd = arithmetic shift right by imm |

Shifts (SHLI, SHRI, SARI) use only the lower 5 bits of the immediate for the shift amount, and are zero-extended.

## Load / Store (I-Type)

| 31-28  | 27-24  | 23-20 | 19-16 | 15-0                      |
| ------ | ------ | ----- | ----- | ------------------------- |
| opcode | sub-op | rd    | rs    | immediate (16-bit offset) |

| Instruction | Major Opcode | Sub-Opcode | Description                                  |
| ----------- | ------------ | ---------- | -------------------------------------------- |
| LB          | 0010         | 0000       | rd = sign-extended byte from rs + offset     |
| LBU         | 0010         | 0001       | rd = zero-extended byte from rs + offset     |
| LH          | 0010         | 0010       | rd = sign-extended halfword from rs + offset |
| LHU         | 0010         | 0011       | rd = zero-extended halfword from rs + offset |
| LW          | 0010         | 0100       | rd = word from rs + offset                   |
| SB          | 0010         | 0101       | store low byte rd → rs + offset              |
| SH          | 0010         | 0110       | store halfword rd → rs + offset              |
| SW          | 0010         | 0111       | store word rd → rs + offset                  |

## Branch (B-Type)

| 31-28  | 27-24  | 23-20 | 19-16 | 15-0                      |
| ------ | ------ | ----- | ----- | ------------------------- |
| opcode | sub-op | rs1   | rs2   | immediate (16-bit offset) |

| Instruction | Major Opcode | Sub-Opcode | Description                     |
| ----------- | ------------ | ---------- | ------------------------------- |
| BEQ         | 0011         | 0000       | branch if rs1 == rs2            |
| BNE         | 0011         | 0001       | branch if rs1 != rs2            |
| BLT         | 0011         | 0010       | branch if rs1 < rs2 (signed)    |
| BGE         | 0011         | 0011       | branch if rs1 >= rs2 (signed)   |
| BLTU        | 0011         | 0100       | branch if rs1 < rs2 (unsigned)  |
| BGEU        | 0011         | 0101       | branch if rs1 >= rs2 (unsigned) |

Branch target is computed as PC + sign-extended immediate in instructions.

```
target = PC + (sign-ext(imm) << 2)
```

## Jump (J-Type)

| 31-28  | 27-24  | 23-20 | 19-16 | 15-0                      |
| ------ | ------ | ----- | ----- | ------------------------- |
| opcode | sub-op | rd    | rs    | immediate (16-bit offset) |

| Instruction | Major Opcode | Sub-Opcode | Description                           |
| ----------- | ------------ | ---------- | ------------------------------------- |
| JAL         | 0100         | 0000       | jump PC+imm, rd = return address      |
| JALR        | 0100         | 0001       | jump to rs + imm, rd = return address |

Similar to branch target calculation, jump target is computed as:

```
target = PC + (sign-ext(imm) << 2)
rd = PC + 4
```

## System / Privileged (S-Type)

| 31-28  | 27-24  | 23-0   |
| ------ | ------ | ------ |
| opcode | sub-op | unused |

| Instruction | Major Opcode | Sub-Opcode | Description                |
| ----------- | ------------ | ---------- | -------------------------- |
| ECALL       | 0101         | 0000       | environment call / syscall |
| BREAK       | 0101         | 0001       | breakpoint / debug trap    |

## NOP / Special (S-Type)

| 31-28  | 27-24  | 23-0   |
| ------ | ------ | ------ |
| opcode | sub-op | unused |

| Instruction | Major Opcode | Sub-Opcode | Description  |
| ----------- | ------------ | ---------- | ------------ |
| NOP         | 1111         | 0000       | no operation |

Any opcode/sub-opcode combinations not listed above are reserved/invalid.
Executing an invalid instruction should trigger an illegal instruction exception.

NOTE: `0x00000000` is a valid NOP instruction, as it is ADD r0, r0, r0. (r0 is hardwired zero, so this is effectively a NOP.)
This allows for easier initialization of memory to zero.
