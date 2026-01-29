#include "MemoryMapParser.h"
#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>

std::map<uint32_t, std::string> parseMemoryMap(const std::string& mmapFile) {
    std::map<uint32_t, std::string> memoryMap;
    std::ifstream file(mmapFile);
    if (!file) {
        std::cerr << "Failed to open memory map file: " << mmapFile << std::endl;
        throw std::runtime_error("Failed to open memory map file");
    }

    std::string line;
    while (std::getline(file, line)) {
        std::istringstream iss(line);
        uint32_t address;
        std::string filename;
        if (!(iss >> std::hex >> address) || !(iss.ignore(2)) || !(iss >> filename)) {
            std::cerr << "Invalid line in memory map file: " << line << std::endl;
            throw std::runtime_error("Invalid line in memory map file");
        }
        memoryMap[address] = filename;
    }
    return memoryMap;
}