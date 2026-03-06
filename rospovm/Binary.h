#ifndef BINARY_H
#define BINARY_H

#include <string>
#include <vector>
#include <cstdint>
#include <map>
#include <memory>

// Segment flags for Binary format V2.
constexpr uint32_t SEGMENT_FLAG_LOADABLE = 0x00000001;
constexpr uint32_t SEGMENT_FLAG_DEBUG = 0x00000002;

struct Segment
{
    uint32_t address;
    std::vector<uint8_t> data;
};

struct DebugEntry
{
    uint32_t address;
    uint32_t flags;
    uint32_t file_id;
    uint32_t line;
    std::string original_text;
};

struct DebugInfo
{
    uint32_t version;
    uint32_t segment_address;
    std::vector<DebugEntry> entries;
    std::map<uint32_t, std::string> file_table;
};

struct SegmentV2
{
    uint32_t flags;
    uint32_t address;
    std::vector<uint8_t> data;
    std::shared_ptr<DebugInfo> debug_info;
};

struct BinaryV2
{
    uint32_t version;
    std::vector<SegmentV2> segments;
    std::map<uint32_t, DebugInfo> debug_map;
};

struct Binary
{
    uint32_t version;
    std::vector<Segment> segments;
    Binary load_binary(const std::string &path);
};

#endif // BINARY_H