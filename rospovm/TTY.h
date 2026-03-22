#ifndef TTY_H
#define TTY_H

#include <cstdint>
#include <functional>

uint8_t TTYReadHandler(uint32_t address);
void TTYWriteHandler(uint32_t address, uint8_t value);

// Push a byte into the TTY input queue (thread-safe)
void TTYPush(uint8_t value);

// UI callbacks for VM-driven TTY events.
void TTYSetWriteCallback(const std::function<void(uint8_t)> &callback);
void TTYSetReadRequestCallback(const std::function<void()> &callback);

// Lifecycle hooks kept for compatibility with existing callers.
void TTYStart();
void TTYShutdown();

#endif // TTY_H
