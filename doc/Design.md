# RospOS 32-bit RISC CPU ISA
By: Erik Rospo

---
geometry: margin=1in
---
Goal:

* 32-bit RISC CPU ISA
* Small OS atop ISA (*RospOS*)
* `sh`-like shell
* `bc`-like calculator
* `TI-84`-like graphing calculator
  * Bresenham's line algorithm on steroids
* `nano`-like text editor
* **Audio**: SID-like synth
* **Display**: 256x256 8-bit framebuffer
* **TTY**: terminal interface

Design principles:

* Orthogonal instruction set
* Load/store architecture (RISC)
* Simple, fixed-size 32-bit instructions
* Memory-mapped I/O for hardware devices
* 16 general-purpose registers

For register file, see [Calling Convention (ABI)](#calling-convention-abi).

!include`incrementSection=0` ./doc/instr_encode.md

## Memory Map

| Address Range            | Purpose                    | Size / Notes                             |
| ------------------------ | --------------------------:| ----------------------------------------:|
| `0x00000000–0x0FFFFFFF`    | RAM                      | Program + stack + heap                   |
| `0x10000000–0x1000FFFF`    | TTY  MMIO                | Read input / write output                |
| `0x20000000–0x2007FFFF`    | Display MMIO             | See [Display](#display) for more details |
| `0x30000000–0x3000FFFF`    | Audio MMIO               | freq, waveform, volume, gate registers   |
| `0x40000000–0x400000FF`    | Block device MMIO        | See [Block Device](#block-device) for more details |
| `0xFFFFFF00–0xFFFFFFFF`    | Interrupt vectors        | Includes reset vector                    |


## Calling Convention (ABI)

Basic register usage:

* `r0`   = hardwired zero 
* `r1-r12` = GP registers (should be preserved across calls)
* `r13` = temp / scratch register (do not rely on value being preserved)
* `r14` = link register (return address)
* `r15` = stack pointer

Arguments can be passed in any of `r1` to `r12`. Arguments beyond 12 should be passed on the stack.
Return values are placed in `r1` (for single return value) or `r1` and `r2` (for two return values). More than two return values should be returned via memory or stack.
Registers that were not used for passing arguments may be used as temporary registers within functions, but their values must be preserved across function calls.
Registers that were used as argument registers may be modified by the callee. If the caller needs to preserve their values, it must save them before the call.

Stack pointer is initialized to top of RAM (`0x0FFFFFFF`) on reset. Stack grows downward. 8-byte alignment. Unaligned accesses cause exceptions.

##  I/O / Virtual Hardware Design

### TTY

* Memory-mapped at `0x10000000`
* Write byte → output
* Read byte → blocking input

### Display

* 128×128 by 8 bits = 16384 bytes at `0x20000000`
* Simple framebuffer: 00RRGGBB, linear addressing

### Audio

* Memory-mapped registers:
  * Frequency
  * Waveform
  * Volume
  * Gate (on/off)
  
### Block Device

* Memory-mapped at `0x40000000`
* Registers:
| Offset | Name        |
|--------|-------------|
| `0x00` | Status      |
| `0x04` | Command     |
| `0x08` | Block ID    |
| `0x0C` | Buffer Addr |
| `0x10` | Block Count |

**Status** register bits:
| Bit | Name       | Description                                       |
|-----|------------|---------------------------------------------------|
| 0   | Busy       | Set when device is processing a command           |
| 1   | Error      | Set if the last command resulted in an error      |
| 2   | Data Ready | Set when data is ready to be read from the buffer |

**Command** register values:
| Value | Name   | Description                           |
|-------|--------|---------------------------------------|
| `0x00` | None   | No operation                         |
| `0x01` | Read   | Read blocks from device into buffer  |
| `0x02` | Write  | Write blocks from buffer to device   |

Writing to the Command register initiates the specified operation. The device will set the Busy bit while processing the command, and clear the busy bit, set the data ready bit (for reads), and clear the command register when the operation is complete. If an error occurs, the device will set the Error bit.

**Block ID**: Logical block number to read/write (0-based)
**Buffer Addr**: Physical address of data buffer in RAM (must be 512-byte aligned)
**Block Count**: Number of blocks to read/write (1-128)

32-bit block ID allows for up to 4 billion blocks. With 512 bytes per block, this supports up to 2 TB of storage.

I don't anticipate needing more than 2 TB for this project, so this is fine. 

Special blocks:
| Block ID | Readable | Writable| Purpose                          |
|----------|----------|---------|----------------------------------|
| `0xFFFFFFFD` | Yes  | No      | Time block (unix ms) |
| `0xFFFFFFFE` | Yes  | No      | RNG block (returns random values) |
| `0xFFFFFFFF` | Yes  | No      | Device info block |

Note: Not-writable blocks will ignore write commands and set the Error bit in the Status register. Given that they're in memory, loads and stores to those addresses will still work as normal, but writes to the block device's Command register with those block IDs will be rejected.

### Reset Behavior

* Clear registers to 0
* Stack pointer (r15) initialized to top of RAM (`0x0FFFFFFF`)
* PC set to value at reset vector (`0xFFFFFFFC`)
* Execution begins
