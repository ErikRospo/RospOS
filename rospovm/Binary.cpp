#include "Binary.h"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>

// Magic number for RospOS binary format
const uint32_t ROSP_MAGIC = 0x50534F52;  // "ROSP" in ASCII

Binary Binary::load_binary(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        throw std::runtime_error("Failed to open binary file: " + path);
    }

    uint32_t magic;
    uint32_t version;
    uint32_t segment_count;

    file.read(reinterpret_cast<char*>(&magic), sizeof(magic));
    file.read(reinterpret_cast<char*>(&version), sizeof(version));
    file.read(reinterpret_cast<char*>(&segment_count), sizeof(segment_count));

    if (magic != ROSP_MAGIC) {
        throw std::runtime_error("Invalid binary format: magic number does not match");
    }
    
    std::cout << "Loading binary version " << version << " with " 
              << segment_count << " segments." << std::endl;

    Binary bin;
    bin.version = version;

    for (uint32_t i = 0; i < segment_count; ++i) {
        uint32_t addr;
        uint32_t size;

        file.read(reinterpret_cast<char*>(&addr), sizeof(addr));
        file.read(reinterpret_cast<char*>(&size), sizeof(size));

        Segment seg;
        seg.address = addr;
        seg.data.resize(size);

        file.read(reinterpret_cast<char*>(seg.data.data()), size);
        
        if (!file) {
            throw std::runtime_error("Error reading segment data from binary file");
        }

        bin.segments.push_back(std::move(seg));
    }

    return bin;
}
