#ifndef ROSPOS_VM_H
#define ROSPOS_VM_H

#include <cstdint>
#include <string>
#include <vector>
#include <memory>
#include <array>
#include <deque>

#include "Register.h"
#include "Memory.h"
#include "Display.h"
#include "Binary.h"

class RospOSVM
{
private:
    struct MemoryByteDelta {
        uint32_t address;
        uint8_t previousValue;
    };

    struct VMStateSnapshot {
        uint32_t pc;
        std::array<uint32_t, 16> registers;
        std::vector<MemoryByteDelta> memoryDeltas;
    };

    static constexpr size_t kMaxStateHistory = 16;

    RegisterFile regFile;
    uint32_t pc; // Program Counter
    Memory memory;
    std::shared_ptr<Binary> loadedBinary;  // Loaded binary with debug info
    std::deque<VMStateSnapshot> stateHistory;
    std::unique_ptr<VMStateSnapshot> currentSnapshot;
    bool applyingHistory = false;

    void beginStateCapture();
    void commitStateCapture();
    void clearStateHistory();
    void recordMemoryDeltaForByte(uint32_t address);
    void writeMemoryTrackedByte(uint32_t address, uint8_t value);
    void writeMemoryTrackedHalf(uint32_t address, uint16_t value);
    void writeMemoryTrackedWord(uint32_t address, uint32_t value);
    
    void rTypeInstruction(uint32_t instruction);
    void iArithTypeInstruction(uint32_t instruction);
    void iTypeLSInstruction(uint32_t instruction);
    bool bTypeInstruction(uint32_t instruction);
    void jTypeInstruction(uint32_t instruction);
    void sTypeInstruction(uint32_t instruction);
    void executeInstruction(uint32_t instruction);

public:
    bool debugMode;
    RospOSVM(bool debugMode);
    void loadBinaryAtAddress(const std::vector<char> &binary, uint32_t address);
    void loadBinaryFromFile(const std::string& filename);
    void step();
    bool stepBackward();
    bool canStepBackward() const { return !stateHistory.empty(); }
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
    void writeMemoryByte(uint32_t address, uint8_t value);
    
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
     * Get the loaded binary (contains debug info maps).
     * @return Shared pointer to the loaded Binary, or nullptr if not loaded
     */
    std::shared_ptr<Binary> getLoadedBinary() const { return loadedBinary; }
};

void dumpMemoryToFile(const Memory &memory);
#endif // ROSPOS_VM_H