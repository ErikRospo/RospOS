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
}

uint8_t Memory::readByte(uint32_t address) const
{
    for (const auto &range : specialRanges)
    {
        if (range.contains(address))
        {
            if (range.readable && range.readHandler)
            {
                return range.readHandler(address);
            }
            else
            {
                throw std::runtime_error("Attempted to read from non-readable special memory range \"" + std::string(range.name) + "\".");
            }
        }
    }
    if (static_cast<size_t>(address) >= mem.size()) {
        throw std::out_of_range("Memory read out of bounds.");
    }
    return mem[address];
}

void Memory::writeByte(uint32_t address, uint8_t value)
{
    for (const auto &range : specialRanges)
    {
        if (range.contains(address))
        {
            if (range.writable && range.writeHandler)
            {
                range.writeHandler(address, value);
                return;
            }
            else
            {
                throw std::runtime_error("Attempted to write to non-writable special memory range \"" + std::string(range.name) + "\".");
            }
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
    return static_cast<uint32_t>(
        (readByte(address) << 24) |
        (readByte(address + 1) << 16) |
        (readByte(address + 2) << 8) |
        (readByte(address + 3)));
}
void Memory::writeWord(uint32_t address, uint32_t value)
{
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
    for (const auto &range : specialRanges)
    {
        if (range.contains(address))
        {
            return true;
        }
    }
    return false;
}
