#ifndef BLOCK_DEVICE_H
#define BLOCK_DEVICE_H

#include <cstdint>
#include <string>

class Memory;

uint8_t BlockDeviceReadHandler(uint32_t address);
void BlockDeviceWriteHandler(uint32_t address, uint8_t value);

void BlockDeviceInitialize(Memory *memory, const std::string &backingFilePath);
void BlockDeviceShutdown();

#endif // BLOCK_DEVICE_H
