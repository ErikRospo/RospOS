#ifndef MEMORY_H
#define MEMORY_H

#include <cstdint>
#include <vector>

using ReadHandler = uint8_t (*)(uint32_t address);
using WriteHandler = void (*)(uint32_t address, uint8_t value);

struct SpecialMemoryRange
{
    uint32_t startAddress;
    uint32_t endAddress;
    enum class Type
    {
        MMIO,
        Reserved
    } type;
    char name[4];
    bool readable;
    bool writable;
    bool contains(uint32_t address) const
    {
        return address >= startAddress && address <= endAddress;
    }
    ReadHandler readHandler;
    WriteHandler writeHandler;
};

class Memory
{
private:
    std::vector<SpecialMemoryRange> specialRanges;
    std::vector<uint8_t> mem;

public:
    Memory(size_t size);
    
    void addSpecialRange(const char* name, uint32_t start, uint32_t end, 
                         SpecialMemoryRange::Type type, bool readable, bool writable,
                         ReadHandler readHandler = nullptr,
                         WriteHandler writeHandler = nullptr);
    
    // Byte access
    uint8_t readByte(uint32_t address) const;
    void writeByte(uint32_t address, uint8_t value);
    
    // Half-word access
    uint16_t readHalf(uint32_t address) const;
    void writeHalf(uint32_t address, uint16_t value);
    
    // Word access
    uint32_t readWord(uint32_t address) const;
    void writeWord(uint32_t address, uint32_t value);
    
    // Binary loading
    void loadBinary(const std::vector<char>& binary, uint32_t address);
};

#endif // MEMORY_H