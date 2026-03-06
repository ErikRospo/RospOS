#include "DebugParser.h"
#include <sstream>
#include <iostream>
#include <iomanip>

std::shared_ptr<DebugInfo> DebugParser::parse(const std::string& data) {
    auto debug_info = std::make_shared<DebugInfo>();
    debug_info->version = 0;
    debug_info->segment_address = 0;
    
    std::istringstream stream(data);
    std::string line;
    
    enum class ParseState {
        HEADER,
        ENTRIES,
        FILES
    };
    
    ParseState state = ParseState::HEADER;
    
    while (std::getline(stream, line)) {
        // Skip empty lines and comments
        if (line.empty() || line[0] == '#') {
            continue;
        }
        
        // Check for state transitions
        if (line == "FILES:") {
            state = ParseState::FILES;
            continue;
        }
        
        switch (state) {
            case ParseState::HEADER: {
                if (line.find("DEBUG_VERSION:") == 0) {
                    std::istringstream iss(line.substr(14));
                    iss >> debug_info->version;
                } else if (line.find("SEGMENT_ADDRESS:") == 0) {
                    std::string addr_str = line.substr(16);
                    // Trim whitespace
                    size_t start = addr_str.find_first_not_of(" \t");
                    if (start != std::string::npos) {
                        addr_str = addr_str.substr(start);
                    }
                    debug_info->segment_address = std::stoul(addr_str, nullptr, 0);
                } else if (line.find("ENCODING:") == 0) {
                    // We assume UTF-8, nothing to do
                } else if (line.find("0x") == 0) {
                    // Start of entries
                    state = ParseState::ENTRIES;
                    // Fall through to parse this line as an entry
                    DebugEntry entry;
                    if (parse_entry_line(line, entry)) {
                        debug_info->entries.push_back(entry);
                    }
                }
                break;
            }
            
            case ParseState::ENTRIES: {
                DebugEntry entry;
                if (parse_entry_line(line, entry)) {
                    debug_info->entries.push_back(entry);
                } else {
                    std::cerr << "Warning: Failed to parse debug entry: " << line << std::endl;
                }
                break;
            }
            
            case ParseState::FILES: {
                uint32_t file_id;
                std::string path;
                if (parse_file_line(line, file_id, path)) {
                    debug_info->file_table[file_id] = path;
                } else {
                    std::cerr << "Warning: Failed to parse file table entry: " << line << std::endl;
                }
                break;
            }
        }
    }
    
    return debug_info;
}

bool DebugParser::parse_entry_line(const std::string& line, DebugEntry& entry) {
    // Format: 0x00000000 0x00000001 0 42 "text"
    std::istringstream iss(line);
    std::string addr_str, flags_str;
    
    iss >> addr_str >> flags_str >> entry.file_id >> entry.line;
    
    if (iss.fail()) {
        return false;
    }
    
    // Parse address and flags as hex
    entry.address = std::stoul(addr_str, nullptr, 0);
    entry.flags = std::stoul(flags_str, nullptr, 0);
    
    // Skip whitespace to find the quoted string
    iss >> std::ws;
    
    // Read the rest of the line as the quoted string
    std::string quoted;
    std::getline(iss, quoted);
    
    if (quoted.empty()) {
        entry.original_text = "";
        return true;
    }
    
    // Unquote the string
    entry.original_text = unquote_string(quoted);
    
    return true;
}

bool DebugParser::parse_file_line(const std::string& line, uint32_t& file_id, std::string& path) {
    // Format: 0 /path/to/file.ros
    std::istringstream iss(line);
    
    iss >> file_id;
    if (iss.fail()) {
        return false;
    }
    
    // Skip whitespace and read the rest as the path
    iss >> std::ws;
    std::getline(iss, path);
    
    return !path.empty();
}

std::string DebugParser::unquote_string(const std::string& quoted) {
    if (quoted.size() < 2) {
        return quoted;
    }
    
    // Check if it starts and ends with quotes
    if (quoted.front() != '"' || quoted.back() != '"') {
        return quoted;
    }
    
    // Remove surrounding quotes
    std::string content = quoted.substr(1, quoted.size() - 2);
    std::string result;
    result.reserve(content.size());
    
    for (size_t i = 0; i < content.size(); ++i) {
        if (content[i] == '\\' && i + 1 < content.size()) {
            char next = content[i + 1];
            switch (next) {
                case '"':  result += '"'; i++; break;
                case '\\': result += '\\'; i++; break;
                case 'n':  result += '\n'; i++; break;
                case 'r':  result += '\r'; i++; break;
                case 't':  result += '\t'; i++; break;
                case 'u': {
                    // Unicode escape: \uXXXX
                    if (i + 5 < content.size()) {
                        std::string hex = content.substr(i + 2, 4);
                        try {
                            uint32_t code = std::stoul(hex, nullptr, 16);
                            // Simple UTF-8 encoding for basic multilingual plane
                            if (code < 0x80) {
                                result += static_cast<char>(code);
                            } else if (code < 0x800) {
                                result += static_cast<char>(0xC0 | (code >> 6));
                                result += static_cast<char>(0x80 | (code & 0x3F));
                            } else {
                                result += static_cast<char>(0xE0 | (code >> 12));
                                result += static_cast<char>(0x80 | ((code >> 6) & 0x3F));
                                result += static_cast<char>(0x80 | (code & 0x3F));
                            }
                            i += 5;
                        } catch (...) {
                            // Invalid unicode escape, keep as-is
                            result += content[i];
                        }
                    } else {
                        result += content[i];
                    }
                    break;
                }
                default:
                    // Unknown escape, keep the backslash
                    result += content[i];
                    break;
            }
        } else {
            result += content[i];
        }
    }
    
    return result;
}
