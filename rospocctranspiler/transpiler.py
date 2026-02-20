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
import re
import sys
from pathlib import Path

# Minimal register mapping respecting the target ISA constraints:
# - r0 is zero
# - r1..r12 are the general-purpose registers you should use
# - r13 is a temporary register: avoid mapping into it
# - r14 is the link/return register (LR)
# - r15 is the stack pointer (SP)
REG_MAP = {
    'zero': 'r0',
    # map a small useful subset into r1..r12
    'gp': 'r1',
    'tp': 'r2',
    't0': 'r3', 't1': 'r4', 't2': 'r5',
    's0': 'r6', 's1': 'r7',
    'a0': 'r8', 'a1': 'r9', 'a2': 'r10', 'a3': 'r11', 'a4': 'r12',
    # special-purpose registers
    'ra': 'r14',  # return / link register
    'sp': 'r15',
}

# Provide numeric aliases only up to r15 (we avoid mapping into r13)
for i in range(16):
    REG_MAP[f'x{i}'] = f'r{i}'
    REG_MAP[f'r{i}'] = f'r{i}'

def map_reg(token: str) -> str:
    t = token.strip()
    # strip any register punctuation
    if t in REG_MAP:
        return REG_MAP[t]
    # try to strip possible trailing commas
    t2 = t.rstrip(',')
    return REG_MAP.get(t2, t2)

def parse_mem_operand(op: str):
    # formats like: 0(a0) or -8(s2)
    m = re.match(r"([\-0-9xXa-fA-F]+)\(([^)]+)\)", op.strip())
    if not m:
        return None
    imm, base = m.groups()
    return imm, map_reg(base)

def translate_instruction(op: str, operands: list[str]) -> str:
    o = op.lower()
    # simple RISC-V -> .ros mnemonic mappings
    if o == 'addi':
        rd, rs1, imm = operands
        return f"ADDI {map_reg(rd)}, {map_reg(rs1)}, {imm}"
    if o == 'add':
        rd, rs1, rs2 = operands
        return f"ADD {map_reg(rd)}, {map_reg(rs1)}, {map_reg(rs2)}"
    if o == 'sub':
        rd, rs1, rs2 = operands
        return f"SUB {map_reg(rd)}, {map_reg(rs1)}, {map_reg(rs2)}"
    if o == 'li':
        rd, imm = operands
        return f"LLI {map_reg(rd)}, {imm}"
    if o == 'lui':
        rd, imm = operands
        return f"LLI {map_reg(rd)}, {imm}"
    if o == 'mv':
        rd, rs = operands
        return f"ADDI {map_reg(rd)}, {map_reg(rs)}, 0"
    if o == 'neg':
        rd, rs = operands
        return f"SUB {map_reg(rd)}, r0, {map_reg(rs)}"
    if o in ('sb', 'sh', 'sw'):
        # sb rs2, offset(rs1) -> SB rs2, rs1, offset
        rs2 = operands[0]
        mem = operands[1]
        parsed = parse_mem_operand(mem)
        if parsed:
            imm, base = parsed
            instr = {'sb': 'SB', 'sh': 'SH', 'sw': 'SW'}[o]
            return f"{instr} {map_reg(rs2)}, {base}, {imm}"
    if o in ('lbu', 'lb', 'lh', 'lhu', 'lw'):
        rd = operands[0]
        mem = operands[1]
        parsed = parse_mem_operand(mem)
        if parsed:
            imm, base = parsed
            instr_map = {'lb': 'LB', 'lbu': 'LBU', 'lh': 'LH', 'lhu': 'LHU', 'lw': 'LW'}
            instr = instr_map[o]
            return f"{instr} {map_reg(rd)}, {base}, {imm}"
    if o == 'beq':
        rs1, rs2, label = operands
        return f"BEQ {map_reg(rs1)}, {map_reg(rs2)}, {label}"
    if o == 'bne':
        rs1, rs2, label = operands
        return f"BNE {map_reg(rs1)}, {map_reg(rs2)}, {label}"
    if o == 'beqz':
        rs, label = operands
        return f"BEQ {map_reg(rs)}, r0, {label}"
    if o == 'bnez':
        rs, label = operands
        return f"BNE {map_reg(rs)}, r0, {label}"
    if o == 'jal':
        # jal label  OR jal rd, label
        if len(operands) == 1:
            return f"CALL {operands[0]}"
        else:
            rd, label = operands
            if rd.lower() in ('ra', 'x1', 'r1'):
                return f"CALL {label}"
            return f"CALL {label} // saved into {map_reg(rd)}"
    if o == 'jalr':
        # often ret
        return "JALR " + ', '.join(map_reg(op) for op in operands)
    if o == 'ret':
        return "RET"
    if o == 'sb':
        return f"SB {', '.join(operands)}"

    # fallback: unknown instruction -> emit as comment so user can enhance
    return f"// UNMAPPED: {op} {' '.join(operands)}"

def tokenize_operands(op_str: str) -> list[str]:
    # split by commas but keep parentheses groups intact
    parts = []
    cur = ''
    depth = 0
    for ch in op_str:
        if ch == ',' and depth == 0:
            parts.append(cur.strip())
            cur = ''
            continue
        cur += ch
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
    if cur.strip():
        parts.append(cur.strip())
    return parts

def process_line(line: str) -> str | None:
    orig = line.rstrip('\n')
    # strip leading/trailing whitespace
    s = orig.strip()
    if not s:
        return ''
    # If the line is a commented dot-label (e.g. "// .LBB0_2:") or
    # an annotated dot-label (e.g. "// .LBB0_2:  # =>This ..."),
    # pass the label through as `.LBB0_2:`.
    m_commented_dot_label = re.match(r'^(?:\/\/|#)\s*(\.[A-Za-z0-9_.]+)\s*:', s)
    if m_commented_dot_label:
        return f"{m_commented_dot_label.group(1)}:"

    # preserve labels (including dot-prefixed labels)
    if s.endswith(':'):
        return s

    # pass through assembler directives as comments or minimal translation
    if s.startswith('.'):  # directive
        # keep major directives as comments to avoid breaking .ros files
        return f"// {s}"
    # remove inline comments starting with # or // or /* style
    s = re.split(r"(#|//)", s)[0].strip()
    # tokenise instruction
    m = re.match(r"([a-zA-Z._]+)\s*(.*)", s)
    if not m:
        return f"// {orig}"
    op = m.group(1)
    rest = m.group(2).strip()
    operands = []
    if rest:
        operands = tokenize_operands(rest)
    try:
        translated = translate_instruction(op, operands)
        return translated
    except Exception:
        return f"// ERROR translating: {orig}"

def transpile_text(text: str) -> str:
    out_lines: list[str] = []
    lines = text.splitlines()
    i = 0
    # look for patterns like:
    #   .type <name>,@function
    #   <name>:
    # and replace them with:
    #   .FUNC <name>:
    while i < len(lines):
        line = lines[i]
        s = line.strip()
        # match .type lines, allowing optional leading comment markers
        m = re.match(r"(?:\/\/\s*)?\.type\s+([A-Za-z_][A-Za-z0-9_.]*)\s*,\s*@function", s)
        if m:
            name = m.group(1)
            # find next non-empty line
            j = i + 1
            while j < len(lines) and lines[j].strip() == '':
                j += 1
            if j < len(lines):
                next_line = lines[j]
                # if the name followed by a colon appears anywhere in the next line
                # (covers "print_string:", "UNMAPPED: print_string :", "ERROR translating: print_string :", etc.)
                if re.search(rf"\b{re.escape(name)}\s*:", next_line):
                    out_lines.append(f".FUNC {name}:")
                    i = j + 1
                    continue
            # fallback: emit the directive as a comment
            out_lines.append(f"// {s}")
            i += 1
            continue

        res = process_line(line)
        if res is None:
            i += 1
            continue
        out_lines.append(res)
        i += 1

    return '\n'.join(out_lines) + '\n'

def main(argv=None):
    p = argparse.ArgumentParser(description='RISC-V to .ros transpiler (best-effort)')
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
