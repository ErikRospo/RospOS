#ifndef TTY_H
#define TTY_H

#include "Memory.h"

#include <cstdint>
#include <vector>
#include <stdexcept>
#include <iostream>
#include <stdio.h>

uint8_t TTYReadHandler(uint32_t address);
void TTYWriteHandler(uint32_t address, uint8_t value);

// Push a byte into the TTY input queue (thread-safe)
void TTYPush(uint8_t value);

// Start/stop the TTY background reader thread. Call `TTYStart()` before
// running the VM's main loop and `TTYShutdown()` during shutdown.
void TTYStart();
void TTYShutdown();

#endif // TTY_H
