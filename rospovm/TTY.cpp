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
#include "TTY.h"
#include "Shutdown.h"
#include <fcntl.h>
#include <errno.h>

static std::atomic<bool> backgroundReaderRunning{false};
static std::thread backgroundReaderThread;

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
    // set non-blocking mode so we can exit promptly
    int flags = fcntl(STDIN_FILENO, F_GETFL, 0);
    fcntl(STDIN_FILENO, F_SETFL, flags | O_NONBLOCK);

    while (backgroundReaderRunning.load() && !shouldShutdown())
    {
        char ch;
        ssize_t n = read(STDIN_FILENO, &ch, 1);
        if (n > 0)
        {
            {
                std::lock_guard<std::mutex> lock(bufferMutex);
                inputBuffer.push(static_cast<uint8_t>(ch));
            }
            bufferCondition.notify_one();
        }
        else
        {
            if (n == -1 && errno != EAGAIN && errno != EWOULDBLOCK)
            {
                // unexpected error, break out
                break;
            }
            // Sleep briefly to avoid busy loop
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    }

    // Restore terminal settings
    tcsetattr(STDIN_FILENO, TCSANOW, &oldt);
}

uint8_t TTYReadHandler(uint32_t address)
{
    (void)address; // Mark the parameter as unused to silence warnings

    std::unique_lock<std::mutex> lock(bufferMutex);
    // Wait with timeout so we can periodically check for shutdown.
    while (inputBuffer.empty() && !shouldShutdown())
    {
        bufferCondition.wait_for(lock, std::chrono::milliseconds(50));
    }

    if (inputBuffer.empty())
    {
        // Shutdown requested (or spurious wake) and no data available.
        return 0;
    }

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
void TTYPush(uint8_t value)
{
    {
        std::lock_guard<std::mutex> lock(bufferMutex);
        inputBuffer.push(value);
    }
    bufferCondition.notify_one();
}

void TTYStart()
{
    if (backgroundReaderRunning.load()) return;
    backgroundReaderRunning.store(true);
    backgroundReaderThread = std::thread(BackgroundReader);
}

void TTYShutdown()
{
    backgroundReaderRunning.store(false);
    // wake reader if blocked on condition
    bufferCondition.notify_all();
    if (backgroundReaderThread.joinable())
    {
        backgroundReaderThread.join();
    }
}