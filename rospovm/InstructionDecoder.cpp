#include "InstructionDecoder.h"
#include "Register.h"
#include "Memory.h"
#include <string>
#include <cstdint>

std::string formatRegister(uint32_t reg, RegisterFile &regFile) {
    return "r" + std::to_string(reg) + ": " + std::to_string(regFile[reg].get());
}

std::string formatRegisterValues(uint32_t rd, uint32_t rs1, uint32_t rs2, RegisterFile &regFile) {
    return formatRegister(rd, regFile) + ", " + formatRegister(rs1, regFile) + ", " + formatRegister(rs2, regFile);
}

std::string decodeInstruction(uint32_t instruction, RegisterFile &regFile) {
    if (instruction == 0) {
        return "NOP";
    };
    uint32_t opcode = (instruction >> 28) & 0x0F;
    std::string oss;
    switch (opcode) {
        case 0x0: { // R-type
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs1 = (instruction >> 16) & 0x0F;
            uint32_t rs2 = (instruction >> 12) & 0x0F;
            switch (sub_op) {
                case 0x0: oss += "ADD "; break;
                case 0x1: oss += "SUB "; break;
                case 0x2: oss += "AND "; break;
                case 0x3: oss += "OR  "; break;
                case 0x4: oss += "XOR "; break;
                case 0x5: oss += "MUL "; break;
                case 0x6: oss += "MULH "; break;
                case 0x7: oss += "NEG "; break;
                case 0x8: oss += "NOT "; break;
                case 0x9: oss += "SHL "; break;
                case 0xA: oss += "SHR "; break;
                case 0xB: oss += "SAR "; break;
                case 0xC: oss += "DIV "; break;
                case 0xD: oss += "DIVU "; break;
                case 0xE: oss += "REM "; break;
                case 0xF: oss += "REMU "; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += formatRegisterValues(rd, rs1, rs2, regFile);
            break;
        }
        case 0x1: { // I-type arithmetic
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs1 = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            switch (sub_op) {
                case 0x0: oss += "ADDI "; break;
                case 0x1: oss += "ANDI "; break;
                case 0x2: oss += "ORI "; break;
                case 0x3: oss += "XORI "; break;
                case 0x4: oss += "SHLI "; break;
                case 0x5: oss += "SHRI "; break;
                case 0x6: oss += "SARI "; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " " + formatRegister(rd, regFile) + ", " + formatRegister(rs1, regFile) + ", " + std::to_string(imm);
            break;
        }
        case 0x2: { // Load/Store
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            switch (sub_op) {
                case 0x0: oss += "LB "; break;
                case 0x1: oss += "LBU "; break;
                case 0x2: oss += "LH "; break;
                case 0x3: oss += "LHU "; break;
                case 0x4: oss += "LW "; break;
                case 0x5: oss += "SB "; break;
                case 0x6: oss += "SH "; break;
                case 0x7: oss += "SW "; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " " + formatRegister(rd, regFile) + ", " + std::to_string(imm) + ", " + formatRegister(rs, regFile);
            break;
        }
        case 0x3: { // Branch
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rs1 = (instruction >> 20) & 0x0F;
            uint32_t rs2 = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            switch (sub_op) {
                case 0x0: oss += "BEQ "; break;
                case 0x1: oss += "BNE "; break;
                case 0x2: oss += "BLT "; break;
                case 0x3: oss += "BGE "; break;
                case 0x4: oss += "BLTU "; break;
                case 0x5: oss += "BGEU "; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " " + formatRegister(rs1, regFile) + ", " + formatRegister(rs2, regFile) + ", " + std::to_string(imm);
            break;
        }
        case 0x4: { // Jump
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            switch (sub_op) {
                case 0x0: oss += "JAL "; break;
                case 0x1: oss += "JALR "; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " " + formatRegister(rd, regFile) + ", " + formatRegister(rs, regFile) + ", " + std::to_string(imm);
            break;
        }
        case 0x5: { // Special
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            switch (sub_op) {
                case 0x0: oss += "ECALL "; break;
                case 0x1: oss += "BREAK "; break;
                default: oss += "UNKNOWN"; break;
            }
            break;
        }
        case 0xF: // NOP
            oss += "NOP";
            break;
        default:
            oss += "UNKNOWN OPCODE";
            break;
    }
    return oss;
}