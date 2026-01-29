#include "Memory.h"

#include <cstdint>
#include <vector>
#include <stdexcept>


Memory::Memory(size_t size) {
    mem.resize(size, 0);
    specialRanges.clear();
        
}

void Memory::addSpecialRange(uint32_t start, uint32_t end, SpecialMemoryRange::Type type, bool readable, bool writable,
                             ReadHandler readHandler,
                             WriteHandler writeHandler)
{
    specialRanges.push_back({start, end, type, readable, writable, readHandler, writeHandler});
}

uint8_t Memory::readByte(uint32_t address) const
{
    return mem[address];
}


void Memory::writeByte(uint32_t address, uint8_t value)
{
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
    if (address + binary.size() > mem.size())
    {
        throw std::out_of_range("Memory overflow while loading binary.");
    }
    std::copy(binary.begin(), binary.end(), mem.begin() + address);
}