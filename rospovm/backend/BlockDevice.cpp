#include "BlockDevice.h"

#include "BlockDeviceBacking.h"
#include "Memory.h"

#include <array>
#include <chrono>
#include <cstdint>
#include <mutex>
#include <random>
#include <stdexcept>
#include <string>
#include <iostream>

namespace {

using BlockDeviceBacking::BlockDeviceState;

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

constexpr uint32_t kSpecialTimeBlockId = 0xFFFFFFFDU;
constexpr uint32_t kSpecialRngBlockId = 0xFFFFFFFEU;
constexpr uint32_t kSpecialInfoBlockId = 0xFFFFFFFFU;

constexpr uint32_t kMaxCommandBlockCount = 128;
constexpr uint64_t kHeaderSize = 20;

BlockDeviceState g_state;
std::mutex g_mutex;

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

bool try_read_special_block(uint32_t blockId, std::array<uint8_t, BlockDeviceBacking::kBlockSize> &block)
{
    if (blockId == kSpecialTimeBlockId) {
        const auto nowMs = std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::system_clock::now().time_since_epoch()
        ).count();
        const uint64_t stamp = static_cast<uint64_t>(nowMs);
        for (size_t i = 0; i < sizeof(stamp); ++i) {
            block[i] = static_cast<uint8_t>((stamp >> (i * 8U)) & 0xFFU);
        }
        return true;
    }

    if (blockId == kSpecialRngBlockId) {
        std::uniform_int_distribution<uint32_t> dist(0, 0xFFFFFFFFU);
        for (uint32_t i = 0; i < BlockDeviceBacking::kBlockSize; i += 4) {
            const uint32_t value = dist(g_state.rng);
            block[i + 0] = static_cast<uint8_t>(value & 0xFFU);
            block[i + 1] = static_cast<uint8_t>((value >> 8U) & 0xFFU);
            block[i + 2] = static_cast<uint8_t>((value >> 16U) & 0xFFU);
            block[i + 3] = static_cast<uint8_t>((value >> 24U) & 0xFFU);
        }
        return true;
    }

    if (blockId == kSpecialInfoBlockId) {
        const char *tag = "ROSPOS-BLOCK-DEVICE";
        for (size_t i = 0; tag[i] != '\0' && i < block.size(); ++i) {
            block[i] = static_cast<uint8_t>(tag[i]);
        }
        block[block.size() - 1] = 0;
        const uint32_t persisted = g_state.persistedBlockCount;
        block[32] = static_cast<uint8_t>(persisted & 0xFFU);
        block[33] = static_cast<uint8_t>((persisted >> 8U) & 0xFFU);
        block[34] = static_cast<uint8_t>((persisted >> 16U) & 0xFFU);
        block[35] = static_cast<uint8_t>((persisted >> 24U) & 0xFFU);
        return true;
    }

    return false;
}

std::array<uint8_t, BlockDeviceBacking::kBlockSize> read_block(uint32_t blockId)
{
    std::array<uint8_t, BlockDeviceBacking::kBlockSize> block{};
    if (try_read_special_block(blockId, block)) {
        return block;
    }

    (void)BlockDeviceBacking::read_persisted_block(g_state, blockId, block);
    return block;
}

void execute_read_command()
{
    if (g_state.blockCount == 0 || g_state.blockCount > kMaxCommandBlockCount) {
        throw std::runtime_error("Invalid block count for READ command");
    }

    for (uint32_t i = 0; i < g_state.blockCount; ++i) {
        const uint32_t id = g_state.blockId + i;
        const uint32_t baseAddr = g_state.bufferAddr + (i * BlockDeviceBacking::kBlockSize);
        const auto block = read_block(id);
        for (uint32_t j = 0; j < BlockDeviceBacking::kBlockSize; ++j) {
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

    for (uint32_t i = 0; i < g_state.blockCount; ++i) {
        const uint32_t id = g_state.blockId + i;
        if (is_special_read_only(id)) {
            throw std::runtime_error("Attempted write to read-only special block");
        }

        const uint32_t baseAddr = g_state.bufferAddr + (i * BlockDeviceBacking::kBlockSize);
        std::array<uint8_t, BlockDeviceBacking::kBlockSize> block{};
        for (uint32_t j = 0; j < BlockDeviceBacking::kBlockSize; ++j) {
            block[j] = g_state.memory->readByte(baseAddr + j);
        }
        BlockDeviceBacking::persist_block(g_state, id, block, false);
    }

    if (g_state.fileVersion == BlockDeviceBacking::kBlockDeviceVersion) {
        BlockDeviceBacking::rewrite_index_section(g_state);
    } else {
        throw std::runtime_error("Unsupported block-device file version for persistence");
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
        set_data_ready(false);
        g_state.status &= ~kStatusBusy;
        g_state.command = kCommandNone;
        return;
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
    g_state.fileVersion = BlockDeviceBacking::kBlockDeviceVersion;
    g_state.persistedBlockCount = 0;
    g_state.indexOffset = kHeaderSize;
    g_state.blockIndex.clear();

    BlockDeviceBacking::ensure_backing_file_exists(g_state.backingFilePath);
    BlockDeviceBacking::load_index_from_file(g_state);

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
