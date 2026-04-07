#ifndef ROSPOS_VM_H
#define ROSPOS_VM_H

#include <cstdint>
#include <string>
#include <vector>
#include <memory>
#include <array>
#include <deque>
#include <unordered_map>
#include <unordered_set>

#include "Register.h"
#include "Memory.h"
#include "Display.h"
#include "Binary.h"

// Compile-time flag to enable/disable state capture (for debugging and step-backward)
// Set to 1 for Qt GUI (needs full debugging), 0 for headless/minimal (performance)
#ifndef ROSPOSVM_ENABLE_STATE_CAPTURE
#define ROSPOSVM_ENABLE_STATE_CAPTURE 1
#endif

class RospOSVM
{
private:
    struct MemoryAccess {
        uint32_t address = 0;
        uint8_t size = 0;
        bool isWrite = false;
    };

    struct MemoryByteDelta {
        uint32_t address;
        uint8_t previousValue;
    };

    struct VMStateSnapshot {
        uint32_t pc;
        std::array<uint32_t, 16> registers;
        std::vector<MemoryByteDelta> memoryDeltas;
        std::unordered_set<uint32_t> touchedAddresses;
    };

    struct DecodedInstruction {
        uint32_t raw = 0;
        uint8_t opcode = 0;
        uint8_t subOp = 0;
        uint8_t rd = 0;
        uint8_t rs1 = 0;
        uint8_t rs2 = 0;
        uint32_t zeroExtImm = 0;
        int32_t signExtImm = 0;
    };

    static constexpr size_t kMaxStateHistory = 32;
    static constexpr bool kEnableStateCapture = (ROSPOSVM_ENABLE_STATE_CAPTURE != 0);

    RegisterFile regFile;
    uint32_t pc; // Program Counter
    Memory memory;
    std::shared_ptr<Binary> loadedBinary;  // Loaded binary with debug info
    
    // State capture only used when ROSPOSVM_ENABLE_STATE_CAPTURE is enabled
    std::deque<VMStateSnapshot> stateHistory;
    std::unique_ptr<VMStateSnapshot> currentSnapshot;
    bool applyingHistory = false;
    MemoryAccess lastMemoryAccess;
    bool hasLastMemoryAccess = false;

    // Fast debug lookup caches (built lazily from loadedBinary->debug_map).
    mutable bool debugCacheBuilt = false;
    mutable std::unordered_map<uint32_t, const DebugEntry*> debugEntryCache;
    mutable std::unordered_map<uint32_t, std::string> debugSourceFileCache;
    mutable std::unordered_map<uint32_t, std::unordered_map<std::string, const RegisterAllocationInfo*>> registerAllocCache;

    std::unordered_map<uint32_t, DecodedInstruction> decodedInstructionCache;

    void invalidateDebugCache();
    void buildDebugCache() const;
    static DecodedInstruction decodeInstructionFields(uint32_t rawInstruction);
    const DecodedInstruction& fetchDecodedInstruction(uint32_t instructionAddress);
    uint32_t executeBasicBlock();

    void beginStateCapture();
    void commitStateCapture();
    void clearStateHistory();
    void clearLastMemoryAccess();
    void recordMemoryAccess(uint32_t address, uint8_t size, bool isWrite);
    void recordMemoryDeltaForByte(uint32_t address);
    void writeMemoryTrackedByte(uint32_t address, uint8_t value);
    void writeMemoryTrackedHalf(uint32_t address, uint16_t value);
    void writeMemoryTrackedWord(uint32_t address, uint32_t value);
    
    void rTypeInstruction(const DecodedInstruction &instruction);
    void iArithTypeInstruction(const DecodedInstruction &instruction);
    void iTypeLSInstruction(const DecodedInstruction &instruction);
    bool bTypeInstruction(const DecodedInstruction &instruction);
    void jTypeInstruction(const DecodedInstruction &instruction);
    void sTypeInstruction(const DecodedInstruction &instruction);
    void executeInstruction(const DecodedInstruction &instruction);

public:
    bool debugMode;
    RospOSVM(bool debugMode);
    void resetCpuState();
    void loadBinaryAtAddress(const std::vector<char> &binary, uint32_t address);
    void loadBinaryFromFile(const std::string& filename);
    uint32_t step();
    bool stepBackward();
    bool canStepBackward() const { 
        if constexpr (kEnableStateCapture) {
            return !stateHistory.empty();
        } else {
            return false;
        }
    }
    std::string getRegisterState() const;

    // Debugger interface
    uint32_t getProgramCounter() const { return pc; }
    void setProgramCounter(uint32_t newPc) { pc = newPc; }
    
    RegisterFile& getRegisterFile() { return regFile; }
    const RegisterFile& getRegisterFile() const { return regFile; }
    
    uint32_t getRegister(int index) const { return regFile[index].get(); }
    void setRegister(int index, uint32_t value) { regFile[index].set(value); }
    
    Memory& getMemory() { return memory; }
    const Memory& getMemory() const { return memory; }
    
    uint32_t readMemory(uint32_t address) const { return memory.readWord(address); }
    void writeMemory(uint32_t address, uint32_t value);
    uint8_t readMemoryByte(uint32_t address) const { return memory.readByte(address); }
    uint8_t readMemoryByteForInspector(uint32_t address) const { return memory.readByteForInspector(address); }
    void writeMemoryByte(uint32_t address, uint8_t value);
    bool getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const;
    
    // Debug info access (Phase 6)
    /**
     * Get debug info for a specific address.
     * @param address The memory address to look up
     * @return Pointer to DebugEntry if found, nullptr otherwise
     */
    const DebugEntry* getDebugInfo(uint32_t address) const;
    
    /**
     * Format a source location string for display (e.g., in error messages).
     * @param address The memory address to format
     * @return String like "main.ros:42" or "unknown" if not found
     */
    std::string formatSourceLocation(uint32_t address) const;
    
    /**
     * Get the original source instruction text.
     * @param address The memory address
     * @return Original instruction text or empty string if not found
     */
    std::string getOriginalInstruction(uint32_t address) const;

    /**
     * Get register allocation info for an address/register pair.
     */
    const RegisterAllocationInfo* getRegisterAllocation(uint32_t address, const std::string &regName) const;

    /**
     * Convenience overload using register index 0..15.
     */
    const RegisterAllocationInfo* getRegisterAllocation(uint32_t address, int regIndex) const;
    
    /**
     * Get the loaded binary (contains debug info maps).
     * @return Shared pointer to the loaded Binary, or nullptr if not loaded
     */
    std::shared_ptr<Binary> getLoadedBinary() const { return loadedBinary; }
};

#endif // ROSPOS_VM_H