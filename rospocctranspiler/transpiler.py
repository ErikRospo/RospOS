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
        super().__init__()
        self.active_func = None
        self.used_regs = set()
        self.stack_ops = []

    def label(self, items):
        label = str(items[0])
        if label.endswith(':') and label.startswith('.FUNC'):
            self.active_func = label
            self.used_regs.clear()
            self.stack_ops.clear()
        return label

    def directive(self, items):
        d = str(items[0])
        if d.startswith('.type'):
            m = re.match(r"\.type\s+([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*@function", d)
            if m:
                self.active_func = m.group(1)
                self.used_regs.clear()
                self.stack_ops.clear()
                return f".FUNC {m.group(1)}:"
        return f"// {d}"

    def instruction(self, items):
        op = str(items[0])
        operands = items[1] if len(items) > 1 else []
        regs = [map_reg(o) for o in operands if re.match(r'^[a-zA-Z][a-zA-Z0-9]*$', o)]
        # Only push/pop for r13, r14, r15 or unmapped
        push_lines = []
        pop_lines = []
        for r in regs:
            if r.startswith('r'):
                idx = int(r[1:])
                if idx > 12:
                    if r not in self.used_regs:
                        push_lines.append(f"PUSH {r}")
                        self.used_regs.add(r)
                    self.stack_ops.append(r)
        ros = translate_riscv_to_ros(op, operands)
        # If instruction is RET, pop all pushed regs
        if op.lower() == 'ret' and self.stack_ops:
            for r in reversed(self.stack_ops):
                pop_lines.append(f"POP {r}")
            self.stack_ops.clear()
            self.used_regs.clear()
        return '\n'.join(push_lines + [ros] + pop_lines)

    def operands(self, items):
        return items
    def operand(self, items):
        return str(items[0])
    def COMMENT(self, items):
        return f"// {str(items[0])}"
    def IMM(self, items):
        return str(items[0])
    def REGISTER(self, items):
        return str(items[0])
    def MEM(self, items):
        return str(items[0])
    def LABELREF(self, items):
        return str(items[0])

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

def transpile_text(text: str) -> str:
    grammar_path = Path(__file__).parent / 'riscv.lark'
    grammar = grammar_path.read_text()
    parser = Lark(grammar, parser='lalr', propagate_positions=False)
    transformer = RiscvTransformer()

    out_lines = [
        ".SEG 0xFFFF_FFFC",
        ".DATA 0x00000000",
        ".SEG 0x00000000",
        ""
    ]
    for line in text.splitlines():
        s = line.strip()
        if not s:
            out_lines.append('')
            continue
        if s.startswith('.'):
            out_lines.append('// ' + line)
            continue
        if s.startswith('//'):
            out_lines.append(line)
            continue
        # Replace any line where the first non-whitespace character is '#' with '//' (preserving indentation)
        if line.lstrip().startswith('#'):
            # Remove lines where the first non-whitespace character is '#'
            continue
        if s.endswith(':') or re.match(r'^[A-Za-z_][A-Za-z0-9_.]*:\s*', s):
            # Label line (allow trailing comment)
            label = s.split(':')[0] + ':'
            out_lines.append(label)
            continue
        # Try to parse as instruction
        try:
            tree = parser.parse(line + '\n', start='instruction')
            ros = transformer.transform(tree)
            if isinstance(ros, list):
                out_lines.extend(ros)
            else:
                out_lines.append(ros)
        except Exception:
            out_lines.append('// UNPARSEABLE: ' + line)
    return '\n'.join(out_lines) + '\n'

def main(argv=None):
    p = argparse.ArgumentParser(description='RISC-V to .ros transpiler (Lark-based)')
    p.add_argument('input', help='Input RISC-V assembly file')
    p.add_argument('-o', '--output', help='Output .ros file (defaults to input.ros)')
    args = p.parse_args(argv)

    inp = Path(args.input)
    if not inp.exists():
        print(f"Input file not found: {inp}", file=sys.stderr)
        sys.exit(2)

    txt = inp.read_text()
    out = transpile_text(txt)

    out_path = Path(args.output) if args.output else inp.with_suffix('.ros')
    out_path.write_text(out)
    print(f"Wrote {out_path}")

if __name__ == '__main__':
    main()