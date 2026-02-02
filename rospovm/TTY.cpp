#include "Memory.h"

#include <cstdint>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

uint8_t TTYReadHandler(uint32_t address)
{
    // Disable terminal echo
    struct termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt); // Get current terminal settings
    newt = oldt;
    newt.c_lflag &= ~ECHO;         // Disable echo
    tcsetattr(STDIN_FILENO, TCSANOW, &newt); // Apply new settings

    // Blocking read from TTY
    char ch;
    std::cin.get(ch);

    // Restore terminal settings
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);

    return static_cast<uint8_t>(ch);
}

void TTYWriteHandler(uint32_t address, uint8_t value)
{
    // Write to TTY (console output)
    std::cerr << "Attempting to write character: " << std::hex << static_cast<int>(value) << std::dec << " " << static_cast<char>(value) << std::endl;
    std::cout << static_cast<char>(value);
    std::cout.flush();
}