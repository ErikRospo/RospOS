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

#endif // TTY_H
