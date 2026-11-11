#include "RospOSVM.h"
#include "Logger.h"
#include "Shutdown.h"

#include <array>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {
constexpr uint32_t faultPc = 0x1000;
constexpr uint32_t handlerPc = 0x4000;
constexpr uint32_t stackTop = 0x8003; // PUSH/POP also support an unaligned SP.

void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void prepare(RospOSVM &vm, uint32_t instruction)
{
    vm.resetCpuState();
    vm.writeMemory(0xFFFFFFF8, handlerPc);
    vm.writeMemory(faultPc, instruction);
    vm.writeMemory(handlerPc, 0x10AA0001); // ADDI r10, r10, 1
    for (int reg = 1; reg < 15; ++reg) vm.setRegister(reg, 0x110000 + reg);
    vm.setRegister(15, stackTop);
    for (uint32_t offset = 4; offset <= 64; offset += 4)
        vm.writeMemory(stackTop - offset, 0xA5A5A5A5);
    vm.setProgramCounter(faultPc);
}

void checkDispatch(RospOSVM &vm, uint32_t errorCode, int executionMode)
{
    std::array<uint32_t, 16> original;
    for (int reg = 0; reg < 16; ++reg) original[reg] = vm.getRegister(reg);
    vm.debugMode = executionMode == 2;
    if (executionMode == 0) vm.step();
    else require(vm.runSteps(1) == 1, "faulting instruction was not counted once");

    require(!shouldShutdown(), "fault dispatch halted instead of entering the handler");
    require(vm.getProgramCounter() == handlerPc, "handler entry was skipped or PC advanced");
    require(vm.getRegister(0) == 0 && vm.getRegister(1) == errorCode, "wrong fault code/zero register");
    require(vm.getRegister(15) == stackTop - 64, "fault frame has the wrong size");
    require(vm.readMemory(stackTop - 64) == faultPc, "frame saved the wrong PC");
    for (int reg = 1; reg < 16; ++reg) {
        require(vm.readMemory(stackTop - 64 + reg * 4) == original[reg], "saved registers are out of order or clobbered");
        if (reg >= 2 && reg < 15)
            require(vm.getRegister(reg) == original[reg], "fault changed a general register");
    }

    vm.step();
    require(vm.getRegister(10) == original[10] + 1, "handler's first instruction did not execute");
    require(vm.stepBackward() && vm.getProgramCounter() == handlerPc, "cannot undo handler instruction");
    require(vm.stepBackward() && vm.getProgramCounter() == faultPc, "cannot undo fault entry");
    for (int reg = 0; reg < 16; ++reg)
        require(vm.getRegister(reg) == original[reg], "step-back did not restore fault registers");
    for (uint32_t offset = 4; offset <= 64; offset += 4)
        require(vm.readMemory(stackTop - offset) == 0xA5A5A5A5, "step-back left a fault stack write behind");
    vm.step();
    require(!shouldShutdown() && vm.getProgramCounter() == handlerPc, "step-back did not restore fault-dispatch state");
}

void testDispatch(RospOSVM &vm)
{
    // Exercise every reserved family/sub-opcode, including family F's reserved operations.
    const std::array<int, 16> highestValid = {15, 6, 7, 5, 1, 1, -1, -1, -1, -1, -1, -1, -1, -1, -1, 0};
    for (int mode = 0; mode < 3; ++mode) {
        for (uint32_t family = 0; family < 16; ++family) {
            for (uint32_t op = highestValid[family] + 1; op < 16; ++op) {
                prepare(vm, (family << 28) | (op << 24) | 0x00234000);
                checkDispatch(vm, 0x10000 | (family << 4) | op, mode);
            }
        }
        for (uint32_t op = 0xC; op <= 0xF; ++op) {
            // Include destinations aliasing an operand, r1, and SP.
            for (uint32_t dest : {1U, 3U, 8U, 15U}) {
                prepare(vm, (op << 24) | (dest << 20) | 0x00034000);
                vm.setRegister(4, 0);
                checkDispatch(vm, 0x20000 | (op << 8) | 0x34, mode);
            }
        }
        for (uint32_t op : {0xCU, 0xEU}) {
            prepare(vm, (op << 24) | 0x00834000);
            vm.setRegister(3, 0x80000000);
            vm.setRegister(4, 0xFFFFFFFF);
            checkDispatch(vm, 0x20000 | (op << 8) | 0x34, mode);
        }
    }

    for (uint32_t op = 0xC; op <= 0xF; ++op) {
        prepare(vm, (op << 24) | 0x00834000);
        vm.setRegister(3, 17);
        vm.setRegister(4, 5);
        vm.step();
        require(vm.getRegister(8) == (op <= 0xD ? 3U : 2U), "valid division/remainder changed");
        require(vm.getRegister(15) == stackTop && vm.getProgramCounter() == faultPc + 4, "valid operation dispatched a fault");
    }
    prepare(vm, 0xF0000000);
    vm.step();
    require(vm.getProgramCounter() == faultPc + 4 && !shouldShutdown(), "valid NOP was rejected");
}

void testHalt(RospOSVM &vm, const std::string &scenario)
{
    prepare(vm, 0x5F000000);
    if (scenario == "missing") vm.writeMemory(0xFFFFFFF8, 0);
    else if (scenario == "unaligned") vm.writeMemory(0xFFFFFFF8, handlerPc + 1);
    else if (scenario == "stack_underflow") vm.setRegister(15, 63);
    else if (scenario == "stack_mmio") vm.setRegister(15, 0x10000020);
    else if (scenario == "nested") {
        vm.writeMemory(handlerPc, 0x5F000000);
        vm.step();
        require(vm.getProgramCounter() == handlerPc && !shouldShutdown(), "first fault failed");
    } else throw std::runtime_error("unknown halt scenario");

    const uint32_t beforePc = vm.getProgramCounter();
    std::array<uint32_t, 16> original;
    for (int reg = 0; reg < 16; ++reg) original[reg] = vm.getRegister(reg);
    vm.step();
    require(shouldShutdown(), "undispatchable fault did not halt");
    require(vm.getProgramCounter() == beforePc, "undispatchable fault advanced PC");
    for (int reg = 0; reg < 16; ++reg)
        require(vm.getRegister(reg) == original[reg], "undispatchable fault clobbered registers");
    if (scenario != "nested")
        for (uint32_t offset = 4; offset <= 64; offset += 4)
            require(vm.readMemory(stackTop - offset) == 0xA5A5A5A5, "undispatchable fault changed the stack");
}
}

int main(int argc, char **argv)
{
    try {
        Logger::instance().setLogLevel(Logger::ERROR);
        RospOSVM vm(false, "");
        const std::string scenario = argc > 1 ? argv[1] : "dispatch";
        if (scenario == "dispatch") testDispatch(vm);
        else testHalt(vm, scenario);
        std::cout << "Error dispatch tests passed: " << scenario << '\n';
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
