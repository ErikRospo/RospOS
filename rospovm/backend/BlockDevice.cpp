#include "BlockDevice.h"

#include "Memory.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <fstream>
#include <mutex>
#include <random>
#include <stdexcept>
#include <string>
#include <unordered_map>
#include <vector>
#include <zlib.h>

namespace {

constexpr uint32_t kMmioBase = 0x40000000;
constexpr uint32_t kMmioSize = 0x100;

constexpr uint32_t kRegStatus = 0x00;
constexpr uint32_t kRegCommand = 0x04;
constexpr uint32_t kRegBlockId = 0x08;
constexpr uint32_t kRegBufferAddr = 0x0C;
constexpr uint32_t kRegBlockCount = 0x10;

constexpr uint32_t kStatusBusy = 1U << 0;
constexpr uint32_t kStatusError = 1U << 1;
constexpr uint32_t kStatusDataReady = 1U << 2;

constexpr uint32_t kCommandNone = 0x00;
constexpr uint32_t kCommandRead = 0x01;
constexpr uint32_t kCommandWrite = 0x02;

constexpr uint32_t kBlockFlagCompressed = 1U << 0;

constexpr uint32_t kSpecialTimeBlockId = 0xFFFFFFFDU;
constexpr uint32_t kSpecialRngBlockId = 0xFFFFFFFEU;
constexpr uint32_t kSpecialInfoBlockId = 0xFFFFFFFFU;

constexpr uint32_t kBlockDeviceMagic = 0x42534F52; // "ROSB"
constexpr uint32_t kBlockDeviceVersion = 1;

constexpr uint32_t kBlockSize = 512;
constexpr uint32_t kMaxCommandBlockCount = 128;
constexpr uint32_t kRecordHeaderSize = 12;

constexpr uint32_t kHeaderSize = 20; // magic + version + block_count + index_offset(u64)

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
    uint64_t indexOffset = kHeaderSize;
    std::vector<BlockIndexEntry> blockIndex; // Sorted by blockId

    std::mt19937 rng{std::random_device{}()};
    bool initialized = false;
};

BlockDeviceState g_state;
std::mutex g_mutex;

template <typename Stream>
uint32_t read_u32(Stream &stream)
{
    uint32_t value = 0;
    stream.read(reinterpret_cast<char *>(&value), sizeof(value));
    if (!stream) {
        throw std::runtime_error("Failed to read 32-bit value from block device file");
    }
    return value;
}

template <typename Stream>
uint64_t read_u64(Stream &stream)
{
    uint64_t value = 0;
    stream.read(reinterpret_cast<char *>(&value), sizeof(value));
    if (!stream) {
        throw std::runtime_error("Failed to read 64-bit value from block device file");
    }
    return value;
}

template <typename Stream>
void write_u32(Stream &stream, uint32_t value)
{
    stream.write(reinterpret_cast<const char *>(&value), sizeof(value));
    if (!stream) {
        throw std::runtime_error("Failed to write 32-bit value to block device file");
    }
}

template <typename Stream>
void write_u64(Stream &stream, uint64_t value)
{
    stream.write(reinterpret_cast<const char *>(&value), sizeof(value));
    if (!stream) {
        throw std::runtime_error("Failed to write 64-bit value to block device file");
    }
}

uint64_t get_file_size(std::ifstream &in)
{
    in.seekg(0, std::ios::end);
    if (!in) {
        throw std::runtime_error("Failed to seek to end of block device file");
    }
    const std::streampos endPos = in.tellg();
    if (endPos < 0) {
        throw std::runtime_error("Failed to determine block device file size");
    }
    in.seekg(0, std::ios::beg);
    if (!in) {
        throw std::runtime_error("Failed to seek to start of block device file");
    }
    return static_cast<uint64_t>(endPos);
}

void write_header(std::fstream &file, uint32_t blockCount, uint64_t indexOffset)
{
    file.seekp(0, std::ios::beg);
    if (!file) {
        throw std::runtime_error("Failed to seek while writing block-device header");
    }

    write_u32(file, kBlockDeviceMagic);
    write_u32(file, kBlockDeviceVersion);
    write_u32(file, blockCount);
    write_u64(file, indexOffset);
}

void create_empty_backing_file(const std::string &path)
{
    std::fstream out(path, std::ios::binary | std::ios::trunc | std::ios::in | std::ios::out);
    if (!out) {
        throw std::runtime_error("Failed to create block-device backing file: " + path);
    }

    write_header(out, 0, kHeaderSize);
    // Empty index section starts immediately after header.
    write_u32(out, 0);
}

void ensure_backing_file_exists(const std::string &path)
{
    std::ifstream in(path, std::ios::binary);
    if (!in.good()) {
        create_empty_backing_file(path);
    }
}

std::vector<uint8_t> compress_buffer(const std::vector<uint8_t> &input)
{
    uLongf compressedSize = compressBound(static_cast<uLong>(input.size()));
    std::vector<uint8_t> compressed(static_cast<size_t>(compressedSize));

    const int rc = compress2(
        compressed.data(),
        &compressedSize,
        input.data(),
        static_cast<uLong>(input.size()),
        Z_BEST_SPEED
    );
    if (rc != Z_OK) {
        throw std::runtime_error("Failed to compress block payload");
    }

    compressed.resize(static_cast<size_t>(compressedSize));
    return compressed;
}

std::vector<uint8_t> decompress_buffer(const std::vector<uint8_t> &input)
{
    std::vector<uint8_t> output(kBlockSize);
    uLongf outputSize = static_cast<uLongf>(output.size());
    const int rc = uncompress(
        output.data(),
        &outputSize,
        input.data(),
        static_cast<uLong>(input.size())
    );
    if (rc != Z_OK || outputSize != kBlockSize) {
        throw std::runtime_error("Failed to decompress block payload");
    }
    return output;
}

void ensure_sorted_unique_index(std::vector<BlockIndexEntry> &entries)
{
    std::sort(entries.begin(), entries.end(), [](const BlockIndexEntry &a, const BlockIndexEntry &b) {
        return a.blockId < b.blockId;
    });

    entries.erase(std::unique(entries.begin(), entries.end(), [](const BlockIndexEntry &a, const BlockIndexEntry &b) {
        return a.blockId == b.blockId;
    }), entries.end());
}

void rewrite_index_section(BlockDeviceState &state)
{
    std::fstream io(state.backingFilePath, std::ios::binary | std::ios::in | std::ios::out);
    if (!io) {
        throw std::runtime_error("Failed to open block-device file for index update");
    }

    io.seekp(0, std::ios::end);
    if (!io) {
        throw std::runtime_error("Failed to seek end while writing block index");
    }

    const std::streampos indexPos = io.tellp();
    if (indexPos < 0) {
        throw std::runtime_error("Failed to get block-index write position");
    }
    state.indexOffset = static_cast<uint64_t>(indexPos);

    write_u32(io, static_cast<uint32_t>(state.blockIndex.size()));
    for (const BlockIndexEntry &entry : state.blockIndex) {
        write_u32(io, entry.blockId);
        write_u64(io, entry.recordOffset);
    }

    state.persistedBlockCount = static_cast<uint32_t>(state.blockIndex.size());
    write_header(io, state.persistedBlockCount, state.indexOffset);
}

void load_index(BlockDeviceState &state, std::ifstream &in, uint32_t declaredCount)
{
    const uint64_t indexOffset = read_u64(in);
    const uint64_t fileSize = get_file_size(in);

    if (indexOffset >= fileSize) {
        throw std::runtime_error("Invalid block index offset");
    }

    in.seekg(static_cast<std::streamoff>(indexOffset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("Failed to seek to block index");
    }

    const uint32_t indexCount = read_u32(in);

    std::vector<BlockIndexEntry> entries;
    entries.reserve(indexCount);

    for (uint32_t i = 0; i < indexCount; ++i) {
        const uint32_t blockId = read_u32(in);
        const uint64_t recordOffset = read_u64(in);
        if (recordOffset + kRecordHeaderSize > fileSize) {
            throw std::runtime_error("Invalid record offset in block index");
        }
        entries.push_back(BlockIndexEntry{blockId, recordOffset});
    }

    const size_t sizeBeforeNormalize = entries.size();
    ensure_sorted_unique_index(entries);

    state.blockIndex = std::move(entries);
    state.persistedBlockCount = static_cast<uint32_t>(state.blockIndex.size());
    state.indexOffset = indexOffset;

    if (declaredCount != state.persistedBlockCount || sizeBeforeNormalize != state.blockIndex.size()) {
        rewrite_index_section(state);
    }
}

void load_index_from_file(BlockDeviceState &state)
{
    std::ifstream in(state.backingFilePath, std::ios::binary);
    if (!in) {
        throw std::runtime_error("Failed to open block-device file: " + state.backingFilePath);
    }

    const uint32_t magic = read_u32(in);
    const uint32_t version = read_u32(in);
    const uint32_t declaredCount = read_u32(in);

    if (magic != kBlockDeviceMagic) {
        throw std::runtime_error("Invalid block-device file magic (expected ROSB)");
    }

    state.fileVersion = version;

    if (version == kBlockDeviceVersion) {
        load_index(state, in, declaredCount);
        return;
    }

    throw std::runtime_error("Unsupported block-device file version: " + std::to_string(version));
}

uint8_t read_reg_byte(uint32_t regValue, uint32_t byteIndex)
{
    if (byteIndex > 3) {
        throw std::runtime_error("Invalid MMIO register byte index");
    }
    const uint32_t shift = (3U - byteIndex) * 8U;
    return static_cast<uint8_t>((regValue >> shift) & 0xFFU);
}

void write_reg_byte(uint32_t &regValue, uint32_t byteIndex, uint8_t byte)
{
    if (byteIndex > 3) {
        throw std::runtime_error("Invalid MMIO register byte index");
    }
    const uint32_t shift = (3U - byteIndex) * 8U;
    regValue &= ~(0xFFU << shift);
    regValue |= static_cast<uint32_t>(byte) << shift;
}

std::vector<BlockIndexEntry>::const_iterator find_block_index_entry(const BlockDeviceState &state, uint32_t blockId)
{
    return std::lower_bound(
        state.blockIndex.begin(),
        state.blockIndex.end(),
        blockId,
        [](const BlockIndexEntry &entry, uint32_t id) {
            return entry.blockId < id;
        }
    );
}

BlockRecordMeta read_record_meta_at_offset(const BlockDeviceState &state, uint64_t recordOffset)
{
    std::ifstream in(state.backingFilePath, std::ios::binary);
    if (!in) {
        throw std::runtime_error("Failed to open block-device file for record read");
    }

    in.seekg(static_cast<std::streamoff>(recordOffset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("Failed to seek to block record");
    }

    const uint32_t ignoredBlockId = read_u32(in);
    (void)ignoredBlockId;

    const uint32_t flags = read_u32(in);
    const uint32_t storedSize = read_u32(in);
    if (storedSize == 0) {
        throw std::runtime_error("Corrupt block record payload size");
    }

    return BlockRecordMeta{
        flags,
        storedSize,
        recordOffset + kRecordHeaderSize
    };
}

std::vector<uint8_t> read_payload_for_block(const BlockDeviceState &state, const BlockRecordMeta &meta)
{
    std::ifstream in(state.backingFilePath, std::ios::binary);
    if (!in) {
        throw std::runtime_error("Failed to open block-device file for payload read");
    }

    in.seekg(static_cast<std::streamoff>(meta.payloadOffset), std::ios::beg);
    if (!in) {
        throw std::runtime_error("Failed to seek to block payload");
    }

    std::vector<uint8_t> payload(meta.storedSize);
    in.read(reinterpret_cast<char *>(payload.data()), static_cast<std::streamsize>(payload.size()));
    if (!in) {
        throw std::runtime_error("Failed to read block payload");
    }
    return payload;
}

std::array<uint8_t, kBlockSize> read_block(uint32_t blockId)
{
    std::array<uint8_t, kBlockSize> block{};

    if (blockId == kSpecialTimeBlockId) {
        const auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        const uint64_t stamp = static_cast<uint64_t>(nowMs);
        for (size_t i = 0; i < sizeof(stamp); ++i) {
            block[i] = static_cast<uint8_t>((stamp >> (i * 8U)) & 0xFFU);
        }
        return block;
    }

    if (blockId == kSpecialRngBlockId) {
        std::uniform_int_distribution<uint32_t> dist(0, 0xFFFFFFFFU);
        for (uint32_t i = 0; i < kBlockSize; i += 4) {
            const uint32_t value = dist(g_state.rng);
            block[i + 0] = static_cast<uint8_t>(value & 0xFFU);
            block[i + 1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
            block[i + 2] = static_cast<uint8_t>((value >> 16U) & 0xFFU);
            block[i + 3] = static_cast<uint8_t>((value >> 24U) & 0xFFU);
        }
        return block;
    }

    if (blockId == kSpecialInfoBlockId) {
        const char *tag = "ROSPOS-BLOCK-DEVICE";
        for (size_t i = 0; tag[i] != '\0' && i < block.size(); ++i) {
            block[i] = static_cast<uint8_t>(tag[i]);
        }
        const uint32_t persisted = g_state.persistedBlockCount;
        block[32] = static_cast<uint8_t>(persisted & 0xFFU);
        block[33] = static_cast<uint8_t>((persisted >> 8U) & 0xFFU);
        block[34] = static_cast<uint8_t>((persisted >> 16U) & 0xFFU);
        block[35] = static_cast<uint8_t>((persisted >> 24U) & 0xFFU);
        return block;
    }

    const auto it = find_block_index_entry(g_state, blockId);
    if (it == g_state.blockIndex.end() || it->blockId != blockId) {
        return block;
    }

    const BlockRecordMeta meta = read_record_meta_at_offset(g_state, it->recordOffset);
    const std::vector<uint8_t> payload = read_payload_for_block(g_state, meta);
    std::vector<uint8_t> data;

    if ((meta.flags & kBlockFlagCompressed) != 0U) {
        data = decompress_buffer(payload);
    } else {
        if (payload.size() != kBlockSize) {
            throw std::runtime_error("Uncompressed block payload has invalid size");
        }
        data = payload;
    }

    for (uint32_t i = 0; i < kBlockSize; ++i) {
        block[i] = data[i];
    }

    return block;
}

void upsert_block_index_entry(BlockDeviceState &state, uint32_t blockId, uint64_t recordOffset)
{
    const auto it = std::lower_bound(
        state.blockIndex.begin(),
        state.blockIndex.end(),
        blockId,
        [](const BlockIndexEntry &entry, uint32_t id) {
            return entry.blockId < id;
        }
    );

    if (it != state.blockIndex.end() && it->blockId == blockId) {
        const size_t idx = static_cast<size_t>(std::distance(state.blockIndex.begin(), it));
        state.blockIndex[idx].recordOffset = recordOffset;
    } else {
        state.blockIndex.insert(it, BlockIndexEntry{blockId, recordOffset});
    }

    state.persistedBlockCount = static_cast<uint32_t>(state.blockIndex.size());
}

void persist_block(uint32_t blockId, const std::array<uint8_t, kBlockSize> &block)
{
    std::vector<uint8_t> raw(block.begin(), block.end());
    std::vector<uint8_t> compressed = compress_buffer(raw);

    uint32_t flags = 0;
    const std::vector<uint8_t> *payload = &raw;
    if (compressed.size() < raw.size()) {
        flags |= kBlockFlagCompressed;
        payload = &compressed;
    }

    std::ofstream out(g_state.backingFilePath, std::ios::binary | std::ios::app);
    if (!out) {
        throw std::runtime_error("Failed to open block-device file for append");
    }

    out.seekp(0, std::ios::end);
    if (!out) {
        throw std::runtime_error("Failed to seek block-device file end");
    }
    const std::streampos recordStartPos = out.tellp();
    if (recordStartPos < 0) {
        throw std::runtime_error("Failed to get block-device file append position");
    }
    const uint64_t recordOffset = static_cast<uint64_t>(recordStartPos);

    const uint32_t storedSize = static_cast<uint32_t>(payload->size());
    write_u32(out, blockId);
    write_u32(out, flags);
    write_u32(out, storedSize);
    out.write(reinterpret_cast<const char *>(payload->data()), static_cast<std::streamsize>(payload->size()));
    if (!out) {
        throw std::runtime_error("Failed to write block payload");
    }
    out.flush();

    upsert_block_index_entry(g_state, blockId, recordOffset);

    if (g_state.fileVersion == kBlockDeviceVersion) {
        rewrite_index_section(g_state);
    } else {
        throw std::runtime_error("Unsupported block-device file version for persistence");
    }
}

void set_error(bool set)
{
    if (set) {
        g_state.status |= kStatusError;
    } else {
        g_state.status &= ~kStatusError;
    }
}

void set_data_ready(bool set)
{
    if (set) {
        g_state.status |= kStatusDataReady;
    } else {
        g_state.status &= ~kStatusDataReady;
    }
}

bool is_special_read_only(uint32_t blockId)
{
    return blockId == kSpecialTimeBlockId ||
           blockId == kSpecialRngBlockId ||
           blockId == kSpecialInfoBlockId;
}

void execute_read_command()
{
    if (g_state.blockCount == 0 || g_state.blockCount > kMaxCommandBlockCount) {
        throw std::runtime_error("Invalid block count for READ command");
    }
    if ((g_state.bufferAddr % kBlockSize) != 0U) {
        throw std::runtime_error("Buffer address must be 512-byte aligned");
    }

    for (uint32_t i = 0; i < g_state.blockCount; ++i) {
        const uint32_t id = g_state.blockId + i;
        const uint32_t baseAddr = g_state.bufferAddr + (i * kBlockSize);
        const std::array<uint8_t, kBlockSize> block = read_block(id);
        for (uint32_t j = 0; j < kBlockSize; ++j) {
            g_state.memory->writeByte(baseAddr + j, block[j]);
        }
    }

    set_data_ready(true);
}

void execute_write_command()
{
    if (g_state.blockCount == 0 || g_state.blockCount > kMaxCommandBlockCount) {
        throw std::runtime_error("Invalid block count for WRITE command");
    }
    if ((g_state.bufferAddr % kBlockSize) != 0U) {
        throw std::runtime_error("Buffer address must be 512-byte aligned");
    }

    for (uint32_t i = 0; i < g_state.blockCount; ++i) {
        const uint32_t id = g_state.blockId + i;
        if (is_special_read_only(id)) {
            throw std::runtime_error("Attempted write to read-only special block");
        }

        const uint32_t baseAddr = g_state.bufferAddr + (i * kBlockSize);
        std::array<uint8_t, kBlockSize> block{};
        for (uint32_t j = 0; j < kBlockSize; ++j) {
            block[j] = g_state.memory->readByte(baseAddr + j);
        }
        persist_block(id, block);
    }

    set_data_ready(false);
}

void run_command_if_needed(uint32_t wroteOffset)
{
    // Trigger command execution when the command register's least significant byte is written.
    if (wroteOffset != (kRegCommand + 3)) {
        return;
    }

    if (!g_state.initialized) {
        throw std::runtime_error("Block device not initialized");
    }

    const uint32_t cmd = g_state.command;
    if (cmd == kCommandNone) {
        return;
    }

    g_state.status |= kStatusBusy;
    set_error(false);

    try {
        if (cmd == kCommandRead) {
            execute_read_command();
        } else if (cmd == kCommandWrite) {
            execute_write_command();
        } else {
            throw std::runtime_error("Unknown block-device command");
        }
    } catch (...) {
        set_error(true);
        g_state.status &= ~kStatusBusy;
        g_state.command = kCommandNone;
        throw;
    }

    g_state.status &= ~kStatusBusy;
    g_state.command = kCommandNone;
}

uint32_t *reg_for_offset(uint32_t offset)
{
    if (offset >= kRegStatus && offset <= (kRegStatus + 3)) {
        return &g_state.status;
    }
    if (offset >= kRegCommand && offset <= (kRegCommand + 3)) {
        return &g_state.command;
    }
    if (offset >= kRegBlockId && offset <= (kRegBlockId + 3)) {
        return &g_state.blockId;
    }
    if (offset >= kRegBufferAddr && offset <= (kRegBufferAddr + 3)) {
        return &g_state.bufferAddr;
    }
    if (offset >= kRegBlockCount && offset <= (kRegBlockCount + 3)) {
        return &g_state.blockCount;
    }
    return nullptr;
}

} // namespace

void BlockDeviceInitialize(Memory *memory, const std::string &backingFilePath)
{
    if (memory == nullptr) {
        throw std::runtime_error("Block device requires a valid memory instance");
    }

    std::lock_guard<std::mutex> lock(g_mutex);

    g_state.memory = memory;
    g_state.backingFilePath = backingFilePath;
    g_state.status = 0;
    g_state.command = 0;
    g_state.blockId = 0;
    g_state.bufferAddr = 0;
    g_state.blockCount = 1;
    g_state.fileVersion = kBlockDeviceVersion;
    g_state.persistedBlockCount = 0;
    g_state.indexOffset = kHeaderSize;
    g_state.blockIndex.clear();

    ensure_backing_file_exists(g_state.backingFilePath);
    load_index_from_file(g_state);

    g_state.initialized = true;
}

void BlockDeviceShutdown()
{
    std::lock_guard<std::mutex> lock(g_mutex);
    g_state = BlockDeviceState{};
}

uint8_t BlockDeviceReadHandler(uint32_t address)
{
    std::lock_guard<std::mutex> lock(g_mutex);

    if (address < kMmioBase || address >= (kMmioBase + kMmioSize)) {
        throw std::runtime_error("BlockDeviceReadHandler: address out of range");
    }

    const uint32_t offset = address - kMmioBase;
    uint32_t *regPtr = reg_for_offset(offset);
    if (regPtr == nullptr) {
        return 0;
    }

    const uint32_t byteIndex = offset & 0x3U;
    return read_reg_byte(*regPtr, byteIndex);
}

void BlockDeviceWriteHandler(uint32_t address, uint8_t value)
{
    std::lock_guard<std::mutex> lock(g_mutex);

    if (address < kMmioBase || address >= (kMmioBase + kMmioSize)) {
        throw std::runtime_error("BlockDeviceWriteHandler: address out of range");
    }

    const uint32_t offset = address - kMmioBase;
    uint32_t *regPtr = reg_for_offset(offset);
    if (regPtr == nullptr) {
        return;
    }

    const uint32_t byteIndex = offset & 0x3U;
    write_reg_byte(*regPtr, byteIndex, value);

    if (regPtr == &g_state.status) {
        // Busy bit is controlled by the device.
        g_state.status &= ~kStatusBusy;
        return;
    }

    run_command_if_needed(offset);
}
