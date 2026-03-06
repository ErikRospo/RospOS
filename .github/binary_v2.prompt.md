# RospOS Binary Format V2 - Debug Information Implementation Plan

**Date**: March 6, 2026  
**Status**: Planning Phase

## Overview

This document outlines the implementation plan for RospOS Binary Format Version 2, which adds comprehensive debug information support for improved debugging and error reporting.

## Goals

1. Add debug information segments to the `.rosp` binary format
2. Track source file and line information throughout compilation
3. Support pseudo-instruction expansion tracking
4. Add rospocc source tracking with sidecar debug files
5. Maintain backward compatibility with V1 binaries

## Binary Format V2 Specification

### File Structure

```
+---------------------------+
| Magic Number (4 bytes)    |  0x50534F52 ("ROSP")
+---------------------------+
| Version (4 bytes)         |  2
+---------------------------+
| Segment Count (4 bytes)   |  Total segments (loadable + debug)
+---------------------------+
| Segment 1                 |
|   - Flags (4 bytes)       |
|   - Address (4 bytes)     |
|   - Size (4 bytes)        |
|   - Data (variable)       |
+---------------------------+
| Segment 2                 |
|   ...                     |
+---------------------------+
| Debug Segment(s)          |
|   - Flags (4 bytes)       |
|   - Address (4 bytes)     |  (0 for debug segments)
|   - Size (4 bytes)        |
|   - Data (variable)       |
+---------------------------+
```

### Segment Flags (32-bit bitmask)

```
Bit 0:  LOADABLE      (1 = load into memory, 0 = metadata only)
Bit 1:  DEBUG_INFO    (1 = contains debug information)
Bit 2:  COMPRESSED    (reserved for future use)
Bits 3-31: Reserved   (must be 0)
```

**Flag Combinations:**
- `0x00000001`: Normal loadable segment (code/data)
- `0x00000002`: Debug information segment (not loaded)
- `0x00000003`: Loadable segment with embedded debug (future use)

### Debug Segment Data Format (Text-based)

Each debug segment is a UTF-8 text file with the following format:

```
DEBUG_VERSION: 1
SEGMENT_ADDRESS: 0x00000000
ENCODING: UTF-8

# Debug entries (one per line)
[address] [flags] [file_id] [line] [original_text]

# File table at end
FILES:
[file_id] [path]

# Example:
0x00000000 0x00000001 0 42 "LLI r1, 0x12345678"
0x00000000 0x00000000 1 10 "ADD r1, r2, r3"
FILES:
0 /home/user/src/main.ros
1 /home/user/src/lib.ros
```

**Debug Entry Fields:**
- `address`: Memory address (hex) of the instruction/data
- `flags`: 32-bit hex flags:
  - Bit 0: Pseudo-instruction (1 = expanded from pseudo)
  - Bit 1: From rospocc (1 = originally from .rosc file)
  - Bit 2: Optimized (1 = modified by optimizer)
  - Bit 3-7: Expansion depth (0-31, for nested expansions)
  - Bits 8-31: Reserved
- `file_id`: Index into file table
- `line`: Line number (1-based)
- `original_text`: Original source text (quoted, escaped)

**File Table Format:**
```
FILES:
[id] [path]
[id] [path]
...
```

## Implementation Phases

### Phase 1: Core Data Structures & IR Enhancements

**Files to modify:**
- `rospoas/ir.py`
- `rospoas/transformer.py`
- `rospovm/Binary.h`
- `rospovm/Binary.cpp`

**Tasks:**

1.1. **Enhance IR Source Tracking** (`rospoas/ir.py`)
   - Extend `src` dict to include:
     - `file`: Source file path
     - `line`: Line number
     - `pp_line`: Preprocessed line number
     - `original_text`: Original source text (NEW)
     - `include_chain`: List of includes that led here (NEW)
   - Add flags field to Instruction/Directive classes:
     - `is_pseudo_expanded`: bool
     - `is_from_rospocc`: bool
     - `is_optimized`: bool
     - `expansion_depth`: int

1.2. **Update Transformer** (`rospoas/transformer.py`)
   - Store original text from tokens
   - Track include chain during preprocessing
   - Propagate source info through transformations

1.3. **Binary Format V2 Structures** (`rospovm/Binary.h`)
   ```cpp
   // Segment flags
   const uint32_t SEGMENT_FLAG_LOADABLE = 0x00000001;
   const uint32_t SEGMENT_FLAG_DEBUG    = 0x00000002;
   
   struct DebugEntry {
       uint32_t address;
       uint32_t flags;
       uint32_t file_id;
       uint32_t line;
       std::string original_text;
   };
   
   struct DebugInfo {
       uint32_t version;
       uint32_t segment_address;
       std::vector<DebugEntry> entries;
       std::map<uint32_t, std::string> file_table;
   };
   
   struct SegmentV2 {
       uint32_t flags;
       uint32_t address;
       std::vector<uint8_t> data;
       std::shared_ptr<DebugInfo> debug_info; // populated if DEBUG flag set
   };
   
   struct BinaryV2 {
       uint32_t version;
       std::vector<SegmentV2> segments;
       std::map<uint32_t, DebugInfo> debug_map; // address -> debug info
   };
   ```

### Phase 2: Debug Info Collection & Generation

**Files to modify:**
- `rospoas/compile.py`
- `rospoas/lower.py`
- `rospoas/optimizer.py`
- `rospoas/encode.py`

**Tasks:**

2.1. **Track Pseudo-Instruction Expansion** (`rospoas/lower.py`)
   - Mark generated instructions with `is_pseudo_expanded=True`
   - Copy parent source info to expanded instructions
   - Increment `expansion_depth` for nested expansions
   - Store original pseudo-instruction text

2.2. **Track Optimizer Changes** (`rospoas/optimizer.py`)
   - Mark modified instructions with `is_optimized=True`
   - Preserve source info through optimizations
   - Log optimization transformations

2.3. **Collect Debug Info During Layout** (`rospoas/compile.py`)
   - Create debug info builder class
   - Collect debug entries during layout phase
   - Build file table from all source references
   - Generate one debug segment per loadable segment

2.4. **Generate Debug Text Format** (new file: `rospoas/debug_writer.py`)
   ```python
   class DebugInfoWriter:
       def __init__(self):
           self.entries = []
           self.file_table = {}
           self.file_id_counter = 0
       
       def add_entry(self, address, flags, src_info, original_text):
           """Add a debug entry"""
           pass
       
       def get_file_id(self, filepath):
           """Get or create file ID"""
           pass
       
       def write_debug_segment(self, segment_addr):
           """Generate text debug segment data"""
           pass
   ```

### Phase 3: Binary Writing (V2 Format)

**Files to modify:**
- `rospoas/compile.py`

**Tasks:**

3.1. **Write V2 Binary Format**
   ```python
   MAGIC = 0x50534F52
   VERSION = 2
   
   # Write header
   f.write(struct.pack("<III", MAGIC, VERSION, total_segment_count))
   
   # Write loadable segments
   for addr, data in segments:
       flags = 0x00000001  # LOADABLE
       f.write(struct.pack("<III", flags, addr, len(data)))
       f.write(data)
   
   # Write debug segments (one per loadable segment)
   for addr, debug_text in debug_segments:
       flags = 0x00000002  # DEBUG_INFO
       debug_bytes = debug_text.encode('utf-8')
       f.write(struct.pack("<III", flags, addr, len(debug_bytes)))
       f.write(debug_bytes)
   ```

### Phase 4: Binary Reading (V2 Format with V1 Compatibility)

**Files to modify:**
- `rospovm/Binary.cpp`
- `rospovm/Binary.h`

**Tasks:**

4.1. **Version Detection**
   ```cpp
   Binary Binary::load_binary(const std::string& path) {
       // Read header
       uint32_t magic, version;
       file.read(...);
       
       if (version == 1) {
           return load_binary_v1(file);
       } else if (version == 2) {
           return load_binary_v2(file);
       } else {
           throw std::runtime_error("Unsupported binary version");
       }
   }
   ```

4.2. **V2 Loader**
   ```cpp
   BinaryV2 load_binary_v2(std::ifstream& file) {
       BinaryV2 bin;
       // Read segments with flags
       for (each segment) {
           uint32_t flags, addr, size;
           file.read(...);
           
           if (flags & SEGMENT_FLAG_LOADABLE) {
               // Load into memory segments
           }
           if (flags & SEGMENT_FLAG_DEBUG) {
               // Parse debug info
               auto debug_info = parse_debug_segment(data);
               bin.debug_map[addr] = debug_info;
           }
       }
       return bin;
   }
   ```

4.3. **Debug Info Parser** (new file: `rospovm/DebugParser.cpp`)
   ```cpp
   class DebugParser {
   public:
       static DebugInfo parse(const std::string& text);
   private:
       static DebugEntry parse_entry(const std::string& line);
       static std::map<uint32_t, std::string> parse_file_table(
           const std::string& text);
   };
   ```

### Phase 5: Rospocc Integration

**Files to modify:**
- `rospocc/transformer.py`
- `rospocc/parser.py`
- `rospocc/emitter.py`

**Tasks:**

5.1. **Source Tracking in Rospocc Transformer** (`rospocc/transformer.py`)
   - Extract line from Lark meta
   - Store original token text
   - Propagate through AST transformations
   - Track include chain from preprocessor

5.2. **Generate .rosc.debug Sidecar** (new file: `rospocc/debug_emitter.py`)
   ```python
   class RoscDebugEmitter:
       def __init__(self, source_file):
           self.source_file = source_file
           self.mappings = []  # (ros_line, rosc_file, rosc_line, text)
       
       def add_mapping(self, ros_line, rosc_loc):
           """Map generated .ros line to source .rosc location"""
           pass
       
       def write(self, output_path):
           """Write .rosc.debug file"""
           # Format:
           # VERSION: 1
           # SOURCE: path/to/file.rosc
           # MAPPINGS:
           # [ros_line] [rosc_file] [rosc_line] [original_text]
           pass
   ```

5.3. **Emit Debug Info During Code Generation** (`rospocc/emitter.py`)
   - Track line numbers in output .ros file
   - For each emitted instruction, record mapping
   - Write .rosc.debug alongside .ros

5.4. **Consume .rosc.debug in Rospoas** (`rospoas/preprocessor.py`)
   - When processing .ros files from rospocc, check for .rosc.debug
   - If present, load mappings
   - Enhance origin_map with rospocc source info
   - Mark instructions with `is_from_rospocc=True`

### Phase 6: VM Debug Information Usage

**Files to modify:**
- `rospovm/RospOSVM.cpp`
- `rospovm/RospOSVM.h`
- `rospovm/Logger.cpp`

**Tasks:**

6.1. **Debug Info Access**
   ```cpp
   class RospOSVM {
       DebugEntry* get_debug_info(uint32_t address);
       std::string format_source_location(uint32_t address);
       std::string get_original_instruction(uint32_t address);
   };
   ```

6.2. **Enhanced Error Reporting**
   - Include source file/line in error messages
   - Show original instruction text
   - Display include chain for nested includes

6.3. **Debugger Integration**
   - Map PC to source location
   - Show source code in debugger view
   - Support breakpoints by source line

### Phase 7: Testing & Validation

**Tasks:**

7.1. **Unit Tests**
   - Test V2 binary writing
   - Test V2 binary reading
   - Test V1 backward compatibility
   - Test debug info parsing
   - Test source tracking through pipeline

7.2. **Integration Tests**
   - Compile sample .ros with debug info
   - Compile sample .rosc with debug info
   - Verify debug info in VM
   - Test error reporting with debug info

7.3. **Test Cases**
   - Simple program with no includes
   - Program with includes (test include chain)
   - Program with pseudo-instructions (test expansion tracking)
   - Program with optimizations (test optimization tracking)
   - rospocc program (test .rosc.debug integration)

## File Changes Summary

### New Files
- `rospoas/debug_writer.py` - Debug segment text format writer
- `rospocc/debug_emitter.py` - Rospocc debug sidecar emitter
- `rospovm/DebugParser.h` - Debug info parser header
- `rospovm/DebugParser.cpp` - Debug info parser implementation
- `.github/binary_v2.prompt.md` - This document

### Modified Files
- `rospoas/ir.py` - Enhanced source tracking
- `rospoas/transformer.py` - text storage
- `rospoas/lower.py` - Pseudo-instruction tracking
- `rospoas/optimizer.py` - Optimization tracking
- `rospoas/compile.py` - Debug info collection & V2 writing
- `rospoas/grammar_parser.py` - Line info in origin_map
- `rospocc/transformer.py` - Source tracking
- `rospocc/parser.py` - Debug sidecar generation
- `rospocc/emitter.py` - Line mapping
- `rospovm/Binary.h` - V2 structures
- `rospovm/Binary.cpp` - V2 loader
- `rospovm/RospOSVM.h` - Debug info access
- `rospovm/RospOSVM.cpp` - Debug info usage
- `rospovm/Logger.cpp` - Enhanced error reporting

## Implementation Order

1. **Phase 1**: Core data structures (IR, Binary structures)
2. **Phase 2**: Debug info collection in rospoas
3. **Phase 3**: Write V2 binary format
4. **Phase 4**: Read V2 binary format (with V1 compat)
5. **Phase 5**: Rospocc integration
6. **Phase 6**: VM debug info usage
7. **Phase 7**: Testing

## Example Debug Segment

For a simple program:
```assembly
; main.ros line 42
.SEG 0x00000000
main:
    LLI r1, 0x12345678  ; pseudo-instruction
    ADD r2, r1, r1
    JMP done
```

After compilation, debug segment:
```
DEBUG_VERSION: 1
SEGMENT_ADDRESS: 0x00000000
ENCODING: UTF-8

0x00000000 0x00000001 0 42 5 "LLI r1, 0x12345678"
0x00000000 0x00000001 0 42 5 "ADDI r1, r0, 0x1234" 
0x00000004 0x00000001 0 42 5 "SHLI r1, r1, 16"
0x00000008 0x00000001 0 42 5 "ORI r1, r1, 0x5678"
0x0000000C 0x00000000 0 43 5 "ADD r2, r1, r1"
0x00000010 0x00000001 0 44 5 "JMP done"
FILES:
0 /home/user/project/main.ros
```

## Notes

- Debug segments do not consume memory addresses (address field = 0 or parent segment addr)
- Text format allows easy inspection and debugging
- File paths are stored once in file table, referenced by ID
- Original text is quoted and escaped (like JSON strings)
- VM can merge debug info from multiple debug segments by address
- Backward compatibility: V1 binaries simply have no debug segments
- Pseudoinstructions like LLI do not increase the PC, they are stored at the address that they would be if they were real instructions. The instructions that make it up are then stored after it. Note that this means that the first instruction of the pseudoinstruction will be at the same address as the pseudoinstruction. 

## Future Enhancements

- Compression for debug segments
- Source file embedding option
- Variable/register name tracking
- Call stack unwinding information
- Performance profiling metadata
- Symbol table segment
