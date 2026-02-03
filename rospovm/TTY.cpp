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
    // Disable terminal echo and enable non-canonical mode
    struct termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt); // Get current terminal settings
    newt = oldt;
    newt.c_lflag &= ~(ECHO | ICANON); // Disable echo and canonical mode
    tcsetattr(STDIN_FILENO, TCSANOW, &newt); // Apply new settings

    // Blocking read from TTY
    char ch;
    read(STDIN_FILENO, &ch, 1); // Use low-level read to capture raw input

    // Restore terminal settings
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);

    return static_cast<uint8_t>(ch);
}

void TTYWriteHandler(uint32_t address, uint8_t value)
{
    // Write to TTY (console output)
    std::cout << static_cast<char>(value);
    std::cout.flush();
}