#pragma endian little
#pragma magic [52 4F 53 50] @ 0x00 // "ROSP" magic number for binary identification
#include <std/string.pat>

// Instruction decoding helpers
fn format_opcode_name(u32 opcode, u32 sub_op) {
    if (opcode == 0x0) { // R-type
        if (sub_op == 0x0) return "ADD";
        if (sub_op == 0x1) return "SUB";
        if (sub_op == 0x2) return "AND";
        if (sub_op == 0x3) return "OR";
        if (sub_op == 0x4) return "XOR";
        if (sub_op == 0x5) return "MUL";
        if (sub_op == 0x6) return "MULH";
        if (sub_op == 0x7) return "NEG";
        if (sub_op == 0x8) return "NOT";
        if (sub_op == 0x9) return "SHL";
        if (sub_op == 0xA) return "SHR";
        if (sub_op == 0xB) return "SAR";
        if (sub_op == 0xC) return "DIV";
        if (sub_op == 0xD) return "DIVU";
        if (sub_op == 0xE) return "REM";
        if (sub_op == 0xF) return "REMU";
    } else if (opcode == 0x1) { // I-type arithmetic
        if (sub_op == 0x0) return "ADDI";
        if (sub_op == 0x1) return "ANDI";
        if (sub_op == 0x2) return "ORI";
        if (sub_op == 0x3) return "XORI";
        if (sub_op == 0x4) return "SHLI";
        if (sub_op == 0x5) return "SHRI";
        if (sub_op == 0x6) return "SARI";
    } else if (opcode == 0x2) { // Load/Store
        if (sub_op == 0x0) return "LB";
        if (sub_op == 0x1) return "LBU";
        if (sub_op == 0x2) return "LH";
        if (sub_op == 0x3) return "LHU";
        if (sub_op == 0x4) return "LW";
        if (sub_op == 0x5) return "SB";
        if (sub_op == 0x6) return "SH";
        if (sub_op == 0x7) return "SW";
    } else if (opcode == 0x3) { // Branch
        if (sub_op == 0x0) return "BEQ";
        if (sub_op == 0x1) return "BNE";
        if (sub_op == 0x2) return "BLT";
        if (sub_op == 0x3) return "BGE";
        if (sub_op == 0x4) return "BLTU";
        if (sub_op == 0x5) return "BGEU";
    } else if (opcode == 0x4) { // Jump
        if (sub_op == 0x0) return "JAL";
        if (sub_op == 0x1) return "JALR";
    } else if (opcode == 0x5) { // Special
        if (sub_op == 0x0) return "ECALL";
        if (sub_op == 0x1) return "BREAK";
    } else if (opcode == 0xF) {
        return "NOP";
    }
    return "UNKNOWN";
};

// Instruction structure
struct Instruction {
    u32 raw_instruction;
    
    // Extract fields
    u8 opcode = (raw_instruction >> 28) & 0x0F;
    u8 sub_op = (raw_instruction >> 24) & 0x0F;
    u8 rd = (raw_instruction >> 20) & 0x0F;
    u8 rs1 = (raw_instruction >> 16) & 0x0F;
    u8 rs2 = (raw_instruction >> 12) & 0x0F;
    s16 imm = raw_instruction & 0xFFFF;
    
    // Decoded instruction name
    str mnemonic = format_opcode_name(opcode, sub_op);
} [[format("format_instruction")]];

fn format_instruction(Instruction instr) {
    str result = instr.mnemonic;
    
    if (instr.opcode == 0x0) { // R-type: ADD rd, rs1, rs2
        result = result + " r" + std::string::to_string(instr.rd) + 
                 ", r" + std::string::to_string(instr.rs1) + 
                 ", r" + std::string::to_string(instr.rs2);
    } else if (instr.opcode == 0x1) { // I-type arithmetic: ADDI rd, rs1, imm
        result = result + " r" + std::string::to_string(instr.rd) + 
                 ", r" + std::string::to_string(instr.rs1) + 
                 ", " + std::string::to_string(instr.imm);
    } else if (instr.opcode == 0x2) { // Load/Store: LW rd, imm(rs)
        result = result + " r" + std::string::to_string(instr.rd) + 
                 ", " + std::string::to_string(instr.imm) + 
                 "(r" + std::string::to_string(instr.rs1) + ")";
    } else if (instr.opcode == 0x3) { // Branch: BEQ rs1, rs2, imm
        result = result + " r" + std::string::to_string(instr.rs1) + 
                 ", r" + std::string::to_string(instr.rs2) + 
                 ", " + std::string::to_string(instr.imm);
    } else if (instr.opcode == 0x4) { // Jump: JAL rd, rs, imm
        result = result + " r" + std::string::to_string(instr.rd) + 
                 ", r" + std::string::to_string(instr.rs1) + 
                 ", " + std::string::to_string(instr.imm);
    }
    
    return result;
};

struct Segment {
    u32 address;
    u32 size;
    Instruction instructions[size / 4];
};
    
struct Binary{
    char magic[4]; // "ROSP"
    u32 version;
    u32 segment_count;

    Segment segments[segment_count];
};



Binary b @ 0;