#include "RospOSVM.h"

#include <cstdint>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <utility>
#include <QString>

#include "Display.h"
#include "InstructionDecoder.h"
#include "Logger.h"
#include "Memory.h"
#include "Shutdown.h"
#include "TTY.h"

RospOSVM::RospOSVM(bool debugMode) 
        : memory(1ULL << 32),  // Initialize 4GB memory
            debugMode(debugMode)
{
        pc = 0;                           // Set after loading binary reset vector
    regFile.sp().set(0x0FFFFFFF);     // Top of RAM
    regFile[0].setReadOnly(true);     // R0 is always zero

    // Setup TTY MMIO range
    memory.addSpecialRange("TTY ", 0x10000000, 0x100001FF, 
                           SpecialMemoryRange::Type::MMIO, true, true,
                           TTYReadHandler, TTYWriteHandler);
    
    // Setup Display MMIO range
    // Note: VMDisplay instance is created in MainWindow for Qt GUI, or separately for CLI
    memory.addSpecialRange("DISP", 0x20000000, 0x2000FFFF, 
                           SpecialMemoryRange::Type::MMIO, true, true,
                           VMDisplay::displayReadHandler, VMDisplay::displayWriteHandler);
}

void RospOSVM::clearLastMemoryAccess()
{
    hasLastMemoryAccess = false;
    lastMemoryAccess = MemoryAccess{};
}

void RospOSVM::recordMemoryAccess(uint32_t address, uint8_t size, bool isWrite)
{
    if (size == 0) {
        return;
    }

    lastMemoryAccess.address = address;
    lastMemoryAccess.size = size;
    lastMemoryAccess.isWrite = isWrite;
    hasLastMemoryAccess = true;
}

void RospOSVM::beginStateCapture()
{
    currentSnapshot = std::make_unique<VMStateSnapshot>();
    currentSnapshot->pc = pc;
    for (int i = 0; i < 16; ++i) {
        currentSnapshot->registers[static_cast<size_t>(i)] = regFile[i].get();
    }
}

void RospOSVM::commitStateCapture()
{
    if (!currentSnapshot) {
        return;
    }

    stateHistory.push_back(std::move(*currentSnapshot));
    currentSnapshot.reset();

    while (stateHistory.size() > kMaxStateHistory) {
        stateHistory.pop_front();
    }
}

void RospOSVM::clearStateHistory()
{
    stateHistory.clear();
    currentSnapshot.reset();
}

void RospOSVM::recordMemoryDeltaForByte(uint32_t address)
{
    if (!currentSnapshot || applyingHistory) {
        return;
    }

    // MMIO/special ranges may have side effects or block on reads (e.g. TTY).
    // Do not include them in reversible memory snapshots.
    if (memory.isSpecialAddress(address)) {
        return;
    }

    for (const MemoryByteDelta &delta : currentSnapshot->memoryDeltas) {
        if (delta.address == address) {
            return;
        }
    }

    uint8_t previousValue = 0;
    try {
        previousValue = memory.readByte(address);
    } catch (const std::exception &) {
        // Non-readable regions cannot be reliably restored.
        return;
    }

    currentSnapshot->memoryDeltas.push_back({address, previousValue});
}

void RospOSVM::writeMemoryTrackedByte(uint32_t address, uint8_t value)
{
    recordMemoryDeltaForByte(address);
    memory.writeByte(address, value);
}

void RospOSVM::writeMemoryTrackedHalf(uint32_t address, uint16_t value)
{
    writeMemoryTrackedByte(address, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeMemoryTrackedByte(address + 1, static_cast<uint8_t>(value & 0xFF));
}

void RospOSVM::writeMemoryTrackedWord(uint32_t address, uint32_t value)
{
    writeMemoryTrackedByte(address, static_cast<uint8_t>((value >> 24) & 0xFF));
    writeMemoryTrackedByte(address + 1, static_cast<uint8_t>((value >> 16) & 0xFF));
    writeMemoryTrackedByte(address + 2, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeMemoryTrackedByte(address + 3, static_cast<uint8_t>(value & 0xFF));
}

void RospOSVM::writeMemory(uint32_t address, uint32_t value)
{
    recordMemoryAccess(address, 4, true);
    writeMemoryTrackedWord(address, value);
}

void RospOSVM::writeMemoryByte(uint32_t address, uint8_t value)
{
    recordMemoryAccess(address, 1, true);
    writeMemoryTrackedByte(address, value);
}

bool RospOSVM::getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const
{
    if (!hasLastMemoryAccess) {
        return false;
    }

    address = lastMemoryAccess.address;
    size = lastMemoryAccess.size;
    isWrite = lastMemoryAccess.isWrite;
    return true;
}

void RospOSVM::loadBinaryAtAddress(const std::vector<char> &binary, uint32_t address)
{
    clearStateHistory();
    clearLastMemoryAccess();
    memory.loadBinary(binary, address);
}

void RospOSVM::loadBinaryFromFile(const std::string& filename)
{
    clearStateHistory();
    clearLastMemoryAccess();

    // Load the binary file using Binary::load_binary
    try {
        loadedBinary = std::make_shared<Binary>();
        *loadedBinary = loadedBinary->load_binary(filename);
        
        // Load all loadable segments into memory
        for (const auto& segment : loadedBinary->segments) {
            memory.loadBinary(
                std::vector<char>(segment.data.begin(), segment.data.end()),
                segment.address
            );
        }

        // Reset PC from reset-vector after all segments are loaded.
        pc = memory.readWord(0xFFFFFFFC);
        
        std::cout << "Loaded binary from " << filename << " with " 
                  << loadedBinary->segments.size() << " loadable segments and "
                  << loadedBinary->debug_map.size() << " debug segments" << std::endl;
    } catch (const std::exception& e) {
        Logger::instance().error(QString("Failed to load binary: %1").arg(e.what()));
        throw;
    }
}

const DebugEntry* RospOSVM::getDebugInfo(uint32_t address) const
{
    if (!loadedBinary) {
        return nullptr;
    }
    return loadedBinary->get_debug_entry(address);
}

std::string RospOSVM::formatSourceLocation(uint32_t address) const
{
    const DebugEntry* entry = getDebugInfo(address);
    if (!entry) {
        return "unknown";
    }
    
    if (!loadedBinary || loadedBinary->debug_map.empty()) {
        return "unknown";
    }
    
    // Find the file path from the debug map
    for (const auto& debug_pair : loadedBinary->debug_map) {
        const auto& debug_info = debug_pair.second;
        auto file_it = debug_info->file_table.find(entry->file_id);
        if (file_it != debug_info->file_table.end()) {
            std::ostringstream oss;
            oss << file_it->second << ":" << entry->line;
            return oss.str();
        }
    }
    
    std::ostringstream oss;
    oss << "<unknown>:" << entry->line;
    return oss.str();
}

std::string RospOSVM::getOriginalInstruction(uint32_t address) const
{
    const DebugEntry* entry = getDebugInfo(address);
    if (!entry) {
        return "";
    }
    return entry->original_text;
}

const RegisterAllocationInfo* RospOSVM::getRegisterAllocation(
    uint32_t address,
    const std::string &regName
) const
{
    if (!loadedBinary) {
        return nullptr;
    }

    for (const auto &debugPair : loadedBinary->debug_map) {
        const std::shared_ptr<DebugInfo> &debugInfo = debugPair.second;
        auto addrIt = debugInfo->register_allocations.find(address);
        if (addrIt == debugInfo->register_allocations.end()) {
            continue;
        }

        for (const auto &alloc : addrIt->second) {
            if (alloc.reg == regName) {
                return &alloc;
            }
        }
    }

    return nullptr;
}

const RegisterAllocationInfo* RospOSVM::getRegisterAllocation(
    uint32_t address,
    int regIndex
) const
{
    if (regIndex < 0 || regIndex > 15) {
        return nullptr;
    }

    std::ostringstream regName;
    regName << "r" << regIndex;
    return getRegisterAllocation(address, regName.str());
}

void RospOSVM::step()
{
    beginStateCapture();
    clearLastMemoryAccess();
    try {
        uint32_t instruction = memory.readWord(pc);
        if (debugMode)
        {
            std::ostringstream oss;
            oss << "PC: " << std::hex << pc << std::dec << " ";
            oss << "I: " << decodeInstruction(instruction, regFile) << "\n";
            oss << "RI: " << std::hex << std::setw(8) << std::setfill('0') << instruction << std::dec << "\n";
            oss << "Registers: " << getRegisterState();
            Logger::instance().debug(QString::fromStdString(oss.str()));
        }
        executeInstruction(instruction);
        commitStateCapture();
        if (debugMode)
        {
            std::ostringstream oss;
            oss << "After Execution:\n";
            oss << "PC: " << std::hex << pc << std::dec << "\n";
            oss << "Registers: " << getRegisterState() << "\n";
            oss << "----------------------------------------";
            Logger::instance().debug(QString::fromStdString(oss.str()));
        }
    } catch (...) {
        currentSnapshot.reset();
        throw;
    }
}

bool RospOSVM::stepBackward()
{
    if (stateHistory.empty()) {
        return false;
    }

    const VMStateSnapshot snapshot = std::move(stateHistory.back());
    stateHistory.pop_back();

    applyingHistory = true;
    for (auto it = snapshot.memoryDeltas.rbegin(); it != snapshot.memoryDeltas.rend(); ++it) {
        memory.writeByte(it->address, it->previousValue);
    }
    applyingHistory = false;

    pc = snapshot.pc;
    for (int i = 1; i < 16; ++i) {
        regFile[i].set(snapshot.registers[static_cast<size_t>(i)]);
    }

    if (debugMode)
    {
        std::ostringstream oss;
        oss << "Step back applied. PC: " << std::hex << pc << std::dec << "\n";
        oss << "Registers: " << getRegisterState();
        Logger::instance().debug(QString::fromStdString(oss.str()));
    }

    clearLastMemoryAccess();

    return true;
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
    
    switch (opcode) {
        case 0x0:  // R-type arithmetic
            rTypeInstruction(instruction);
            break;
        case 0x1:  // I-type arithmetic/logical (immediate)
            iArithTypeInstruction(instruction);
            break;
        case 0x2:  // Load/Store (I-type)
            iTypeLSInstruction(instruction);
            break;
        case 0x3:  // Branch (B-type)
            pcModified = bTypeInstruction(instruction);
            break;
        case 0x4:  // Jump (J-type)
            jTypeInstruction(instruction);
            pcModified = true;
            break;
        case 0x5:  // Special (S-type)
            sTypeInstruction(instruction);
            break;
        case 0xF:  // NOP - no operation
            break;
        default:
            Logger::instance().error(QString("Unknown opcode: %1").arg(opcode));
            break;
    }
    
    if (!pcModified) {
        pc += 4;  // Move to next instruction
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
            Logger::instance().error("Division by zero error in DIV instruction.");
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
            Logger::instance().error("Division by zero error in DIVU instruction.");
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
            Logger::instance().error("Division by zero error in REM instruction.");
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
            Logger::instance().error("Division by zero error in REMU instruction.");
            regFile[rd].set(0xFFFFFFFF);
        }
        else
        {
            regFile[rd].set(regFile[rs1].get() % regFile[rs2].get());
        }
        break;
    default:
        Logger::instance().error(QString("Unknown R-type sub-opcode: %1").arg(sub_op));
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
        Logger::instance().error(QString("Unknown I-type sub-opcode: %1").arg(sub_op));
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
        recordMemoryAccess(addr, 1, false);
        regFile[rd].set(static_cast<int8_t>(memory.readByte(addr)));
        break;
    case 0x1: // LBU
        recordMemoryAccess(addr, 1, false);
        regFile[rd].set(static_cast<uint8_t>(memory.readByte(addr)));
        break;
    case 0x2: // LH
        recordMemoryAccess(addr, 2, false);
        regFile[rd].set(static_cast<int16_t>(memory.readHalf(addr)));
        break;
    case 0x3: // LHU
        recordMemoryAccess(addr, 2, false);
        regFile[rd].set(static_cast<uint16_t>(memory.readHalf(addr)));
        break;
    case 0x4: // LW
        recordMemoryAccess(addr, 4, false);
        regFile[rd].set(static_cast<uint32_t>(memory.readWord(addr)));
        break;
    case 0x5: // SB
        recordMemoryAccess(addr, 1, true);
        writeMemoryTrackedByte(addr, static_cast<uint8_t>(regFile[rd].get() & 0xFF));
        break;
    case 0x6: // SH
        recordMemoryAccess(addr, 2, true);
        writeMemoryTrackedHalf(addr, static_cast<uint16_t>(regFile[rd].get() & 0xFFFF));
        break;
    case 0x7: // SW
        recordMemoryAccess(addr, 4, true);
        writeMemoryTrackedWord(addr, static_cast<uint32_t>(regFile[rd].get()));
        break;
    default:
        Logger::instance().error(QString("Unknown Load/Store sub-opcode: %1").arg(sub_op));
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

    // Shift as unsigned to avoid UB when immediate is negative.
    const uint32_t branchOffset = static_cast<uint32_t>(sign_ext_imm) << 2;

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
        Logger::instance().error(QString("Unknown B-type sub-opcode: %1").arg(sub_op));
        break;
    }
    if (takeBranch)
    {
        pc += branchOffset;
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
        pc += static_cast<uint32_t>(sign_ext_imm) << 2;
        break;
    case 0x1: // JALR
    {
        uint32_t temp = pc + 4;
        pc = (regFile[rs].get() + (static_cast<uint32_t>(sign_ext_imm) << 2)) & ~1u;
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
        Logger::instance().info("ECALL invoked.");
        break;
    case 0x1: // BREAK
        Logger::instance().info("BREAK invoked. Halting execution.");
        Logger::instance().info(QString("Final PC: 0x%1").arg(pc, 8, 16, QChar('0')));
        Logger::instance().info(QString::fromStdString(std::string("Final Registers: ") + getRegisterState()));
        requestShutdown();
        break;
    default:
        Logger::instance().error(QString("Unknown S-type sub-opcode: %1").arg(sub_op));
        break;
    }
}
