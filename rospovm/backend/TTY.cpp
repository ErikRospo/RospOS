#include "TTY.h"

#include "Shutdown.h"

#include <QCoreApplication>
#include <QThread>

#include <chrono>
#include <condition_variable>
#include <mutex>
#include <queue>
#include <stdexcept>

namespace {
std::queue<uint8_t> inputBuffer;
std::mutex bufferMutex;
std::condition_variable bufferCondition;

std::mutex callbackMutex;
std::function<void(uint8_t)> writeCallback;
std::function<void()> readRequestCallback;
}

bool TTYHasInput(size_t count)
{
    std::lock_guard<std::mutex> lock(bufferMutex);
    return inputBuffer.size() >= count;
}

void TTYRequestInput()
{
    std::function<void()> callbackCopy;
    {
        std::lock_guard<std::mutex> callbackLock(callbackMutex);
        callbackCopy = readRequestCallback;
    }
    if (callbackCopy) callbackCopy();
}

uint8_t TTYReadHandler(uint32_t address)
{
    (void)address;

    std::unique_lock<std::mutex> lock(bufferMutex);
    if (inputBuffer.empty() && !shouldShutdown()) {
        lock.unlock();
        TTYRequestInput();
        lock.lock();
    }
    while (inputBuffer.empty() && !shouldShutdown())
    {
        if (QCoreApplication::instance() &&
            QThread::currentThread() == QCoreApplication::instance()->thread())
        {
            // GUI execution preflights complete TTY reads and yields before
            // reaching here. Reject other synchronous reads (e.g. device DMA)
            // rather than blocking the browser or entering a nested event loop.
            throw std::runtime_error("TTY input is not available for a synchronous GUI read");
        }
        else
        {
            bufferCondition.wait_for(lock, std::chrono::milliseconds(50));
        }
    }

    if (inputBuffer.empty())
    {
        // This can happen if a shutdown was requested while we were waiting for input.
        return 0;
    }

    const uint8_t value = inputBuffer.front();
    inputBuffer.pop();
    return value;
}

void TTYWriteHandler(uint32_t address, uint8_t value)
{
    (void)address;

    std::function<void(uint8_t)> callbackCopy;
    {
        std::lock_guard<std::mutex> callbackLock(callbackMutex);
        callbackCopy = writeCallback;
    }

    if (callbackCopy)
    {
        callbackCopy(value);
    }
}

void TTYPush(uint8_t value)
{
    {
        std::lock_guard<std::mutex> lock(bufferMutex);
        inputBuffer.push(value);
    }
    bufferCondition.notify_one();
}

void TTYSetWriteCallback(const std::function<void(uint8_t)> &callback)
{
    std::lock_guard<std::mutex> callbackLock(callbackMutex);
    writeCallback = callback;
}

void TTYSetReadRequestCallback(const std::function<void()> &callback)
{
    std::lock_guard<std::mutex> callbackLock(callbackMutex);
    readRequestCallback = callback;
}

void TTYStart()
{
    // No-op: input is supplied by the Qt TTY widget.
}

void TTYShutdown()
{
    {
        std::lock_guard<std::mutex> lock(bufferMutex);
        std::queue<uint8_t> empty;
        inputBuffer.swap(empty);
    }

    {
        std::lock_guard<std::mutex> callbackLock(callbackMutex);
        writeCallback = nullptr;
        readRequestCallback = nullptr;
    }

    bufferCondition.notify_all();
}
