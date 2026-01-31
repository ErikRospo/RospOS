#include <iostream>
#include <fstream>
#include <vector>
#include <string>
#include <cstdint>

#include "InstructionDecoder.h"
#include "Register.h"
#include "RospOSVM.h"
#include "MemoryMapParser.h"
#include "Binary.h"

int main(int argc, char* argv[]) {
    std::cerr << "RospOS Virtual Machine starting..." << std::endl;
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <file.rosp>" << std::endl;
        return 1;
    }

    std::string rospFile = argv[1];
    
    Binary binary = Binary().load_binary(rospFile);

    RospOSVM vm;
    for (const auto& segment : binary.segments) {
        vm.loadBinaryAtAddress(std::vector<char>(segment.data.begin(), segment.data.end()), segment.address);
    }

    // Simple execution loop
    while (true){
        vm.step();
    }
    

    return 0;
}