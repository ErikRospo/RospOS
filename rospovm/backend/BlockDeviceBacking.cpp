#include "BlockDeviceBacking.h"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdint>
#include <fstream>
#include <stdexcept>
#include <string>
#include <vector>
#include <zlib.h>

namespace BlockDeviceBacking {

namespace {

constexpr uint32_t kBlockFlagCompressed = 1U << 0;

constexpr uint32_t kBlockDeviceMagic = 0x42534F52; // "ROSB"

constexpr uint32_t kRecordHeaderSize = 12;
constexpr uint32_t kHeaderSize = 20; // magic + version + block_count + index_offset(u64)

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

std::vector<uint8_t> compress_buffer(const std::vector<uint8_t> &input)
{
    z_stream stream{};
    const int initRc = deflateInit2(
        &stream,
        Z_BEST_SPEED,
        Z_DEFLATED,
        MAX_WBITS + 16,
        8,
        Z_DEFAULT_STRATEGY
    );
    if (initRc != Z_OK) {
        throw std::runtime_error("Failed to initialize gzip compressor");
    }

    std::vector<uint8_t> compressed(compressBound(static_cast<uLong>(input.size())));
    stream.next_in = const_cast<Bytef *>(reinterpret_cast<const Bytef *>(input.data()));
    stream.avail_in = static_cast<uInt>(input.size());
    stream.next_out = reinterpret_cast<Bytef *>(compressed.data());
    stream.avail_out = static_cast<uInt>(compressed.size());

    const int rc = deflate(&stream, Z_FINISH);
    if (rc != Z_STREAM_END) {
        deflateEnd(&stream);
        throw std::runtime_error("Failed to compress block payload");
    }

    const int endRc = deflateEnd(&stream);
    if (endRc != Z_OK) {
        throw std::runtime_error("Failed to finalize gzip compressor");
    }

    compressed.resize(static_cast<size_t>(stream.total_out));
    return compressed;
}

std::vector<uint8_t> decompress_buffer(const std::vector<uint8_t> &input)
{
    z_stream stream{};
    const int initRc = inflateInit2(&stream, MAX_WBITS + 16);
    if (initRc != Z_OK) {
        throw std::runtime_error("Failed to initialize gzip decompressor");
    }

    std::vector<uint8_t> output(kBlockSize);
    stream.next_in = const_cast<Bytef *>(reinterpret_cast<const Bytef *>(input.data()));
    stream.avail_in = static_cast<uInt>(input.size());
    stream.next_out = reinterpret_cast<Bytef *>(output.data());
    stream.avail_out = static_cast<uInt>(output.size());

    const int rc = inflate(&stream, Z_FINISH);
    const bool ok = (rc == Z_STREAM_END) && (stream.total_out == kBlockSize);
    if (!ok) {
        inflateEnd(&stream);
        throw std::runtime_error("Failed to decompress block payload");
    }

    const int endRc = inflateEnd(&stream);
    if (endRc != Z_OK) {
        throw std::runtime_error("Failed to finalize gzip decompressor");
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

} // namespace

void ensure_backing_file_exists(const std::string &path)
{
    std::ifstream in(path, std::ios::binary);
    if (!in.good()) {
        create_empty_backing_file(path);
    }
}

void rewrite_index_section(BlockDeviceState &state)
{
    const std::string tempPath = state.backingFilePath + ".tmp";

    std::fstream out(tempPath, std::ios::binary | std::ios::trunc | std::ios::in | std::ios::out);
    if (!out) {
        throw std::runtime_error("Failed to create compacted block-device file");
    }

    write_header(out, 0, kHeaderSize);

    std::vector<BlockIndexEntry> compactedIndex;
    compactedIndex.reserve(state.blockIndex.size());

    for (const BlockIndexEntry &entry : state.blockIndex) {
        const BlockRecordMeta meta = read_record_meta_at_offset(state, entry.recordOffset);
        const std::vector<uint8_t> payload = read_payload_for_block(state, meta);

        out.seekp(0, std::ios::end);
        if (!out) {
            throw std::runtime_error("Failed to seek while compacting block-device file");
        }

        const std::streampos recordStartPos = out.tellp();
        if (recordStartPos < 0) {
            throw std::runtime_error("Failed to determine compacted record offset");
        }
        const uint64_t recordOffset = static_cast<uint64_t>(recordStartPos);

        write_u32(out, entry.blockId);
        write_u32(out, meta.flags);
        write_u32(out, meta.storedSize);
        out.write(reinterpret_cast<const char *>(payload.data()), static_cast<std::streamsize>(payload.size()));
        if (!out) {
            throw std::runtime_error("Failed to write compacted block payload");
        }

        compactedIndex.push_back(BlockIndexEntry{entry.blockId, recordOffset});
    }

    out.seekp(0, std::ios::end);
    if (!out) {
        throw std::runtime_error("Failed to seek while writing compacted block index");
    }

    const std::streampos indexPos = out.tellp();
    if (indexPos < 0) {
        throw std::runtime_error("Failed to determine compacted block-index offset");
    }

    write_u32(out, static_cast<uint32_t>(compactedIndex.size()));
    for (const BlockIndexEntry &entry : compactedIndex) {
        write_u32(out, entry.blockId);
        write_u64(out, entry.recordOffset);
    }

    const uint64_t compactedIndexOffset = static_cast<uint64_t>(indexPos);
    const uint32_t compactedCount = static_cast<uint32_t>(compactedIndex.size());
    write_header(out, compactedCount, compactedIndexOffset);
    out.flush();
    if (!out) {
        throw std::runtime_error("Failed to flush compacted block-device file");
    }

    out.close();

    if (std::remove(state.backingFilePath.c_str()) != 0 && errno != ENOENT) {
        throw std::runtime_error("Failed to replace block-device file during compaction");
    }

    if (std::rename(tempPath.c_str(), state.backingFilePath.c_str()) != 0) {
        throw std::runtime_error("Failed to activate compacted block-device file");
    }

    state.blockIndex = std::move(compactedIndex);
    state.persistedBlockCount = compactedCount;
    state.indexOffset = compactedIndexOffset;
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

bool read_persisted_block(
    BlockDeviceState &state,
    uint32_t blockId,
    std::array<uint8_t, kBlockSize> &outBlock
)
{
    const auto it = find_block_index_entry(state, blockId);
    if (it == state.blockIndex.end() || it->blockId != blockId) {
        return false;
    }

    const BlockRecordMeta meta = read_record_meta_at_offset(state, it->recordOffset);
    const std::vector<uint8_t> payload = read_payload_for_block(state, meta);
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
        outBlock[i] = data[i];
    }

    return true;
}

void persist_block(
    BlockDeviceState &state,
    uint32_t blockId,
    const std::array<uint8_t, kBlockSize> &block,
    bool compactAfterWrite
)
{
    std::vector<uint8_t> raw(block.begin(), block.end());
    std::vector<uint8_t> compressed = compress_buffer(raw);

    uint32_t flags = 0;
    const std::vector<uint8_t> *payload = &raw;
    if (compressed.size() < raw.size()) {
        flags |= kBlockFlagCompressed;
        payload = &compressed;
    }

    std::ofstream out(state.backingFilePath, std::ios::binary | std::ios::app);
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

    upsert_block_index_entry(state, blockId, recordOffset);

    if (state.fileVersion != kBlockDeviceVersion) {
        throw std::runtime_error("Unsupported block-device file version for persistence");
    }

    if (compactAfterWrite) {
        rewrite_index_section(state);
    }
}

} // namespace BlockDeviceBacking
