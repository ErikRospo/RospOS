#include "Memory.h"

#include <cstdint>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <stdio.h>

uint8_t TTYReadHandler(uint32_t address)
{
    // Blocking read from TTY
    char ch;
    std::cin.get(ch);
    return static_cast<uint8_t>(ch);
}

void TTYWriteHandler(uint32_t address, uint8_t value)
{
    // Write to TTY (console output)
    std::cout << static_cast<char>(value);
    std::cout.flush();
}