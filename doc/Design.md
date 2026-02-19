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

### Reset Behavior

* Clear registers to 0
* Stack pointer (r15) initialized to top of RAM (`0x0FFFFFFF`)
* PC set to value at reset vector (`0xFFFFFFFC`)
* Execution begins
