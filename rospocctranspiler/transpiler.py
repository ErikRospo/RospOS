#!/usr/bin/env python3
"""Simple RISC-V to .ros transpiler

Usage: python transpiler.py input.s -o output.ros

This tool performs a best-effort translation of common RISC-V textual
assembly patterns into a readable .ros assembly file for the RospOS
toolchain. It is intentionally conservative: unmapped instructions are
emitted as comments so you can iteratively add translations.

The script supports a small set of instructions and a register-name
mapping from RISC-V ABI names (zero, ra, sp, a0..a7, t0..t6, s0..s11)
to `rN` registers used in .ros files.
"""


from __future__ import annotations
import argparse
import sys
from pathlib import Path
from lark import Lark, Transformer, Token
import re

# --- Register mapping (RISC-V ABI to .ros) ---
REG_MAP = {
    'zero': 'r0',
    'gp': 'r1', 'tp': 'r2',
    't0': 'r3', 't1': 'r4', 't2': 'r5',
    's0': 'r6', 's1': 'r7',
    'a0': 'r8', 'a1': 'r9', 'a2': 'r10', 'a3': 'r11', 'a4': 'r12',
    'ra': 'r14', 'sp': 'r15',
}
for i in range(16):
    REG_MAP[f'x{i}'] = f'r{i}'
    REG_MAP[f'r{i}'] = f'r{i}'

def map_reg(token: str) -> str:
    t = str(token).strip().rstrip(',')
    return REG_MAP.get(t, t)


class RiscvTransformer(Transformer):
    def __init__(self):

        # --- Hybrid parsing logic ---
        from lark import Lark, Transformer
        import re

        REG_MAP = {
            'zero': 'r0',
            'gp': 'r1', 'tp': 'r2',
            't0': 'r3', 't1': 'r4', 't2': 'r5',
            's0': 'r6', 's1': 'r7',
            'a0': 'r8', 'a1': 'r9', 'a2': 'r10', 'a3': 'r11', 'a4': 'r12',
            'ra': 'r14', 'sp': 'r15',
        }
        for i in range(16):
            REG_MAP[f'x{i}'] = f'r{i}'
            REG_MAP[f'r{i}'] = f'r{i}'

        def map_reg(token: str) -> str:
            t = str(token).strip().rstrip(',')
            return REG_MAP.get(t, t)

        def parse_mem_operand(op: str):
            m = re.match(r"([\-0-9xXa-fA-F]+)\(([^)]+)\)", op.strip())
            if not m:
                return None
            imm, base = m.groups()
            return imm, map_reg(base)

        def translate_riscv_to_ros(op: str, operands: list[str]) -> str:
            o = op.lower()
            # --- Arithmetic ---
            if o == 'addi':
                if len(operands) == 3:
                    rd, rs1, imm = operands
                    return f"ADDI {map_reg(rd)}, {map_reg(rs1)}, {imm}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'add':
                if len(operands) == 3:
                    rd, rs1, rs2 = operands
                    return f"ADD {map_reg(rd)}, {map_reg(rs1)}, {map_reg(rs2)}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'sub':
                if len(operands) == 3:
                    rd, rs1, rs2 = operands
                    return f"SUB {map_reg(rd)}, {map_reg(rs1)}, {map_reg(rs2)}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'li':
                if len(operands) == 2:
                    rd, imm = operands
                    return f"LLI {map_reg(rd)}, {imm}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'lui':
                if len(operands) == 2:
                    rd, imm = operands
                    return f"LLI {map_reg(rd)}, {imm}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'mv':
                if len(operands) == 2:
                    rd, rs = operands
                    return f"ADDI {map_reg(rd)}, {map_reg(rs)}, 0"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'neg':
                if len(operands) == 2:
                    rd, rs = operands
                    return f"SUB {map_reg(rd)}, r0, {map_reg(rs)}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            # --- Memory ---
            if o in ('sb', 'sh', 'sw'):
                if len(operands) == 2:
                    rs2 = operands[0]
                    mem = operands[1]
                    parsed = parse_mem_operand(mem)
                    if parsed:
                        imm, base = parsed
                        instr = {'sb': 'SB', 'sh': 'SH', 'sw': 'SW'}[o]
                        return f"{instr} {map_reg(rs2)}, {base}, {imm}"
                return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o in ('lbu', 'lb', 'lh', 'lhu', 'lw'):
                if len(operands) == 2:
                    rd = operands[0]
                    mem = operands[1]
                    parsed = parse_mem_operand(mem)
                    if parsed:
                        imm, base = parsed
                        instr_map = {'lb': 'LB', 'lbu': 'LBU', 'lh': 'LH', 'lhu': 'LHU', 'lw': 'LW'}
                        instr = instr_map[o]
                        return f"{instr} {map_reg(rd)}, {base}, {imm}"
                return f"// UNMAPPED: {op} {' '.join(operands)}"
            # --- Branches ---
            if o == 'beq':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BEQ {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'bne':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BNE {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'blt':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BLT {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'bge':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BGE {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'bltu':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BLTU {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'bgeu':
                if len(operands) == 3:
                    rs1, rs2, label = operands
                    return f"BGEU {map_reg(rs1)}, {map_reg(rs2)}, {label}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            # --- Jumps/Calls ---
            if o == 'jal':
                if len(operands) == 1:
                    return f"CALL {operands[0]}"
                elif len(operands) == 2:
                    rd, label = operands
                    if rd.lower() in ('ra', 'x1', 'r1'):
                        return f"CALL {label}"
                    return f"CALL {label} // saved into {map_reg(rd)}"
                else:
                    return f"// UNMAPPED: {op} {' '.join(operands)}"
            if o == 'jalr':
                if operands and operands[0].lower() in ('ra', 'x1', 'r1'):
                    return "RET"
                elif operands:
                    return f"JALR {', '.join(map_reg(op) for op in operands)}"
                else:
                    return f"JALR"
            if o == 'ret':
                return "RET"
            # --- Pseudoinstructions ---
            if o == 'nop':
                return "NOP"
            # --- Fallback ---
            return f"// UNMAPPED: {op} {' '.join(operands)}"

        def parse_instruction_lark(line):
            grammar = """
            start: opcode operands
            opcode: /[a-zA-Z._]+/
            operands: operand ("," operand)*
            operand: /[^,\s#]+/
            %import common.WS
            %ignore WS
            """
            parser = Lark(grammar, parser='lalr')
            try:
                tree = parser.parse(line)
                op = str(tree.children[0])
                operands = [str(child) for child in tree.children[1].children]
                return op, operands
            except Exception:
                return None, []

        def transpile_text(text: str) -> str:
            out_lines = []
            for line in text.splitlines():
                s = line.strip()
                if not s:
                    out_lines.append('')
                    continue
                if s.startswith('.'):
                    out_lines.append('// ' + line)
                    continue
                if s.startswith('//') or s.startswith('#'):
                    out_lines.append(line)
                    continue
                # Label: ends with colon
                if re.match(r'^[A-Za-z_.][A-Za-z0-9_.]*:', s):
                    out_lines.append(line)
                    continue
                # Try to parse as instruction
                op, operands = parse_instruction_lark(s)
                if op:
                    out_lines.append(translate_riscv_to_ros(op, operands))
                else:
                    out_lines.append('// UNMAPPED: ' + line)
            return '\n'.join(out_lines) + '\n'