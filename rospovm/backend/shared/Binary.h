#ifndef BINARY_H
#define BINARY_H

#include <string>
#include <vector>
#include <cstdint>
#include <map>
#include <memory>

// Compile-time flag to enable/disable parsing debug segments when loading binaries.
// Set to 1 for debug-capable builds, 0 for release-oriented builds.
#ifndef ROSPOSVM_ENABLE_DEBUG_INFO
#define ROSPOSVM_ENABLE_DEBUG_INFO 1
#endif

// Segment flags for Binary format V2.
constexpr uint32_t SEGMENT_FLAG_LOADABLE = 0x00000001;
constexpr uint32_t SEGMENT_FLAG_DEBUG = 0x00000002;
constexpr uint32_t SEGMENT_FLAG_COMPRESSED = 0x00000004;

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

struct RegisterAllocationInfo
{
    std::string reg;
    std::string variable_name;
    std::string variable_type;
    std::string var_kind;
    std::string origin;
};

struct DebugInfo
{
    uint32_t version;
    uint32_t segment_address;
    std::vector<DebugEntry> entries;
    std::map<uint32_t, std::string> file_table;
    std::map<uint32_t, std::vector<RegisterAllocationInfo>> register_allocations;
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
    std::map<uint32_t, std::shared_ptr<DebugInfo>> debug_map;  // Maps segment address to debug info
    Binary load_binary(const std::string &path);
    
    /**
     * Get debug info for a specific memory address.
     * Returns the debug entry if found, nullptr otherwise.
     */
    const DebugEntry* get_debug_entry(uint32_t address) const;
};

#endif // BINARY_H