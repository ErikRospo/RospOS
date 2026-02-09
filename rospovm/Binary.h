#ifndef BINARY_H
#define BINARY_H

#include <string>
#include <vector>
#include <cstdint>

struct Segment
{
    uint32_t address;
    std::vector<uint8_t> data;
};
struct Binary
{
    uint32_t version;
    std::vector<Segment> segments;
    Binary load_binary(const std::string &path);
};

#endif // BINARY_H