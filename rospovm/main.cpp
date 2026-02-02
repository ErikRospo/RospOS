#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstdint>
#include <algorithm> // For std::find

#include "InstructionDecoder.h"
#include "Register.h"
#include "RospOSVM.h"
#include "Binary.h"

int main(int argc, char* argv[]) {
    std::cerr << "RospOS Virtual Machine starting..." << std::endl;
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <file.rosp> [--verbose] [--step]" << std::endl;
        return 1;
    }

    std::string rospFile = argv[1];
    bool verboseMode = (std::find(argv, argv + argc, std::string("--verbose")) != argv + argc);
    bool stepMode = (std::find(argv, argv + argc, std::string("--step")) != argv + argc);

    Binary binary = Binary().load_binary(rospFile);

    RospOSVM vm(verboseMode);
    for (const auto& segment : binary.segments) {
        if (verboseMode) {
            std::cout << "Loading segment at address 0x" << std::hex << segment.address 
                      << " with size " << std::dec << segment.data.size() << " bytes." << std::endl;
            for (uint8_t byte : segment.data) {
                std::cout << std::hex << static_cast<int>(byte) << " ";
            }
            std::cout << std::dec << std::endl;
        }
        vm.loadBinaryAtAddress(std::vector<char>(segment.data.begin(), segment.data.end()), segment.address);
    }
    std::cout << "Loaded. Starting execution..." << std::endl;

    char ch;
    if (stepMode) {
        std::cout << "Press Enter to step, 'q' to quit." << std::endl;
    }
    while (true) {
        if (stepMode) {
            std::cin.get(ch);
            if (ch == 'q') break;
        }
        vm.step();
    }
    return 0;
}