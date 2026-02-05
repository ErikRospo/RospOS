#include "Memory.h"

#include <cstdint>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <stdio.h>
#include <termios.h>
#include <unistd.h>

#include <queue>
#include <mutex>
#include <condition_variable>
#include <thread>

std::queue<uint8_t> inputBuffer;
std::mutex bufferMutex;
std::condition_variable bufferCondition;

void BackgroundReader()
{
    struct termios oldt, newt;
    tcgetattr(STDIN_FILENO, &oldt); // Get current terminal settings
    newt = oldt;
    newt.c_lflag &= ~(ECHO | ICANON); // Disable echo and canonical mode
    tcsetattr(STDIN_FILENO, TCSANOW, &newt); // Apply new settings

    while (true)
    {
        char ch;
        read(STDIN_FILENO, &ch, 1); // Blocking read from TTY

        {
            std::lock_guard<std::mutex> lock(bufferMutex);
            inputBuffer.push(static_cast<uint8_t>(ch));
        }
        bufferCondition.notify_one();
    }

    // Restore terminal settings (not reachable, but good practice)
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
}

uint8_t TTYReadHandler(uint32_t address)
{
    (void)address; // Mark the parameter as unused to silence warnings

    std::unique_lock<std::mutex> lock(bufferMutex);
    bufferCondition.wait(lock, [] { return !inputBuffer.empty(); });

    uint8_t value = inputBuffer.front();
    inputBuffer.pop();
    return value;
}

void TTYWriteHandler(uint32_t address, uint8_t value)
{
    (void)address; // Mark the parameter as unused to silence warnings
    // Write to TTY (console output)
    std::cout << static_cast<char>(value);
    std::cout.flush();
}

// Start the background reader thread
std::thread backgroundReaderThread(BackgroundReader);