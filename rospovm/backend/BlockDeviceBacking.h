#ifndef BLOCK_DEVICE_BACKING_H
#define BLOCK_DEVICE_BACKING_H

#include <array>
#include <cstdint>
#include <mutex>
#include <random>
#include <string>
#include <vector>

class Memory;

namespace BlockDeviceBacking {

inline constexpr uint32_t kBlockDeviceVersion = 1;
inline constexpr uint32_t kBlockSize = 512;

struct BlockRecordMeta {
    uint32_t flags = 0;
    uint32_t storedSize = 0;
    uint64_t payloadOffset = 0;
};

struct BlockIndexEntry {
    uint32_t blockId = 0;
    uint64_t recordOffset = 0;
};

struct BlockDeviceState {
    Memory *memory = nullptr;
    std::string backingFilePath;

    uint32_t status = 0;
    uint32_t command = 0;
    uint32_t blockId = 0;
    uint32_t bufferAddr = 0;
    uint32_t blockCount = 1;

    uint32_t fileVersion = kBlockDeviceVersion;
    uint32_t persistedBlockCount = 0;
    uint64_t indexOffset = 0;
    std::vector<BlockIndexEntry> blockIndex;

    std::mt19937 rng{std::random_device{}()};
    bool initialized = false;
};

void ensure_backing_file_exists(const std::string &path);
void load_index_from_file(BlockDeviceState &state);
void rewrite_index_section(BlockDeviceState &state);

bool read_persisted_block(
    BlockDeviceState &state,
    uint32_t blockId,
    std::array<uint8_t, kBlockSize> &outBlock
);
void persist_block(
    BlockDeviceState &state,
    uint32_t blockId,
    const std::array<uint8_t, kBlockSize> &block,
    bool compactAfterWrite
);

} // namespace BlockDeviceBacking

#endif // BLOCK_DEVICE_BACKING_H
