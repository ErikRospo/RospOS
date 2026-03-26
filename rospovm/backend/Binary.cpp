#include "Binary.h"
#include "DebugParser.h"

#include <cstdint>
#include <fstream>
#include <iostream>
#include <stdexcept>
#include <vector>
#include <filesystem>
#include <sstream>
#include <zlib.h>

// Magic number for RospOS binary format
const uint32_t ROSP_MAGIC = 0x50534F52;  // "ROSP" in ASCII

static std::vector<uint8_t> decompress_gzip(const std::vector<uint8_t>& data) {
    z_stream stream = {};
    stream.next_in = const_cast<Bytef*>(data.data());
    stream.avail_in = static_cast<uInt>(data.size());

    // windowBits = 15 + 16 enables gzip decoding in zlib
    if (inflateInit2(&stream, 15 + 16) != Z_OK) {
        throw std::runtime_error("Failed to initialize gzip decompression");
    }

    std::vector<uint8_t> result;
    uint8_t buf[65536];
    int ret;
    do {
        stream.next_out = buf;
        stream.avail_out = sizeof(buf);
        ret = inflate(&stream, Z_NO_FLUSH);
        if (ret == Z_STREAM_ERROR || ret == Z_DATA_ERROR || ret == Z_MEM_ERROR) {
            inflateEnd(&stream);
            throw std::runtime_error("Gzip decompression failed");
        }
        result.insert(result.end(), buf, buf + (sizeof(buf) - stream.avail_out));
    } while (ret != Z_STREAM_END);

    inflateEnd(&stream);
    return result;
}

Binary Binary::load_binary(const std::string& path)
{
    std::ifstream file(path, std::ios::binary);
    if (!file) {
        std::filesystem::path cwd=std::filesystem::current_path();
        std::filesystem::path full_path = cwd / path;
        full_path=full_path.lexically_normal();
        std::ostringstream oss;
        oss << "Failed to open binary file: " << path << ". Does the file exist and is it readable? Does the path ";
        oss << full_path.string() << " exist?";
        throw std::runtime_error(oss.str());
    }

    uint32_t magic;
    uint32_t version;
    uint32_t segment_count;

    file.read(reinterpret_cast<char*>(&magic), sizeof(magic));
    file.read(reinterpret_cast<char*>(&version), sizeof(version));
    file.read(reinterpret_cast<char*>(&segment_count), sizeof(segment_count));

    if (magic != ROSP_MAGIC) {
        throw std::runtime_error("Invalid binary format: magic number does not match");
    }
    
    std::cout << "Loading binary version " << version << " with " 
              << segment_count << " segments." << std::endl;

    Binary bin;
    bin.version = version;

    // Version detection: V1 vs V2
    if (version == 1) {
        // V1 format: no flags, just address and size
        for (uint32_t i = 0; i < segment_count; ++i) {
            uint32_t addr;
            uint32_t size;

            file.read(reinterpret_cast<char*>(&addr), sizeof(addr));
            file.read(reinterpret_cast<char*>(&size), sizeof(size));

            Segment seg;
            seg.address = addr;
            seg.data.resize(size);

            file.read(reinterpret_cast<char*>(seg.data.data()), size);
            
            if (!file) {
                throw std::runtime_error("Error reading segment data from binary file");
            }

            bin.segments.push_back(std::move(seg));
        }
    } else if (version == 2) {
        // V2 format: flags, address, size
        for (uint32_t i = 0; i < segment_count; ++i) {
            uint32_t flags;
            uint32_t addr;
            uint32_t size;

            file.read(reinterpret_cast<char*>(&flags), sizeof(flags));
            file.read(reinterpret_cast<char*>(&addr), sizeof(addr));
            file.read(reinterpret_cast<char*>(&size), sizeof(size));

            std::vector<uint8_t> data(size);
            file.read(reinterpret_cast<char*>(data.data()), size);
            
            if (!file) {
                throw std::runtime_error("Error reading segment data from binary file");
            }

            if (flags & SEGMENT_FLAG_COMPRESSED) {
                data = decompress_gzip(data);
            }

            // Check if this is a debug segment
            if (flags & SEGMENT_FLAG_DEBUG) {
                // Parse debug segment
                std::string debug_text(data.begin(), data.end());
                auto debug_info = DebugParser::parse(debug_text);
                
                if (debug_info) {
                    std::cout << "  Debug segment for address 0x" << std::hex << addr 
                              << std::dec << " (" << debug_info->entries.size() 
                              << " entries, " << debug_info->file_table.size() 
                              << " files)" << std::endl;
                    // Store debug info in the binary's debug map
                    bin.debug_map[addr] = debug_info;
                } else {
                    std::cerr << "Warning: Failed to parse debug segment" << std::endl;
                }
            } else if (flags & SEGMENT_FLAG_LOADABLE) {
                // Loadable segment - add to segments list
                Segment seg;
                seg.address = addr;
                seg.data = std::move(data);
                bin.segments.push_back(std::move(seg));
                std::cout << "  Loadable segment at address 0x" << std::hex << addr 
                          << std::dec << " with size " << seg.data.size() << " bytes" << std::endl;
            } else {
                std::cerr << "Warning: Segment with unknown flags 0x" 
                          << std::hex << flags << std::dec << std::endl;
            }
        }
    } else {
        throw std::runtime_error("Unsupported binary version: " + std::to_string(version));
    }

    return bin;
}

const DebugEntry* Binary::get_debug_entry(uint32_t address) const {
    // Search through all debug info maps
    for (const auto& pair : debug_map) {
        const auto& debug_info = pair.second;
        
        // Search for an entry matching this address
        for (const auto& entry : debug_info->entries) {
            if (entry.address == address) {
                return &entry;
            }
        }
    }
    
    return nullptr;
}
