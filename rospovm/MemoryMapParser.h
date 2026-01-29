#ifndef MEMORY_MAP_PARSER_H
#define MEMORY_MAP_PARSER_H

#include <map>
#include <string>
#include <cstdint>

std::map<uint32_t, std::string> parseMemoryMap(const std::string& mmapFile);

#endif // MEMORY_MAP_PARSER_H