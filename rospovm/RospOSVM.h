#ifndef ROSPOS_VM_H
#define ROSPOS_VM_H

#include "Register.h"
#include "Memory.h"
#include <vector>
#include <cstdint>
#include <string>

class RospOSVM {
private:
    RegisterFile regFile;
    uint32_t pc; // Program Counter
    Memory memory;
    void rTypeInstruction(uint32_t instruction);
    void iArithTypeInstruction(uint32_t instruction);
    void iTypeLSInstruction(uint32_t instruction);
    void bTypeInstruction(uint32_t instruction);
    void jTypeInstruction(uint32_t instruction);
    void sTypeInstruction(uint32_t instruction);
    void executeInstruction(uint32_t instruction);

public:
    bool debugMode;
    RospOSVM(bool debugMode);
    void loadBinaryAtAddress(const std::vector<char>& binary, uint32_t address);
    void step();
    std::string getRegisterState() const;
};

#endif // ROSPOS_VM_H