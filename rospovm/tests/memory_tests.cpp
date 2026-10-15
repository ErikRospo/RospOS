#include "Memory.h"

#include <array>
#include <iostream>
#include <random>
#include <stdexcept>

namespace {
void require(bool condition)
{
    if (!condition) throw std::runtime_error("memory regression check failed");
}

template<typename F> void requireOutOfRange(F operation)
{
    try { operation(); } catch (const std::out_of_range &) { return; }
    throw std::runtime_error("expected an out-of-range access");
}

std::array<uint8_t, 4> device{};
uint32_t reads = 0;
uint8_t readDevice(uint32_t address) { ++reads; return device[address - 0x10000]; }
void writeDevice(uint32_t address, uint8_t value) { device[address - 0x10000] = value; }
}

int main()
{
    try {
        constexpr uint32_t size = 0x20005;
        Memory memory(size);
        require(memory.readWord(0xFFFF) == 0); // Two initially absent pages.
        memory.writeByte(0x10000, 0xAB);
        require(memory.readWord(0xFFFE) == 0x0000AB00); // Only second page exists.
        for (uint32_t address : {0xFFFCU, 0xFFFDU, 0xFFFEU, 0xFFFFU, size - 4}) {
            memory.writeWord(address, 0x80FF1234);
            require(memory.readWord(address) == 0x80FF1234);
            require(memory.readHalf(address) == 0x80FF);
            require(memory.readByteForInspector(address + 3) == 0x34);
        }
        memory.loadBinary({'a', 'b', 'c', 'd'}, 0xFFFE);
        require(memory.readWord(0xFFFE) == 0x61626364);
        requireOutOfRange([&]() { memory.readWord(size - 3); });
        requireOutOfRange([&]() { memory.writeWord(size - 3, 0); });
        requireOutOfRange([&]() { memory.writeByte(size, 0); });
        requireOutOfRange([&]() { memory.readByte(size); });
        requireOutOfRange([&]() { memory.loadBinary({'a', 'b'}, size - 1); });
        requireOutOfRange([&]() { memory.readHalf(UINT32_MAX); });
        requireOutOfRange([&]() { memory.writeWord(UINT32_MAX - 2, 0); });

        // Compare unaligned/page-crossing accesses against a byte-level oracle.
        Memory randomMemory(size);
        std::vector<uint8_t> reference(size, 0);
        std::mt19937 random(42);
        for (int i = 0; i < 5000; ++i) {
            const uint32_t address = random() % (size - 3);
            const uint32_t value = random();
            randomMemory.writeWord(address, value);
            for (int byte = 0; byte < 4; ++byte)
                reference[address + byte] = static_cast<uint8_t>(value >> (24 - byte * 8));
            const uint32_t probe = random() % (size - 3);
            uint32_t expected = 0;
            for (int byte = 0; byte < 4; ++byte) expected = (expected << 8) | reference[probe + byte];
            require(randomMemory.readWord(probe) == expected);
        }

        memory.addSpecialRange("TEST", 0x10000, 0x10003, SpecialMemoryRange::Type::MMIO,
                               true, true, readDevice, writeDevice);
        memory.writeWord(0xFFFE, 0x11223344); // RAM/MMIO crossing retains handlers.
        require(device[0] == 0x33 && device[1] == 0x44);
        require(memory.readWord(0xFFFE) == 0x11223344 && reads == 2);

#if ROSPOSVM_SPARSE_MEMORY
        memory.loadBinary({'x', 'y'}, 0x10000);
        require(device[0] == 'x' && device[1] == 'y');
        Memory fullAddressSpace(1ULL << 32);
        require(fullAddressSpace.readWord(0xFFFFFFFC) == 0);
        fullAddressSpace.writeWord(0xFFFFFFFC, 0xDEADBEEF);
        require(fullAddressSpace.readWord(0xFFFFFFFC) == 0xDEADBEEF);
        fullAddressSpace.writeHalf(0xFFFFFFFE, 0x1234);
        require(fullAddressSpace.readWord(0xFFFFFFFC) == 0xDEAD1234);
        requireOutOfRange([&]() { fullAddressSpace.readWord(0xFFFFFFFD); });
#endif
        std::cout << "Memory regression tests passed\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
