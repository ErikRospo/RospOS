#include "RospOSVM.h"
#include "Memory.h"
#include "TTY.h"
#include "InstructionDecoder.h"
#include "Display.h"
#include "Shutdown.h"

#include <fstream>
#include <iostream>
#include <iomanip>
#include <stdexcept>

RospOSVM::RospOSVM(bool debugMode) : memory(1ULL << 32) // Initialize 4GB memory
{
    this->debugMode = debugMode;
    pc = memory.readWord(0xFFFFFFFC); // Set PC to reset vector
    regFile.sp().set(0x0FFFFFFF);     // Top of RAM
    regFile[0].setReadOnly(true);     // R0 is always zero

    // Setup TTY MMIO range
    memory.addSpecialRange((char *)"TTY ", 0x10000000, 0x100001FF, SpecialMemoryRange::Type::MMIO, true, true,
                           TTYReadHandler, TTYWriteHandler);
    // Setup Display MMIO range
    // Note: VMDisplay instance is created in MainWindow for Qt GUI, or separately for CLI
    memory.addSpecialRange((char *)"DISP", 0x20000000, 0x2000FFFF, SpecialMemoryRange::Type::MMIO, true, true,
                           VMDisplay::displayReadHandler, VMDisplay::displayWriteHandler);
}

void RospOSVM::loadBinaryAtAddress(const std::vector<char> &binary, uint32_t address)
{
    memory.loadBinary(binary, address);
}

void RospOSVM::step()
{
    uint32_t instruction = memory.readWord(pc);
    if (debugMode)
    {
        std::cerr << "PC: " << std::hex << pc << std::dec << " ";
        std::cerr << "I: " << decodeInstruction(instruction, regFile) << "\n";
        std::cerr << "RI: " << std::hex << std::setw(8) << std::setfill('0') << instruction << std::dec << "\n";
        std::cerr << "Registers: " << getRegisterState() << std::endl;
    }
    executeInstruction(instruction);
    if (debugMode)
    {
        std::cerr << "After Execution:\n";
        std::cerr << "PC: " << std::hex << pc << std::dec << "\n";
        std::cerr << "Registers: " << getRegisterState() << "\n";
        std::cerr << "----------------------------------------\n"
                  << std::endl;
    }
}

std::string RospOSVM::getRegisterState() const
{
    std::ostringstream state;
    for (int i = 0; i < 16; ++i)
    {
        state << "R" << i << ": " << std::hex << std::setw(8) << std::setfill('0') << regFile[i].get() << " ";
    }
    return state.str();
}

void RospOSVM::executeInstruction(uint32_t instruction)
{
    uint32_t opcode = (instruction >> 28) & 0x0F;
    bool pcModified = false;
    switch (opcode)
    {
    case 0x0: // R-type arithmetic
        rTypeInstruction(instruction);
        break;
    case 0x1: // I-type arithmetic/logical (immediate)
        iArithTypeInstruction(instruction);
        break;
    case 0x2: // Load/Store (I-type)
        iTypeLSInstruction(instruction);
        break;
    case 0x3: // Branch (B-type)
        pcModified = bTypeInstruction(instruction);
        break;
    case 0x4: // Jump (J-type)
        jTypeInstruction(instruction);
        pcModified = true;
        break;
    case 0x5: // Special (S-type)
        sTypeInstruction(instruction);
        break;
    case 0xF: // NOP
        // Do nothing
        break;
    default:
        std::cerr << "Unknown opcode: " << opcode << std::endl;
        break;
    }
    if (!pcModified)
    {
        pc += 4; // Move to next instruction
    }
}
void RospOSVM::rTypeInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-12 | 11-0          |
    |-------|-------|-------|-------|-------|---------------|
    | opcode| sub-op|   rd  |  rs1  |  rs2  |   unused      | */
    uint32_t sub_op = (instruction >> 24) & 0x0F;
    uint32_t rd = (instruction >> 20) & 0x0F;
    uint32_t rs1 = (instruction >> 16) & 0x0F;
    uint32_t rs2 = (instruction >> 12) & 0x0F;
    switch (sub_op)
    {
    case 0x0: // ADD
        regFile[rd].set(regFile[rs1].get() + regFile[rs2].get());
        break;
    case 0x1: // SUB
        regFile[rd].set(regFile[rs1].get() - regFile[rs2].get());
        break;
    case 0x2: // AND
        regFile[rd].set(regFile[rs1].get() & regFile[rs2].get());
        break;
    case 0x3: // OR
        regFile[rd].set(regFile[rs1].get() | regFile[rs2].get());
        break;
    case 0x4: // XOR
        regFile[rd].set(regFile[rs1].get() ^ regFile[rs2].get());
        break;
    case 0x5: // MUL (lower 32 bits)
        regFile[rd].set(regFile[rs1].get() * regFile[rs2].get());
        break;
    case 0x6: // MULH
    {
        uint64_t result = static_cast<uint64_t>(regFile[rs1].get()) * static_cast<uint64_t>(regFile[rs2].get());
        regFile[rd].set(static_cast<uint32_t>(result >> 32));
    }
    break;
    case 0x7: // NEG
        regFile[rd].set(-regFile[rs1].get());
        break;
    case 0x8: // NOT
        regFile[rd].set(~regFile[rs1].get());
        break;
    case 0x9: // SHL
        regFile[rd].set(regFile[rs1].get() << (regFile[rs2].get() & 0x1F));
        break;
    case 0xA: // SHR
        regFile[rd].set(regFile[rs1].get() >> (regFile[rs2].get() & 0x1F));
        break;
    case 0xB: // SAR
        regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) >> (regFile[rs2].get() & 0x1F));
        break;
    case 0xC: // DIV
        if (regFile[rs2].get() == 0)
        {
            std::cerr << "Division by zero error in DIV instruction." << std::endl;
            regFile[rd].set(0xFFFFFFFF);
        }
        else
        {
            regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) / static_cast<int32_t>(regFile[rs2].get()));
        }
        break;
    case 0xD: // DIVU
        if (regFile[rs2].get() == 0)
        {
            std::cerr << "Division by zero error in DIVU instruction." << std::endl;
            regFile[rd].set(0xFFFFFFFF);
        }
        else
        {
            regFile[rd].set(regFile[rs1].get() / regFile[rs2].get());
        }
        break;
    case 0xE: // REM
        if (regFile[rs2].get() == 0)
        {
            std::cerr << "Division by zero error in REM instruction." << std::endl;
            regFile[rd].set(0xFFFFFFFF);
        }
        else
        {
            regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) % static_cast<int32_t>(regFile[rs2].get()));
        }
        break;
    case 0xF: // REMU
        if (regFile[rs2].get() == 0)
        {
            std::cerr << "Division by zero error in REMU instruction." << std::endl;
            regFile[rd].set(0xFFFFFFFF);
        }
        else
        {
            regFile[rd].set(regFile[rs1].get() % regFile[rs2].get());
        }
        break;
    default:
        std::cerr << "Unknown R-type sub-opcode: " << sub_op << std::endl;
        break;
    }
}
void RospOSVM::iArithTypeInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0           |
    |-------|-------|-------|-------|----------------|
    | opcode| sub-op|   rd  |  rs1  |   immediate    | */
    uint32_t sub_op = (instruction >> 24) & 0x0F;
    uint32_t rd = (instruction >> 20) & 0x0F;
    uint32_t rs1 = (instruction >> 16) & 0x0F;
    int32_t r_imm = static_cast<int32_t>(instruction & 0xFFFF);
    int32_t zero_ext_imm = static_cast<uint16_t>(instruction & 0xFFFF);
    int32_t sign_ext_imm = (r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;

    switch (sub_op)
    {
    case 0x0: // ADDI
        regFile[rd].set(regFile[rs1].get() + sign_ext_imm);
        break;
    case 0x1: // ANDI
        regFile[rd].set(regFile[rs1].get() & zero_ext_imm);
        break;
    case 0x2: // ORI
        regFile[rd].set(regFile[rs1].get() | zero_ext_imm);
        break;
    case 0x3: // XORI
        regFile[rd].set(regFile[rs1].get() ^ zero_ext_imm);
        break;
    case 0x4: // SHLI
        regFile[rd].set(regFile[rs1].get() << (zero_ext_imm & 0x1F));
        break;
    case 0x5: // SHRI
        regFile[rd].set(regFile[rs1].get() >> (zero_ext_imm & 0x1F));
        break;
    case 0x6: // SARI
        regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) >> (zero_ext_imm & 0x1F));
        break;
    default:
        std::cerr << "Unknown I-type sub-opcode: " << sub_op << std::endl;
        break;
    }
}
void RospOSVM::iTypeLSInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
    */
    uint32_t sub_op = (instruction >> 24) & 0x0F;
    uint32_t rd = (instruction >> 20) & 0x0F;
    uint32_t rs = (instruction >> 16) & 0x0F;
    int32_t r_imm = static_cast<int32_t>(instruction & 0xFFFF);
    int32_t sign_ext_imm = (r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
    uint32_t addr = regFile[rs].get() + sign_ext_imm;
    switch (sub_op)
    {
    case 0x0: // LB
        regFile[rd].set(static_cast<int8_t>(memory.readByte(addr)));
        break;
    case 0x1: // LBU
        regFile[rd].set(static_cast<uint8_t>(memory.readByte(addr)));
        break;
    case 0x2: // LH
        regFile[rd].set(static_cast<int16_t>(memory.readHalf(addr)));
        break;
    case 0x3: // LHU
        regFile[rd].set(static_cast<uint16_t>(memory.readHalf(addr)));
        break;
    case 0x4: // LW
        regFile[rd].set(static_cast<uint32_t>(memory.readWord(addr)));
        break;
    case 0x5: // SB
        memory.writeByte(addr, static_cast<uint8_t>(regFile[rd].get() & 0xFF));
        break;
    case 0x6: // SH
        memory.writeHalf(addr, static_cast<uint16_t>(regFile[rd].get() & 0xFFFF));
        break;
    case 0x7: // SW
        memory.writeWord(addr, static_cast<uint32_t>(regFile[rd].get()));
        break;
    default:
        std::cerr << "Unknown Load/Store sub-opcode: " << sub_op << std::endl;
        break;
    }
}
bool RospOSVM::bTypeInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|  rs1  |  rs2  | immediate (16-bit offset)|
    */
    uint32_t sub_op = (instruction >> 24) & 0x0F;
    uint32_t rs1 = (instruction >> 20) & 0x0F;
    uint32_t rs2 = (instruction >> 16) & 0x0F;
    int32_t r_imm = static_cast<int32_t>(instruction & 0xFFFF);
    int32_t sign_ext_imm = (r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;

    sign_ext_imm <<= 2; // Branch addresses are word-aligned

    bool takeBranch = false;
    switch (sub_op)
    {
    case 0x0: // BEQ
        takeBranch = (regFile[rs1].get() == regFile[rs2].get());
        break;
    case 0x1: // BNE
        takeBranch = (regFile[rs1].get() != regFile[rs2].get());
        break;
    case 0x2: // BLT
        takeBranch = (static_cast<int32_t>(regFile[rs1].get()) < static_cast<int32_t>(regFile[rs2].get()));
        break;
    case 0x3: // BGE
        takeBranch = (static_cast<int32_t>(regFile[rs1].get()) >= static_cast<int32_t>(regFile[rs2].get()));
        break;
    case 0x4: // BLTU
        takeBranch = (regFile[rs1].get() < regFile[rs2].get());
        break;
    case 0x5: // BGEU
        takeBranch = (regFile[rs1].get() >= regFile[rs2].get());
        break;
    default:
        std::cerr << "Unknown B-type sub-opcode: " << sub_op << std::endl;
        break;
    }
    if (takeBranch)
    {
        pc += sign_ext_imm;
    }
    return takeBranch;
}
void RospOSVM::jTypeInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
    */
    int32_t sub_op = (instruction >> 24) & 0x0F;
    int32_t rd = (instruction >> 20) & 0x0F;
    int32_t rs = (instruction >> 16) & 0x0F;
    int32_t r_imm = static_cast<int32_t>(instruction & 0xFFFF);
    int32_t sign_ext_imm = (r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
    switch (sub_op)
    {
    case 0x0: // JAL
        regFile[rd].set(pc + 4);
        pc += sign_ext_imm << 2;
        break;
    case 0x1: // JALR
    {
        uint32_t temp = pc + 4;
        pc = (regFile[rs].get() + (sign_ext_imm << 2)) & ~1;
        regFile[rd].set(temp);
    }
    break;
    }
}
void RospOSVM::sTypeInstruction(uint32_t instruction)
{
    /*
    | 31-28 | 27-24 | 23-0                             |
    |-------|-------|----------------------------------|
    | opcode| sub-op|   unused                         |
    */
    uint32_t sub_op = (instruction >> 24) & 0x0F;
    switch (sub_op)
    {
    case 0x0: // ECALL
        std::cerr << "ECALL invoked." << std::endl;
        break;
    case 0x1: // BREAK
        std::cerr << "BREAK invoked. Halting execution." << std::endl;
        // Dump memory and register state for debugging
        std::cerr << "Final PC: " << std::hex << pc << std::dec << std::endl;
        std::cerr << "Final Registers: " << getRegisterState() << std::endl;
        dumpMemoryToFile(memory);
        requestShutdown();
        break;
    default:
        std::cerr << "Unknown S-type sub-opcode: " << sub_op << std::endl;
        break;
    }
}

void dumpMemoryToFile(const Memory &memory)
{
    std::ofstream file("memory_dump.bin", std::ios::binary);
    if (!file.is_open())
    {
        std::cerr << "Failed to open memory_dump.bin for writing." << std::endl;
        return;
    }

    for (uint32_t addr = 0; addr < (1ULL << 16); addr += 4)
    {
        uint32_t word = memory.readWord(addr);
        file.write(reinterpret_cast<const char *>(&word), sizeof(word));
    } 
    if (!file.good())
    {
        std::cerr << "Error writing to memory_dump.bin." << std::endl;
    }

    file.close();
}