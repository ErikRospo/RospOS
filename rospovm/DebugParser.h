#ifndef DEBUG_PARSER_H
#define DEBUG_PARSER_H

#include "Binary.h"
#include <string>
#include <memory>

/**
 * DebugParser: Parses debug segment text format into DebugInfo structures.
 * 
 * Format:
 *   DEBUG_VERSION: 1
 *   SEGMENT_ADDRESS: 0x00000000
 *   ENCODING: UTF-8
 *   
 *   0x00000000 0x00000001 0 42 "LLI r1, 0x12345678"
 *   0x00000004 0x00000000 0 43 "ADD r2, r1, r1"
 *   FILES:
 *   0 /path/to/file.ros
 *   1 /path/to/other.ros
 */
class DebugParser {
public:
    /**
     * Parse a debug segment from text data.
     * 
     * @param data The UTF-8 text data from the debug segment
     * @return A shared pointer to the parsed DebugInfo, or nullptr on failure
     */
    static std::shared_ptr<DebugInfo> parse(const std::string& data);

private:
    /**
     * Unescape a JSON-style quoted string.
     * Handles: \", \\, \n, \r, \t, \uXXXX
     */
    static std::string unquote_string(const std::string& quoted);
    
    /**
     * Parse a single debug entry line.
     * Returns true if successful, false otherwise.
     */
    static bool parse_entry_line(const std::string& line, DebugEntry& entry);
    
    /**
     * Parse a file table line.
     * Returns true if successful, false otherwise.
     */
    static bool parse_file_line(const std::string& line, uint32_t& file_id, std::string& path);
};

#endif // DEBUG_PARSER_H
