#include "RospOSVM.h"
#include "Binary.h"

#include <cstdint>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <string>
#include <vector>

static uint32_t readU32(std::istream &input)
{
    uint32_t value = 0;
    for (int index = 0; index < 4; ++index) {
        const int byte = input.get();
        if (byte == std::char_traits<char>::eof()) {
            throw std::runtime_error("truncated segment image");
        }
        value = (value << 8) | static_cast<uint8_t>(byte);
    }
    return value;
}

int main(int argc, char **argv)
{
    if (argc == 3 && std::string(argv[1]) == "--binary-file") {
        try {
            Binary binary;
            binary.load_binary(argv[2]);
            std::cout << "accepted\n";
        } catch (const std::exception &error) {
            std::cout << "rejected " << error.what() << '\n';
        }
        return 0;
    }
    if (argc == 2 && std::string(argv[1]) == "--run-image") {
        try {
            const uint32_t count = readU32(std::cin);
            if (count == 0 || count > 16) return 2;
            RospOSVM vm(false, "");
            for (uint32_t index = 0; index < count; ++index) {
                const uint32_t address = readU32(std::cin);
                const uint32_t size = readU32(std::cin);
                if (size == 0 || size > (1U << 20)) return 2;
                std::vector<char> segment(size);
                if (!std::cin.read(segment.data(), size)) return 2;
                vm.loadBinaryAtAddress(segment, address);
            }
            vm.setProgramCounter(vm.readMemory(0xFFFFFFFC));
            vm.runSteps(256);
            std::cout << "result " << vm.getRegister(1) << '\n';
        } catch (const std::exception &error) {
            std::cerr << error.what() << '\n';
            return 4;
        }
        return 0;
    }
    std::vector<char> program((std::istreambuf_iterator<char>(std::cin)), {});
    if (program.empty() || program.size() > 64 || program.size() % 4 != 0) {
        return 2;
    }

    try {
        RospOSVM vm(false, "");
        vm.loadBinaryAtAddress(program, 0x1000);
        vm.setProgramCounter(0x1000);
        vm.runSteps(32);
        if (vm.getRegister(0) != 0) {
            return 3;
        }
        std::cout << "ok " << vm.getProgramCounter() << " " << vm.getRegister(1) << '\n';
    } catch (const std::exception &error) {
        // Invalid memory accesses and arithmetic traps are valid fuzz outcomes.
        std::cout << "rejected " << error.what() << '\n';
    }
    return 0;
}
