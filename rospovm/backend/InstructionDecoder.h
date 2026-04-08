#ifndef INSTRUCTION_DECODER_H
#define INSTRUCTION_DECODER_H

#include <string>
#include <cstdint>
#include "Register.h"
#include "Memory.h"

std::string decodeInstruction(uint32_t instruction, RegisterFile &regFile);
std::string formatRegister(uint32_t reg, RegisterFile &regFile);
std::string formatRegisterValues(uint32_t rd, uint32_t rs1, uint32_t rs2, RegisterFile &regFile);
#endif // INSTRUCTION_DECODER_H