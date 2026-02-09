#include <fstream>
#include <vector>
#include <cstdint>
#include <stdexcept>
#include <iostream>
#include "Binary.h"

Binary Binary::load_binary(const std::string &path)
{
    std::ifstream f(path, std::ios::binary);
    if (!f)
    {
        throw std::runtime_error("Failed to open file");
    }

    uint32_t magic;
    uint32_t version;
    uint32_t segment_count;

    f.read(reinterpret_cast<char *>(&magic), sizeof(magic));
    f.read(reinterpret_cast<char *>(&version), sizeof(version));
    f.read(reinterpret_cast<char *>(&segment_count), sizeof(segment_count));

    if (magic != 0x50534F52)
    { // "ROSP"
        throw std::runtime_error("Invalid magic");
    }
    std::cout << "Loading binary version " << version << " with " << segment_count << " segments." << std::endl;

    Binary bin;
    bin.version = version;

    for (uint32_t i = 0; i < segment_count; ++i)
    {
        uint32_t addr;
        uint32_t size;

        f.read(reinterpret_cast<char *>(&addr), sizeof(addr));
        f.read(reinterpret_cast<char *>(&size), sizeof(size));

        Segment seg;
        seg.address = addr;
        seg.data.resize(size);

        f.read(reinterpret_cast<char *>(seg.data.data()), size);

        bin.segments.push_back(std::move(seg));
    }

    return bin;
}
