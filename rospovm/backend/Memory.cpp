#include "Memory.h"

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>
#include <fstream>
#include <iostream>
#include <sstream>

Memory::Memory(uint64_t size)
{
#if ROSPOSVM_SPARSE_MEMORY
    if (size > (1ULL << 32)) {
        throw std::out_of_range("Memory exceeds the VM address space.");
    }
    totalSize = size;
    pages.resize(static_cast<size_t>((size + kPageSize - 1) / kPageSize));
#else
    mem.resize(static_cast<size_t>(size), 0);
#endif

    specialRanges.clear();
    lastSpecialRangeIndex = -1;
}

#if ROSPOSVM_SPARSE_MEMORY
uint8_t *Memory::ensurePage(uint32_t page)
{
    auto &data = pages[page];
    if (!data) {
        data = std::make_unique<uint8_t[]>(kPageSize);
    }
    return data.get();
}
#endif

void Memory::addSpecialRange(const char* name, uint32_t start, uint32_t end, SpecialMemoryRange::Type type, bool readable, bool writable,
                             ReadHandler readHandler,
                             WriteHandler writeHandler)
{
    SpecialMemoryRange range{start, end, type, {}, readable, writable, readHandler, writeHandler};
    if (name) {
        range.name[0] = name[0];
        range.name[1] = name[1];
        range.name[2] = name[2];
        range.name[3] = name[3];
    }
    specialRanges.push_back(range);
    lastSpecialRangeIndex = -1;
}

const SpecialMemoryRange* Memory::findSpecialRange(uint32_t address) const
{
    if (lastSpecialRangeIndex >= 0)
    {
        const size_t cachedIndex = static_cast<size_t>(lastSpecialRangeIndex);
        if (cachedIndex < specialRanges.size())
        {
            const auto &cachedRange = specialRanges[cachedIndex];
            if (cachedRange.contains(address))
            {
                return &cachedRange;
            }
        }
    }

    for (size_t i = 0; i < specialRanges.size(); ++i)
    {
        const auto &range = specialRanges[i];
        if (range.contains(address))
        {
            lastSpecialRangeIndex = static_cast<int>(i);
            return &range;
        }
    }

    lastSpecialRangeIndex = -1;
    return nullptr;
}

const SpecialMemoryRange* Memory::findOverlappingSpecialRange(uint32_t startAddress, uint32_t endAddress) const
{
    if (startAddress > endAddress)
    {
        return nullptr;
    }

    if (lastSpecialRangeIndex >= 0)
    {
        const size_t cachedIndex = static_cast<size_t>(lastSpecialRangeIndex);
        if (cachedIndex < specialRanges.size())
        {
            const auto &cachedRange = specialRanges[cachedIndex];
            if (cachedRange.startAddress <= endAddress && cachedRange.endAddress >= startAddress)
            {
                return &cachedRange;
            }
        }
    }

    for (size_t i = 0; i < specialRanges.size(); ++i)
    {
        const auto &range = specialRanges[i];
        if (range.startAddress <= endAddress && range.endAddress >= startAddress)
        {
            lastSpecialRangeIndex = static_cast<int>(i);
            return &range;
        }
    }

    lastSpecialRangeIndex = -1;
    return nullptr;
}

uint32_t Memory::readWordDirectRam(uint32_t address) const
{
#if ROSPOSVM_SPARSE_MEMORY
    const uint32_t start = address;
    if (static_cast<uint64_t>(start) + 3 >= totalSize) {
        throw std::out_of_range("Memory read out of bounds.");
    }

    const uint32_t offset = start % kPageSize;
    if (offset <= kPageSize - 4) {
        const uint8_t *data = pages[start / kPageSize].get();
        if (!data) return 0;
        return (static_cast<uint32_t>(data[offset]) << 24) |
               (static_cast<uint32_t>(data[offset + 1]) << 16) |
               (static_cast<uint32_t>(data[offset + 2]) << 8) |
               static_cast<uint32_t>(data[offset + 3]);
    }

    // Unaligned words can straddle two pages.
    uint32_t result = 0;
    for (uint32_t i = 0; i < 4; ++i) {
        uint32_t a = start + i;
        uint32_t page = a / kPageSize;
        uint32_t off = a % kPageSize;
        const auto &data = pages[page];
        const uint8_t b = data ? data[off] : 0;
        result = (result << 8) | static_cast<uint32_t>(b);
    }
    return result;
#else
    const size_t start = static_cast<size_t>(address);
    if (start + 3 >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }

    return (static_cast<uint32_t>(mem[start]) << 24) |
           (static_cast<uint32_t>(mem[start + 1]) << 16) |
           (static_cast<uint32_t>(mem[start + 2]) << 8) |
           static_cast<uint32_t>(mem[start + 3]);
#endif
}

void Memory::writeWordDirectRam(uint32_t address, uint32_t value)
{
#if ROSPOSVM_SPARSE_MEMORY
    const uint32_t start = address;
    if (static_cast<uint64_t>(start) + 3 >= totalSize) {
        throw std::out_of_range("Memory write out of bounds.");
    }

    const uint32_t offset = start % kPageSize;
    if (offset <= kPageSize - 4) {
        uint8_t *data = ensurePage(start / kPageSize);
        data[offset] = static_cast<uint8_t>(value >> 24);
        data[offset + 1] = static_cast<uint8_t>(value >> 16);
        data[offset + 2] = static_cast<uint8_t>(value >> 8);
        data[offset + 3] = static_cast<uint8_t>(value);
        return;
    }

    for (int i = 0; i < 4; ++i) {
        uint32_t a = start + i;
        uint32_t page = a / kPageSize;
        uint32_t off = a % kPageSize;
        ensurePage(page)[off] = static_cast<uint8_t>((value >> ((3 - i) * 8)) & 0xFF);
    }
#else
    const size_t start = static_cast<size_t>(address);
    if (start + 3 >= mem.size()) {
        throw std::out_of_range("Memory write out of bounds.");
    }

    mem[start] = static_cast<uint8_t>((value >> 24) & 0xFF);
    mem[start + 1] = static_cast<uint8_t>((value >> 16) & 0xFF);
    mem[start + 2] = static_cast<uint8_t>((value >> 8) & 0xFF);
    mem[start + 3] = static_cast<uint8_t>(value & 0xFF);
#endif
}

uint8_t Memory::readByte(uint32_t address) const
{
    const SpecialMemoryRange *range = findSpecialRange(address);
    if (range)
    {
        if (range->readable && range->readHandler)
        {
            return range->readHandler(address);
        }
        else
        {
            throw std::runtime_error("Attempted to read from non-readable special memory range \"" + std::string(range->name) + "\".");
        }
    }

#if ROSPOSVM_SPARSE_MEMORY
    if (static_cast<size_t>(address) >= totalSize) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    uint32_t page = address / kPageSize;
    uint32_t off = address % kPageSize;
    const auto &data = pages[page];
    return data ? data[off] : 0;
#else
    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    return mem[address];
#endif
}

uint8_t Memory::readByteForInspector(uint32_t address) const
{
    const SpecialMemoryRange *range = findSpecialRange(address);
    if (range)
    {
        if (range->name[0] == 'T' && range->name[1] == 'T' &&
            range->name[2] == 'Y' && range->name[3] == ' ')
        {
            return 0;
        }

        if (range->readable && range->readHandler)
        {
            return range->readHandler(address);
        }

        throw std::runtime_error("Attempted to read from non-readable special memory range \"" + std::string(range->name, 4) + "\".");
    }

#if ROSPOSVM_SPARSE_MEMORY
    if (static_cast<size_t>(address) >= totalSize) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    uint32_t page = address / kPageSize;
    uint32_t off = address % kPageSize;
    const auto &data = pages[page];
    return data ? data[off] : 0;
#else
    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    return mem[address];
#endif
}

void Memory::writeByte(uint32_t address, uint8_t value)
{
    const SpecialMemoryRange *range = findSpecialRange(address);
    if (range)
    {
        if (range->writable && range->writeHandler)
        {
            range->writeHandler(address, value);
            return;
        }
        else
        {
            throw std::runtime_error("Attempted to write to non-writable special memory range \"" + std::string(range->name) + "\".");
        }
    }

#if ROSPOSVM_SPARSE_MEMORY
    if (static_cast<size_t>(address) >= totalSize) {
        throw std::out_of_range("Memory write out of bounds.");
    }
    uint32_t page = address / kPageSize;
    uint32_t off = address % kPageSize;
    ensurePage(page)[off] = value;
#else
    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory write out of bounds.");
    }
    mem[address] = value;
#endif
}

uint16_t Memory::readHalf(uint32_t address) const
{
    if (address == UINT32_MAX) {
        throw std::out_of_range("Memory half-word read out of bounds.");
    }
    // MMIO reads may consume input; sequence them in address order.
    const uint16_t high = readByte(address);
    const uint16_t low = readByte(address + 1);
    return static_cast<uint16_t>((high << 8) | low);
}
void Memory::writeHalf(uint32_t address, uint16_t value)
{
    if (address == UINT32_MAX) {
        throw std::out_of_range("Memory half-word write out of bounds.");
    }
    writeByte(address, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeByte(address + 1, static_cast<uint8_t>(value & 0xFF));
}
uint32_t Memory::readWord(uint32_t address) const
{
    if (address > UINT32_MAX - 3) {
        throw std::out_of_range("Memory word read out of bounds.");
    }
    const uint32_t endAddress = address + 3;
    if (!findOverlappingSpecialRange(address, endAddress)) {
        return readWordDirectRam(address);
    }

    const uint32_t b0 = readByte(address);
    const uint32_t b1 = readByte(address + 1);
    const uint32_t b2 = readByte(address + 2);
    const uint32_t b3 = readByte(address + 3);
    return (b0 << 24) | (b1 << 16) | (b2 << 8) | b3;
}
void Memory::writeWord(uint32_t address, uint32_t value)
{
    if (address > UINT32_MAX - 3) {
        throw std::out_of_range("Memory word write out of bounds.");
    }
    const uint32_t endAddress = address + 3;
    if (!findOverlappingSpecialRange(address, endAddress)) {
        writeWordDirectRam(address, value);
        return;
    }

    writeByte(address, static_cast<uint8_t>((value >> 24) & 0xFF));
    writeByte(address + 1, static_cast<uint8_t>((value >> 16) & 0xFF));
    writeByte(address + 2, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeByte(address + 3, static_cast<uint8_t>(value & 0xFF));
}

void Memory::loadBinary(const std::vector<char>& binary, uint32_t address)
{
    const size_t start = static_cast<size_t>(address);
#if ROSPOSVM_SPARSE_MEMORY
    if (start > totalSize || binary.size() > (totalSize - start)) {
        std::ostringstream oss;
        oss << "Memory overflow while loading binary. start=" << start << " totalSize=" << totalSize << " binary.size()=" << binary.size() << ". Double check formatting";
        throw std::out_of_range(oss.str());
    }
    // Write byte-by-byte to lazily allocate pages
    for (size_t i = 0; i < binary.size(); ++i) {
        writeByte(static_cast<uint32_t>(start + i), static_cast<uint8_t>(binary[i]));
    }
#else
    if (start > mem.size() || binary.size() > (mem.size() - start)) {
        throw std::out_of_range("Memory overflow while loading binary.");
    }
    std::copy(binary.begin(), binary.end(), mem.begin() + start);
#endif
}

bool Memory::isSpecialAddress(uint32_t address) const
{
    return findSpecialRange(address) != nullptr;
}
