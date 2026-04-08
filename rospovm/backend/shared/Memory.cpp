#include "Memory.h"

#include <algorithm>
#include <cstdint>
#include <stdexcept>
#include <string>
#include <vector>

Memory::Memory(size_t size)
{
    mem.resize(size, 0);
    specialRanges.clear();
    lastSpecialRangeIndex = -1;
}

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
    const size_t start = static_cast<size_t>(address);
    if (start + 3 >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }

    return (static_cast<uint32_t>(mem[start]) << 24) |
           (static_cast<uint32_t>(mem[start + 1]) << 16) |
           (static_cast<uint32_t>(mem[start + 2]) << 8) |
           static_cast<uint32_t>(mem[start + 3]);
}

void Memory::writeWordDirectRam(uint32_t address, uint32_t value)
{
    const size_t start = static_cast<size_t>(address);
    if (start + 3 >= mem.size()) {
        throw std::out_of_range("Memory write out of bounds.");
    }

    mem[start] = static_cast<uint8_t>((value >> 24) & 0xFF);
    mem[start + 1] = static_cast<uint8_t>((value >> 16) & 0xFF);
    mem[start + 2] = static_cast<uint8_t>((value >> 8) & 0xFF);
    mem[start + 3] = static_cast<uint8_t>(value & 0xFF);
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

    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    return mem[address];
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

    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    return mem[address];
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

    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory write out of bounds.");
    }
    mem[address] = value;
}

uint16_t Memory::readHalf(uint32_t address) const
{
    return static_cast<uint16_t>(readByte(address) << 8 | (readByte(address + 1)));
}
void Memory::writeHalf(uint32_t address, uint16_t value)
{
    writeByte(address, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeByte(address + 1, static_cast<uint8_t>(value & 0xFF));
}
uint32_t Memory::readWord(uint32_t address) const
{
    if (address <= (UINT32_MAX - 3)) {
        const uint32_t endAddress = address + 3;
        if (!findOverlappingSpecialRange(address, endAddress)) {
            return readWordDirectRam(address);
        }
    }

    return static_cast<uint32_t>(
        (static_cast<uint32_t>(readByte(address)) << 24) |
        (static_cast<uint32_t>(readByte(address + 1)) << 16) |
        (static_cast<uint32_t>(readByte(address + 2)) << 8) |
        static_cast<uint32_t>(readByte(address + 3)));
}
void Memory::writeWord(uint32_t address, uint32_t value)
{
    if (address <= (UINT32_MAX - 3)) {
        const uint32_t endAddress = address + 3;
        if (!findOverlappingSpecialRange(address, endAddress)) {
            writeWordDirectRam(address, value);
            return;
        }
    }

    writeByte(address, static_cast<uint8_t>((value >> 24) & 0xFF));
    writeByte(address + 1, static_cast<uint8_t>((value >> 16) & 0xFF));
    writeByte(address + 2, static_cast<uint8_t>((value >> 8) & 0xFF));
    writeByte(address + 3, static_cast<uint8_t>(value & 0xFF));
}

void Memory::loadBinary(const std::vector<char>& binary, uint32_t address)
{
    const size_t start = static_cast<size_t>(address);
    if (start > mem.size() || binary.size() > (mem.size() - start)) {
        throw std::out_of_range("Memory overflow while loading binary.");
    }
    std::copy(binary.begin(), binary.end(), mem.begin() + start);
}

bool Memory::isSpecialAddress(uint32_t address) const
{
    return findSpecialRange(address) != nullptr;
}
