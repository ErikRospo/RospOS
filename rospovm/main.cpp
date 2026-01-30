#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstdint>

#include "InstructionDecoder.h"
#include "Register.h"
#include "RospOSVM.h"
#include "MemoryMapParser.h"


int main(int argc, char* argv[]) {
    std::cerr << "RospOS Virtual Machine starting..." << std::endl;
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <mmap.txt>" << std::endl;
        return 1;
    }

    std::string mmapFile = argv[1];
    auto memoryMap = parseMemoryMap(mmapFile);

    RospOSVM vm;
    for (const auto& [address, filename] : memoryMap) {
        std::ifstream file(filename, std::ios::binary | std::ios::ate);
        if (!file) {
            std::cerr << "Failed to open binary file: " << filename << std::endl;
            continue;
        }

        std::streamsize size = file.tellg();
        file.seekg(0, std::ios::beg);

        std::vector<char> buffer(size);
        if (!file.read(buffer.data(), size)) {
            std::cerr << "Failed to read binary file: " << filename << std::endl;
            continue;
        }

        try {
            vm.loadBinaryAtAddress(buffer, address);
            std::cerr << "Loaded " << filename << " at address 0x" << std::hex << address << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "Error loading binary at address 0x" << std::hex << address << ": " << e.what() << std::endl;
        }
    }

    // Simple execution loop
    while (true){
        vm.step();
    }
    

    return 0;
}