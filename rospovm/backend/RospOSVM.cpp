#include "RospOSVM.h"

#include <cstdint>
#include <cstdlib>
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
#include "BlockDevice.h"
#include "Shutdown.h"
#include "TTY.h"

RospOSVM::RospOSVM(bool debugMode) 
        : memory(1ULL << 32),  // Initialize 4GB memory
            debugMode(debugMode)
{
        pc = 0;                           // Set after loading binary reset vector
    regFile.sp().set(0x0FFFFFFF);     // Top of RAM
    regFile.unchecked(0).setReadOnly(true);     // R0 is always zero

    // Setup TTY MMIO range
    memory.addSpecialRange("TTY ", 0x10000000, 0x100001FF, 
                           SpecialMemoryRange::Type::MMIO, true, true,
                           TTYReadHandler, TTYWriteHandler);
    
    // Setup Display MMIO range
    // Note: VMDisplay instance is created in MainWindow for Qt GUI, or separately for CLI
    memory.addSpecialRange("DISP", 0x20000000, 0x2000FFFF, 
                           SpecialMemoryRange::Type::MMIO, true, true,
                           VMDisplay::displayReadHandler, VMDisplay::displayWriteHandler);

    // Setup Block Device MMIO range
    const char *blockDevicePath = std::getenv("ROSPOS_BLOCK_DEVICE_FILE");
    std::string resolvedBlockDevicePath =
        (blockDevicePath != nullptr && blockDevicePath[0] != '\0')
        ? std::string(blockDevicePath)
        : std::string("rospos.blockdev");
    BlockDeviceInitialize(&memory, resolvedBlockDevicePath);
    memory.addSpecialRange("BLK ", 0x40000000, 0x400000FF,
                           SpecialMemoryRange::Type::MMIO, true, true,
                           BlockDeviceReadHandler, BlockDeviceWriteHandler);
}

void RospOSVM::invalidateDebugCache()
{
    debugCacheBuilt = false;
    debugEntryCache.clear();
    debugSourceFileCache.clear();
    registerAllocCache.clear();
}

void RospOSVM::buildDebugCache() const
{
    if (debugCacheBuilt) {
        return;
    }

    debugEntryCache.clear();
    debugSourceFileCache.clear();
    registerAllocCache.clear();

    if (!loadedBinary) {
        debugCacheBuilt = true;
        return;
    }

    for (const auto &debugPair : loadedBinary->debug_map) {
        const std::shared_ptr<DebugInfo> &debugInfo = debugPair.second;
        if (!debugInfo) {
            continue;
        }

        for (const auto &entry : debugInfo->entries) {
            debugEntryCache.emplace(entry.address, &entry);

            auto fileIt = debugInfo->file_table.find(entry.file_id);
            if (fileIt != debugInfo->file_table.end()) {
                debugSourceFileCache.emplace(entry.address, fileIt->second);
            }
        }

        for (const auto &addrAllocPair : debugInfo->register_allocations) {
            const uint32_t address = addrAllocPair.first;
            auto &byRegister = registerAllocCache[address];
            for (const auto &alloc : addrAllocPair.second) {
                byRegister.emplace(alloc.reg, &alloc);
            }
        }
    }

    debugCacheBuilt = true;
}

RospOSVM::DecodedInstruction RospOSVM::decodeInstructionFields(uint32_t rawInstruction)
{
    DecodedInstruction decoded;
    decoded.raw = rawInstruction;
    decoded.opcode = static_cast<uint8_t>((rawInstruction >> 28) & 0x0F);
    decoded.subOp = static_cast<uint8_t>((rawInstruction >> 24) & 0x0F);
    decoded.rd = static_cast<uint8_t>((rawInstruction >> 20) & 0x0F);
    decoded.rs1 = static_cast<uint8_t>((rawInstruction >> 16) & 0x0F);
    decoded.rs2 = static_cast<uint8_t>((rawInstruction >> 12) & 0x0F);

    const uint16_t imm16 = static_cast<uint16_t>(rawInstruction & 0xFFFF);
    decoded.zeroExtImm = static_cast<uint32_t>(imm16);
    decoded.signExtImm = static_cast<int32_t>(static_cast<int16_t>(imm16));
    return decoded;
}

const RospOSVM::DecodedInstruction& RospOSVM::fetchDecodedInstruction(uint32_t instructionAddress)
{
    const uint32_t rawInstruction = memory.readWord(instructionAddress);
    auto it = decodedInstructionCache.find(instructionAddress);
    if (it != decodedInstructionCache.end() && it->second.raw == rawInstruction) {
        return it->second;
    }

    auto [insertedIt, _] = decodedInstructionCache.insert_or_assign(
        instructionAddress,
        decodeInstructionFields(rawInstruction)
    );
    return insertedIt->second;
}

uint32_t RospOSVM::executeBasicBlock()
{
    // Keep steps bounded so long-running loops still yield control regularly.
    static constexpr uint32_t kMaxInstructionsPerFastStep = 64;

    uint32_t executedInstructions = 0;
    clearLastMemoryAccess();
    for (uint32_t i = 0; i < kMaxInstructionsPerFastStep; ++i) {
        const DecodedInstruction &decoded = fetchDecodedInstruction(pc);
        executeInstruction(decoded);
        ++executedInstructions;

        if (decoded.opcode == 0x3 || decoded.opcode == 0x4 || decoded.opcode == 0x5) {
            break;
        }
    }

    return executedInstructions;
}

void RospOSVM::resetCpuState()
{
    pc = 0;
    for (int i = 1; i < 16; ++i) {
        regFile.unchecked(i).set(0);
    }
    regFile.sp().set(0x0FFFFFFF);
    invalidateDebugCache();
    decodedInstructionCache.clear();
    clearStateHistory();
    clearLastMemoryAccess();
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
    if constexpr (kEnableStateCapture) {
        currentSnapshot = std::make_unique<VMStateSnapshot>();
        currentSnapshot->pc = pc;
        currentSnapshot->memoryDeltas.reserve(16);
        currentSnapshot->touchedAddresses.reserve(16);
        for (int i = 0; i < 16; ++i) {
            currentSnapshot->registers[static_cast<size_t>(i)] = regFile.unchecked(i).get();
        }
    }
}

void RospOSVM::commitStateCapture()
{
    if constexpr (kEnableStateCapture) {
        if (!currentSnapshot) {
            return;
        }

        stateHistory.push_back(std::move(*currentSnapshot));
        currentSnapshot.reset();

        while (stateHistory.size() > kMaxStateHistory) {
            stateHistory.pop_front();
        }
    }
}

void RospOSVM::clearStateHistory()
{
    if constexpr (kEnableStateCapture) {
        stateHistory.clear();
        currentSnapshot.reset();
    }
}

void RospOSVM::recordMemoryDeltaForByte(uint32_t address)
{
    if constexpr (kEnableStateCapture) {
        if (!currentSnapshot || applyingHistory) {
            return;
        }

        // MMIO/special ranges may have side effects or block on reads (e.g. TTY).
        // Do not include them in reversible memory snapshots.
        if (memory.isSpecialAddress(address)) {
            return;
        }

        const auto insertResult = currentSnapshot->touchedAddresses.insert(address);
        if (!insertResult.second) {
            return;
        }

        uint8_t previousValue = 0;
        try {
            previousValue = memory.readByte(address);
        } catch (const std::exception &) {
            // Non-readable regions cannot be reliably restored.
            currentSnapshot->touchedAddresses.erase(address);
            return;
        }

        currentSnapshot->memoryDeltas.push_back({address, previousValue});
    }
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
    // Keep per-byte deltas for reversible execution while doing a single memory write.
    recordMemoryDeltaForByte(address);
    recordMemoryDeltaForByte(address + 1);
    recordMemoryDeltaForByte(address + 2);
    recordMemoryDeltaForByte(address + 3);
    memory.writeWord(address, value);
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
    loadedBinary.reset();
    invalidateDebugCache();
    decodedInstructionCache.clear();
    clearStateHistory();
    clearLastMemoryAccess();
    memory.loadBinary(binary, address);
}

void RospOSVM::loadBinaryFromFile(const std::string& filename)
{
    resetCpuState();

    // Load the binary file using Binary::load_binary
    try {
        loadedBinary = std::make_shared<Binary>();
        *loadedBinary = loadedBinary->load_binary(filename);
        invalidateDebugCache();
        
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
    buildDebugCache();
    auto it = debugEntryCache.find(address);
    if (it != debugEntryCache.end()) {
        return it->second;
    }
    return nullptr;
}

std::string RospOSVM::formatSourceLocation(uint32_t address) const
{
    const DebugEntry* entry = getDebugInfo(address);
    if (!entry) {
        return "unknown";
    }
    
    buildDebugCache();
    auto fileIt = debugSourceFileCache.find(address);
    if (fileIt != debugSourceFileCache.end()) {
        std::ostringstream oss;
        oss << fileIt->second << ":" << entry->line;
        return oss.str();
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
    buildDebugCache();
    auto addrIt = registerAllocCache.find(address);
    if (addrIt == registerAllocCache.end()) {
        return nullptr;
    }

    const auto &allocByReg = addrIt->second;
    auto regIt = allocByReg.find(regName);
    if (regIt != allocByReg.end()) {
        return regIt->second;
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

    static const std::array<std::string, 16> kRegisterNames = {
        "r0", "r1", "r2", "r3", "r4", "r5", "r6", "r7",
        "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"
    };
    return getRegisterAllocation(address, kRegisterNames[static_cast<size_t>(regIndex)]);
}

uint32_t RospOSVM::step()
{
    if constexpr (!kEnableStateCapture) {
        if (!debugMode) {
            return executeBasicBlock();
        }
    }

    beginStateCapture();
    clearLastMemoryAccess();
    try {
        const DecodedInstruction &decoded = fetchDecodedInstruction(pc);
        if (debugMode)
        {
            std::ostringstream oss;
            oss << "PC: " << std::hex << pc << std::dec << " ";
            oss << "I: " << decodeInstruction(decoded.raw, regFile) << "\n";
            oss << "RI: " << std::hex << std::setw(8) << std::setfill('0') << decoded.raw << std::dec << "\n";
            oss << "Registers: " << getRegisterState();
            Logger::instance().debug(QString::fromStdString(oss.str()));
        }
        executeInstruction(decoded);
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
        return 1;
    } catch (...) {
        currentSnapshot.reset();
        throw;
    }
}

bool RospOSVM::stepBackward()
{
    if constexpr (!kEnableStateCapture) {
        return false;  // Step-backward not available when state capture is disabled
    } else {
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
            regFile.unchecked(i).set(snapshot.registers[static_cast<size_t>(i)]);
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
}

std::string RospOSVM::getRegisterState() const
{
    std::ostringstream state;
    for (int i = 0; i < 16; ++i)
    {
        state << "R" << i << ": " << std::hex << std::setw(8) << std::setfill('0') << regFile.unchecked(i).get() << " ";
    }
    return state.str();
}

void RospOSVM::executeInstruction(const DecodedInstruction &instruction)
{
    const uint32_t opcode = instruction.opcode;
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
void RospOSVM::rTypeInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-12 | 11-0          |
    |-------|-------|-------|-------|-------|---------------|
    | opcode| sub-op|   rd  |  rs1  |  rs2  |   unused      | */
    const uint32_t sub_op = instruction.subOp;
    const int rd = static_cast<int>(instruction.rd);
    const int rs1 = static_cast<int>(instruction.rs1);
    const int rs2 = static_cast<int>(instruction.rs2);
    Register &dst = regFile.unchecked(rd);
    const uint32_t rs1Val = regFile.unchecked(rs1).get();
    const uint32_t rs2Val = regFile.unchecked(rs2).get();
    switch (sub_op)
    {
    case 0x0: // ADD
        dst.set(rs1Val + rs2Val);
        break;
    case 0x1: // SUB
        dst.set(rs1Val - rs2Val);
        break;
    case 0x2: // AND
        dst.set(rs1Val & rs2Val);
        break;
    case 0x3: // OR
        dst.set(rs1Val | rs2Val);
        break;
    case 0x4: // XOR
        dst.set(rs1Val ^ rs2Val);
        break;
    case 0x5: // MUL (lower 32 bits)
        dst.set(rs1Val * rs2Val);
        break;
    case 0x6: // MULH
    {
        const uint64_t result = static_cast<uint64_t>(rs1Val) * static_cast<uint64_t>(rs2Val);
        dst.set(static_cast<uint32_t>(result >> 32));
    }
    break;
    case 0x7: // NEG
        dst.set(-rs1Val);
        break;
    case 0x8: // NOT
        dst.set(~rs1Val);
        break;
    case 0x9: // SHL
        dst.set(rs1Val << (rs2Val & 0x1F));
        break;
    case 0xA: // SHR
        dst.set(rs1Val >> (rs2Val & 0x1F));
        break;
    case 0xB: // SAR
        dst.set(static_cast<uint32_t>(static_cast<int32_t>(rs1Val) >> (rs2Val & 0x1F)));
        break;
    case 0xC: // DIV
        if (rs2Val == 0)
        {
            Logger::instance().error("Division by zero error in DIV instruction.");
            dst.set(0xFFFFFFFF);
        }
        else
        {
            dst.set(static_cast<uint32_t>(static_cast<int32_t>(rs1Val) / static_cast<int32_t>(rs2Val)));
        }
        break;
    case 0xD: // DIVU
        if (rs2Val == 0)
        {
            Logger::instance().error("Division by zero error in DIVU instruction.");
            dst.set(0xFFFFFFFF);
        }
        else
        {
            dst.set(rs1Val / rs2Val);
        }
        break;
    case 0xE: // REM
        if (rs2Val == 0)
        {
            Logger::instance().error("Division by zero error in REM instruction.");
            dst.set(0xFFFFFFFF);
        }
        else
        {
            dst.set(static_cast<uint32_t>(static_cast<int32_t>(rs1Val) % static_cast<int32_t>(rs2Val)));
        }
        break;
    case 0xF: // REMU
        if (rs2Val == 0)
        {
            Logger::instance().error("Division by zero error in REMU instruction.");
            dst.set(0xFFFFFFFF);
        }
        else
        {
            dst.set(rs1Val % rs2Val);
        }
        break;
    default:
        Logger::instance().error(QString("Unknown R-type sub-opcode: %1").arg(sub_op));
        break;
    }
}
void RospOSVM::iArithTypeInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0           |
    |-------|-------|-------|-------|----------------|
    | opcode| sub-op|   rd  |  rs1  |   immediate    | */
    const uint32_t sub_op = instruction.subOp;
    const int rd = static_cast<int>(instruction.rd);
    const int rs1 = static_cast<int>(instruction.rs1);
    const uint32_t zero_ext_imm = instruction.zeroExtImm;
    const int32_t sign_ext_imm = instruction.signExtImm;
    Register &dst = regFile.unchecked(rd);
    const uint32_t rs1Val = regFile.unchecked(rs1).get();

    switch (sub_op)
    {
    case 0x0: // ADDI
        dst.set(static_cast<uint32_t>(static_cast<int32_t>(rs1Val) + sign_ext_imm));
        break;
    case 0x1: // ANDI
        dst.set(rs1Val & zero_ext_imm);
        break;
    case 0x2: // ORI
        dst.set(rs1Val | zero_ext_imm);
        break;
    case 0x3: // XORI
        dst.set(rs1Val ^ zero_ext_imm);
        break;
    case 0x4: // SHLI
        dst.set(rs1Val << (zero_ext_imm & 0x1F));
        break;
    case 0x5: // SHRI
        dst.set(rs1Val >> (zero_ext_imm & 0x1F));
        break;
    case 0x6: // SARI
        dst.set(static_cast<uint32_t>(static_cast<int32_t>(rs1Val) >> (zero_ext_imm & 0x1F)));
        break;
    default:
        Logger::instance().error(QString("Unknown I-type sub-opcode: %1").arg(sub_op));
        break;
    }
}
void RospOSVM::iTypeLSInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
    */
    const uint32_t sub_op = instruction.subOp;
    const int rd = static_cast<int>(instruction.rd);
    const int rs = static_cast<int>(instruction.rs1);
    const int32_t sign_ext_imm = instruction.signExtImm;
    const uint32_t addr = regFile.unchecked(rs).get() + static_cast<uint32_t>(sign_ext_imm);
    Register &dst = regFile.unchecked(rd);
    switch (sub_op)
    {
    case 0x0: // LB
        recordMemoryAccess(addr, 1, false);
        dst.set(static_cast<uint32_t>(static_cast<int32_t>(static_cast<int8_t>(memory.readByte(addr)))));
        break;
    case 0x1: // LBU
        recordMemoryAccess(addr, 1, false);
        dst.set(static_cast<uint32_t>(static_cast<uint8_t>(memory.readByte(addr))));
        break;
    case 0x2: // LH
        recordMemoryAccess(addr, 2, false);
        dst.set(static_cast<uint32_t>(static_cast<int32_t>(static_cast<int16_t>(memory.readHalf(addr)))));
        break;
    case 0x3: // LHU
        recordMemoryAccess(addr, 2, false);
        dst.set(static_cast<uint32_t>(static_cast<uint16_t>(memory.readHalf(addr))));
        break;
    case 0x4: // LW
        recordMemoryAccess(addr, 4, false);
        dst.set(static_cast<uint32_t>(memory.readWord(addr)));
        break;
    case 0x5: // SB
        recordMemoryAccess(addr, 1, true);
        writeMemoryTrackedByte(addr, static_cast<uint8_t>(dst.get() & 0xFF));
        break;
    case 0x6: // SH
        recordMemoryAccess(addr, 2, true);
        writeMemoryTrackedHalf(addr, static_cast<uint16_t>(dst.get() & 0xFFFF));
        break;
    case 0x7: // SW
        recordMemoryAccess(addr, 4, true);
        writeMemoryTrackedWord(addr, dst.get());
        break;
    default:
        Logger::instance().error(QString("Unknown Load/Store sub-opcode: %1").arg(sub_op));
        break;
    }
}
bool RospOSVM::bTypeInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|  rs1  |  rs2  | immediate (16-bit offset)|
    */
    const uint32_t sub_op = instruction.subOp;
    const int rs1 = static_cast<int>(instruction.rd);
    const int rs2 = static_cast<int>(instruction.rs1);
    const int32_t sign_ext_imm = instruction.signExtImm;
    const uint32_t rs1Val = regFile.unchecked(rs1).get();
    const uint32_t rs2Val = regFile.unchecked(rs2).get();

    // Shift as unsigned to avoid UB when immediate is negative.
    const uint32_t branchOffset = static_cast<uint32_t>(sign_ext_imm) << 2;

    bool takeBranch = false;
    switch (sub_op)
    {
    case 0x0: // BEQ
        takeBranch = (rs1Val == rs2Val);
        break;
    case 0x1: // BNE
        takeBranch = (rs1Val != rs2Val);
        break;
    case 0x2: // BLT
        takeBranch = (static_cast<int32_t>(rs1Val) < static_cast<int32_t>(rs2Val));
        break;
    case 0x3: // BGE
        takeBranch = (static_cast<int32_t>(rs1Val) >= static_cast<int32_t>(rs2Val));
        break;
    case 0x4: // BLTU
        takeBranch = (rs1Val < rs2Val);
        break;
    case 0x5: // BGEU
        takeBranch = (rs1Val >= rs2Val);
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
void RospOSVM::jTypeInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
    |-------|-------|-------|-------|--------------------------|
    | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
    */
    const int32_t sub_op = static_cast<int32_t>(instruction.subOp);
    const int rd = static_cast<int>(instruction.rd);
    const int rs = static_cast<int>(instruction.rs1);
    const int32_t sign_ext_imm = instruction.signExtImm;
    Register &dst = regFile.unchecked(rd);
    switch (sub_op)
    {
    case 0x0: // JAL
        dst.set(pc + 4);
        pc += static_cast<uint32_t>(sign_ext_imm) << 2;
        break;
    case 0x1: // JALR
    {
        const uint32_t temp = pc + 4;
        pc = (regFile.unchecked(rs).get() + (static_cast<uint32_t>(sign_ext_imm) << 2)) & ~1u;
        dst.set(temp);
    }
    break;
    }
}
void RospOSVM::sTypeInstruction(const DecodedInstruction &instruction)
{
    /*
    | 31-28 | 27-24 | 23-0                             |
    |-------|-------|----------------------------------|
    | opcode| sub-op|   unused                         |
    */
    const uint32_t sub_op = instruction.subOp;
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
