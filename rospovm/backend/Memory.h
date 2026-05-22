#ifndef MEMORY_H
#define MEMORY_H

#include <cstdint>
#include <vector>
#include <unordered_map>

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
#ifdef EMSCRIPTEN
    // On WASM, avoid a single huge allocation. Use a sparse page map (64KB pages)
    static constexpr size_t kPageSize = 65536;
    std::unordered_map<uint32_t, std::vector<uint8_t>> pages; // key = page index
    uint64_t totalSize = 0;
#else
    std::vector<uint8_t> mem;
#endif
    mutable int lastSpecialRangeIndex = -1;

    const SpecialMemoryRange* findSpecialRange(uint32_t address) const;
    const SpecialMemoryRange* findOverlappingSpecialRange(uint32_t startAddress, uint32_t endAddress) const;
    uint32_t readWordDirectRam(uint32_t address) const;
    void writeWordDirectRam(uint32_t address, uint32_t value);

public:
    Memory(uint64_t size);
    
    void addSpecialRange(const char* name, uint32_t start, uint32_t end, 
                         SpecialMemoryRange::Type type, bool readable, bool writable,
                         ReadHandler readHandler = nullptr,
                         WriteHandler writeHandler = nullptr);
    
    // Byte access
    uint8_t readByte(uint32_t address) const;
    uint8_t readByteForInspector(uint32_t address) const;
    void writeByte(uint32_t address, uint8_t value);
    
    // Half-word access
    uint16_t readHalf(uint32_t address) const;
    void writeHalf(uint32_t address, uint16_t value);
    
    // Word access
    uint32_t readWord(uint32_t address) const;
    void writeWord(uint32_t address, uint32_t value);
    
    // Binary loading
    void loadBinary(const std::vector<char>& binary, uint32_t address);

    // Returns true if the address belongs to a special/MMIO range.
    bool isSpecialAddress(uint32_t address) const;
};

#endif // MEMORY_H