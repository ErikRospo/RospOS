#ifndef ROSPOS_VM_H
#define ROSPOS_VM_H

#include "Register.h"
#include "Memory.h"
#include "Display.h"
#include <vector>
#include <cstdint>
#include <string>

class RospOSVM
{
private:
    RegisterFile regFile;
    uint32_t pc; // Program Counter
    Memory memory;
    // Display display;
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
    void step();
    std::string getRegisterState() const;

    // Debugger interface
    uint32_t getProgramCounter() const { return pc; }
    void setProgramCounter(uint32_t newPc) { pc = newPc; }
    
    RegisterFile &getRegisterFile() { return regFile; }
    const RegisterFile &getRegisterFile() const { return regFile; }
    
    uint32_t getRegister(int index) const { return regFile[index].get(); }
    void setRegister(int index, uint32_t value) { regFile[index].set(value); }
    
    Memory &getMemory() { return memory; }
    const Memory &getMemory() const { return memory; }
    
    uint32_t readMemory(uint32_t address) const { return memory.readWord(address); }
    void writeMemory(uint32_t address, uint32_t value) { memory.writeWord(address, value); }
    uint8_t readMemoryByte(uint32_t address) const { return memory.readByte(address); }
    void writeMemoryByte(uint32_t address, uint8_t value) { memory.writeByte(address, value); }
};

void dumpMemoryToFile(const Memory &memory);
#endif // ROSPOS_VM_H