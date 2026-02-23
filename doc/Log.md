---
title: Log of RospOS
subtitle: Or, why did I make the decisions I did?
author: Erik Rospo
documentclass: extarticle
fontsize: 11pt
papersize: letter
geometry: margin=1in
colorlinks: true
linkcolor: blue
toc: true
toc-depth: 4
---

This is a log of the development of RospOS, focusing on design decisions and implementation details. 

# RospOS Log

## Background: Mini-8

[Mini-8](https://github.com/ErikRospo/Mini-8)

When I first started working on RospOS, I was considering expanding my previous project, Mini-8, to 16 bits. Mini-8, as the name implies, was a small 8-bit CPU with a very simple instruction set. An 8-bit ISA is very easy to implement, but it has significant limitations in terms of performance and usability. At most, I was able to write a simple (yet functional) Tic-Tac-Toe game in it. There would be no way to write anything more complex without a lot of workarounds. Chiefly among them was that I could, at most, have 256 bytes of RAM and 256 instructions (each instruction was 4 bytes long, but the PC indexed instructions, not bytes). 

In addition, Mini-8 had, in hindsight, *a very bad design*. Technically, it had 8 GP registers. But only `r0`-`r3` were actually usable as GP registers. `r4` was the RAM address register, and r5 was the RAM data register. Basically what this means is that when you want to read from RAM address X, you have to load X into `r4`, then read from `r5`. This isn't too bad, and you could even *technically* use `r4` as a GP register if you were careful and didn't depend on `r5`. But it was still a very awkward design, and it made writing code more difficult than it needed to be. `r6` was just unused, which was a waste, plain and simple. `r7` was the program counter, which could be useful for certain things, but it also meant that you couldn't use `r7` as a GP register without horrendous consequences.

Mini-8 also had a few "cheats" in it. For example, `WRT` was an instruction would write the value in the first operand to the terminal, using the second operand as a format specifier. For example, if you wanted to write a number in hexadecimal, you would do `WRT r0, 0b11`. UTF-8 was `0b00`, decimal was `0b01`, and alphabet was `0b10`. There was also `RFT`, which would read a character from the terminal and store it in the destination operand, interpreting it according to the same format specifier.

These instructions were very convenient for writing programs, but also felt very out of place in a CPU. They should have been implemented as functions in the standard library. As the CPU was always going to be run in a VM, there was no real added complexity to implementing these in the VM, but it would have made the CPU design much cleaner and more consistent.

Another issue that eagle-eyed readers may have noticed is that there is a separate concept of "RAM" in Mini-8, which was accessed through `r4`. This address was completely separate from the program counter, which meant that you couldn't execute code from RAM. This was a significant limitation, as it meant that you couldn't load code from disk into RAM and execute it. You would have to hardcode all of your code into the ROM, which was very limiting. It was also impossible to have any constants, as they'd have to be hardcoded as instructions. While not impossible, there is a reason nearly every real-world ISA is a Von Neumann architecture, where code and data share the same address space. This allows for much more flexibility in how code and data are accessed and manipulated, and it is a *fundamental* feature of modern computing.

Some of the design decisions in Mini-8 were very clever, but that didn't balance out the many issues with the design. For example, the conditional instructions encoding was very clever. The condition was kind of encoded in the opcode. The first bit in the subtype negated the condition, the second bit encoded whether it checked for equality, and the third bit encoded whether it checked for LT or GT. This was a very clever way to encode 8 different conditions with only 3 actual logic gates, but given that the computer always be running in a VM written in a high-level language that had no problem executing another few operations, there wasn't any *actual* benefit to this design.

It also had two bits in the opcode that determined whether the register pointers were actually registers, or whether they were immediate values. This was a very clever way to allow for immediate values without having to add more bits to the instruction. All of the instructions used this feature, which made it very flexible. Because Mini-8 was, well, an 8 bit computer, the 8-bit register selector could be used as any immediate value that a register could store. This was sort of convienient, but also didn't really make up for *all* the rest of the design issues.

Overall, Mini-8 was a very fun project, and I learned a lot from it. But it was also a very flawed design, and I knew that if I wanted to create a more usable and performant ISA for a "real" OS, I would need to design a new ISA from scratch. The experience with Mini-8 was invaluable for informing the design of RospOS, as it gave me a lot of insight into what worked and what didn't work in a simple ISA, and it also gave me a lot of experience with implementing a CPU and writing assembly code.

## RospOS ISA

Again, I initially considered just expanding Mini-8 to 16 bits, but I quickly realized that it would be easier to just design a new ISA from scratch. I wanted to keep the ISA as simple as possible, while still being powerful enough to write complex programs in it. I also wanted to avoid any of the "cheats" that I had in Mini-8, and instead only implement things that made sense in a CPU.

16 bits probably would have been enough for a simple OS, but I wanted to have more registers and larger ones, as well as a larger address space, so I decided to go with a 32-bit ISA. This also made it easier to implement certain features, such as function calls and a more complex instruction set.

There were some things that I did really like about Mini-8, such as the orthogonality of the instruction set. For example, in Mini-8, you could use any register as a source or destination for any instruction, which made it very flexible. I wanted to maintain this orthogonality in RospOS, as it makes writing code much easier and more intuitive. Compare this to, e.g. 6502, which had an `A` register that was always used as the destination for arithmetic instructions, and separate `X` and `Y` registers that were only used for indexing. This made writing code in 6502 more difficult, as you had to constantly move values between registers to use them in different instructions. 

Another thing that I wanted to preserve was the fixed 32-bit instruction encoding. This makes it much easier to decode instructions, as you can just read 4 bytes and know that you have a complete instruction. It also makes it easier to implement the CPU, as you don't have to worry about variable-length instructions. By contrast, x86 has a very complex variable-length instruction encoding, which makes it much more difficult to decode instructions and implement the CPU.

### Initial Design

My first step was just listing out instructions that I thought would be useful for a very simple OS. I wanted to have basic arithmetic and logic instructions, obviously. I also wanted to have some basic control flow instructions, such as jumps and calls. In contrast to Mini-8, I wanted to have a single unified address space for both code and data, which meant that I needed to have instructions for loading and storing from memory. MMIO could be implemented as a special case of memory access, so I didn't need to have any special instructions for that. 

For registers, I initially considered going with a very similar design to Mini-8, where there would be 8 GP registers, with r7 being the PC. But I learned that LLVM doesn't really play well with this, so I decided to expand to 16 GP registers, and have the PC be a separate register that isn't directly accessible. This also made it easier to implement function calls, as I could use one of the registers as a link register to store the return address. In the end, I settled on the following register design:

* `r0`   = hardwired zero
* `r1-r12` = GP registers
* `r13` = temp / scratch register 
* `r14` = link register (return address)
* `r15` = stack pointer
  
A few notes about this: 

* All registers are 32 bits, which is also the size of the address space. This means that you can use any register to hold an address, which makes it much easier to work with memory. It also means that you can use any register for arithmetic and logic operations, which makes the instruction set more orthogonal and easier to use.
* The PC is not directly accessible, which means that you can't directly manipulate the program counter. This is an acceptable trade-off, as it simplifies the instruction encoding and makes it easier to implement the CPU.
* `r0` is a hardwired zero register, which means that it always reads as zero, and writes to it are ignored. This is a common feature in many ISAs, as it allows for certain instructions to be simplified. For example, if you want to set a register to zero, you can just do `ADD r1, r0, r0`, which will set `r1` to zero without having to use an immediate value. It also allows for certain instructions to be simplified, such as `BEQ r1, r0, label`, which will branch if `r1` is equal to zero. `ADDI r1, r0, imm` will set `r1` to the immediate value, as it adds zero to it.
* `r13` is a temporary register when using the assembler. The assembler will use `r13` for any temporary values that it needs to generate, such as when loading a 32-bit immediate value into a register. This means that you can't rely on `r13` being preserved across instructions, as the assembler may use it at any time. When using the assembler, it's best to just avoid using `r13` altogether, as it is meant to be a temporary register for the assembler's use. When writing assembly code by hand, you can use `r13` as a temporary register, but you should be aware that the assembler may overwrite it if you use it in a way that requires the assembler to generate extra instructions.
* `r14` is the link register, which is used to store the return address for function calls. The `CALL` pseudoinstruction encodes the appropriate jump instruction to jump to the function, and also stores the return address in `r14`. The `RET` pseudoinstruction encodes a jump to the address stored in `r14`, which allows for returning from function calls.
* `r15` is the stack pointer. The `PUSH` and `POP` pseudoinstructions manipulate the stack pointer to push and pop values from the stack. The stack grows downward, so `PUSH` will decrement the stack pointer and then store the value at the new stack pointer address, while `POP` will load the value from the current stack pointer address and then increment the stack pointer.
* `r1`-`r4` ended up being argument registers, with `r1` also being the return register. As of right now, no function can take more than 4 arguments, but if needed, additional arguments could be passed on the stack.
  * These registers are caller-saved, so any callee that wants to preserve their values after a call must save them before calling the function and restoring them after the call.
* `r5`-`r12` are just general-purpose registers that can be used for whatever. They are callee-saved, so if a function uses them, it must save their values at the beginning of the function and restore them before returning.
  * Again, as mentioned, `r13` is a temporary register that the assembler may use for its own purposes, so it's best to just avoid using it in your code unless you write you code in such a way to avoid the assembler using it. 

### Instruction Set

My instruction set was fairly simple and standard. It wasn't really inspired by any particular ISA, but it was influenced by what I thought would be useful for writing an OS.
Initially, I didn't keep a very consistent encoding for the instructions and their operands. For example, some instructions had a variable number of bits in the opcode encoding, which at one point made it impossible to tell the difference between, say, an `ADD` instruction and a `DIV` instruction with a certain combination of operands. This was a mistake, and I eventually settled on a more consistent encoding for the instructions, which made it much easier to decode instructions and implement the CPU.

!include`incrementSection=2` ./doc/instr_encode.md


### Hardware

For external "hardware", I decided to just have it use memory-mapped I/O (MMIO). This is a common technique used in many real-world ISAs, and it allows for a very simple and consistent way to interact with hardware. Instead of having special instructions for interacting with hardware, you can just read and write to specific memory addresses to interact with the hardware. This also makes it easier to implement the hardware in the VM, as you can just check for reads and writes to specific addresses and handle them accordingly.

The specific MMIO addresses were mostly settled early on, as I had a good idea of what hardware I wanted to implement. I wanted a terminal for input and output, a SID-like sound interface for audio, and a simple 2-bit 128x128 framebuffer for graphics. 

| Address Range              | Purpose                    | Size / Notes                             |
| ------------------------   | --------------------------:| ----------------------------------------:|
| `0x00000000–0x0FFFFFFF`    | RAM                        | Program + stack + heap                   |
| `0x10000000–0x1000FFFF`    | TTY  MMIO                  | Read input / write output                |
| `0x20000000–0x20001000`    | Display MMIO               | 2-bit 128x128 framebuffer                |
| `0x30000000–0x3000FFFF`    | Audio MMIO                 | freq, waveform, volume, gate registers   |
| `0xFFFF0000–0xFFFFFFFF`    | Kernel/Interrupt          |  Stores kernel code and interrupt vectors |

These addresses were chosen somewhat arbitrarily, but they are spaced out enough to allow for future expansion if needed. The RAM is at the beginning of the address space, which makes it easy to load code and data into it. The MMIO addresses are spaced out enough to allow for future expansion if I want to add more hardware in the future. In hindsight, the being at the top of the address space, as any JMPs to the kernel would have to use a large immediate value, which requires 3 instructions to load.


### Revisions

In the end, I made a few revisions to the instructions set and the hardware design, but the overall structure remained the same. I split out instructions into different types. Those types are:

* **R-Type**: Register-Register instructions, which take two source registers and one destination register. These include arithmetic and logic instructions.
* **I-Type**: Register-Immediate instructions, which take one source register, one immediate value, and one destination register. 
  * The immediate value is 16 bits, which allows for a wide range of values to be used without having to load them from memory. This is especially useful for things like loop counters and offsets. However, given that the address space is 32 bits, this means that you can't use an immediate value to directly address memory. You would have to load the address into a register first, and then use that register to access memory. This is an acceptable trade-off, as it keeps the instruction encoding simple and consistent, while still allowing for a wide range of immediate values to be used.
* **L/S-Type**: Load/Store instructions, which take one source register, one immediate value, and one destination register. These are used for loading and storing from memory. The immediate value is used as an offset from the source register, which allows for easy access to local variables and array elements.
* **B-Type**: Branch instructions, which take two source registers and one destination register. These are used for control flow, such as jumps and calls. 
* **J-Type**: Jump instructions take a source and destination register, and an immediate value. These are used for unconditional jumps, as well as calls and returns. The immediate value is used as an offset from the source register, which allows for easy access to local variables and array elements. The destination register stores the current program counter, which allows for easy returns from function calls.
* **S-Type**: Special instructions, which include instructions that don't fit into the above categories, such as `ECALL`, `BREAK` and `NOP`. These are used for special purposes, such as halting the CPU or doing nothing.

All instructions in the same type share the same encoding for the operands, which makes it much easier to decode instructions and implement the CPU. For example, all R-Type instructions have the same encoding for the source and destination registers, which means that you can just read those bits in the instruction and know that they are the source and destination registers for any R-Type instruction. This also makes it easier to implement the assembler, as you can just generate the appropriate instruction encoding based on the type of instruction. 

One note is that the instruction `0x00_00_00_00` encodes the instruction `ADD r0, r0, r0`, or `r0=r0+r0`. `r0` is a constant zero register, so this instruction does nothing. This makes it convienient to initialize memory to all zeros, and it will effectively execute `NOP`s

As for the hardware design, the terminal MMIO was fairly straightforward, as it just needed to support reading input and writing output. As of right now, the audio MMIO is not implemented, as it is the least important and I wanted to focus on getting the CPU and terminal working first. The display MMIO was a bit more complex, especially with the fact that there are 4 pixels in each byte. In the end, I decided to switch over to a 6-bit 256x256 framebuffer, as it actually ends up being easier to implement and use than a 2-bit 128x128 framebuffer. This is because with a 2-bit framebuffer that gets packed into 8-bit bytes, you have to do a lot of bit manipulation to set individual pixels, which is a pain. With a 6-bit framebuffer, each pixel gets its own byte, which makes it much easier to set individual pixels without having to do any bit manipulation. The trade-off is that it uses more memory and wastes 2 bits, but that's not a significant concern given the amount of RAM available. It also allows for a wider range of colors, which is a nice bonus.


### Implementing the VM

The first big milestone was implementing the VM to run the RospOS ISA. I thought this would be a difficult task, but it ended up being fairly straightforward. The fixed 32-bit instruction encoding made it easy to decode instructions, and the orthogonality of the instruction set made it easy to implement the instructions. The MMIO was also fairly easy to implement, as I just had to check for reads and writes to specific addresses and handle them accordingly.

This was also my first time *actually* using C++, and I was pleasantly surprised by how much I enjoyed it. The performance was great, and the language features were very useful for implementing the VM. All of the instructions boiled down to a switch/case block for the major opcode, then execute the appropriate function that had another switch/case block, one per type. For example, all R-Type instructions would be handled by a single function that takes care of decoding the specific instruction and executing it.

Each of the MMIO types were pretty much just a struct that contained a function for handling reads and writes, as well as a start and end address for the MMIO range. The VM would just check for reads and writes to those addresses and call the appropriate function. This made it very easy to implement new hardware in the future, as I could just create a new struct for the new hardware and add it to the list of MMIO handlers. As long as the new hardware had a concept of "reading" and/or "writing" to an address, it could be implemented as an MMIO device without having to add any new instructions to the ISA. This is one of the main benefits of using MMIO, as it allows for a very simple and consistent way to interact with hardware without having to worry about how the hardware is implemented or how it interacts with the CPU. The CPU just reads and writes to specific addresses, and the hardware takes care of the rest.

```c++

using ReadHandler = uint8_t (*)(uint32_t address);
using WriteHandler = void (*)(uint32_t address, uint8_t value);
struct SpecialMemoryRange
{
  uint32_t startAddress;
  uint32_t endAddress;
  enum class Type
  {
      MMIO,
      Reserved
  } type;
  char name[4];
  bool readable;
  bool writable;
  bool contains(uint32_t address) const
  {
      return address >= startAddress && address <= endAddress;
  }
  ReadHandler readHandler;
  WriteHandler writeHandler;
};

```

The VM was also when I had to really lock down the instruction encoding, as I needed to be able to decode instructions in a way that was consistent and unambiguous. This is when I settled on the final instruction encoding, which has a fixed 32-bit format for all instructions, with specific bits reserved for the opcode and operands. This made it much easier to decode instructions and implement the CPU, as I could just read 4 bytes and know that I had a complete instruction.


### Implementing the Assembler

When I had the VM running, I wrote a very simple python program to just write raw machine code into a 4GB file that the VM would load directly as the computer's memory. This was a good way to test the VM, but it was very difficult to write complex programs in this way. I had to manually calculate the byte values for each instruction, which was very error-prone and time-consuming. I also had to manually calculate the addresses for jumps and calls, which was a nightmare. This was helped a bit by the fact that the instruction encoding was reasonably simple, and that in hex, each nybble had a separate meaning. For example, to encode `ADD r1, r2, r3`, I know that `ADD` is the first instruction in the R-Type category and R-type is 0x0X while ADD is 0x00. Then, to encode the destination is `r1`, which is 0x1, the first source is `r2`, which is 0x2, and the second source is `r3`, which is 0x3. This means that the instruction encodes to `0x00_12_30_00`. This was a bit easier than encoding it in binary or if it was a CISC ISA, but it was still very error-prone and difficult to write complex programs in this way. 

The solution to this was, obviously, to write an assembler that could take a more human-readable assembly language and convert it into the raw bytes that the VM could execute. This was a much more complex task than I initially anticipated, as I had to implement a full parser for the assembly language, as well as a way to handle labels and addresses. The parser wasn't hard to implement, in truth. I used a library called [Lark](https://lark-parser.readthedocs.io/en/stable/) to help with the parsing, which made it much easier to implement. 

The largest challenge by far was handling labels and addresses. I had to implement a two-pass assembler, where the first pass would parse the assembly code and collect all the labels and their corresponding addresses, and the second pass would actually generate the machine code, replacing the labels with their corresponding addresses. This was a bit tricky to implement, as I had to make sure that all the labels were correctly resolved and that there were no undefined labels. I also had to handle forward references, where a label is used before it is defined, which added an extra layer of complexity.

Even that wasn't enough, though, as when a label's value was greater than 16 bits, I had to generate extra instructions to load the full 32-bit address into a register before using it. This would then shift over the rest of the code, invalidating all the rest of the calculated addresses. In the worst case, this would lead to the original label being shifted to an even higher address. This would never be more than 3 words long, but it was still a nightmare to implement.

Around this time was when I decided to move init and kernel code into the lower parts of address space, to mostly avoid this issue. This way, most of the code would be within the 16-bit address range, and I wouldn't have to worry about generating extra instructions for loading addresses. This was a band-aid solution, but it was good enough for my purposes, as I didn't have any plans to write *very* large programs in RospOS at this point. It also made it easier to load the kernel and init code into memory, as I could just load them at the beginning of the address space without having to worry about where they would end up. The top of address space (0xFFFF_FFFC-0xFFFF_FFFF) was reserved for the reset vector, and that's where it stands now. Wherever the reset vector points to is where the CPU will start executing code when it is reset, so it can really be anywhere in the address space.

Once I started working more on the assembler, the cost of writing 4GB of zeros to a file every time I wanted to test something became apparent. It was very slow, and it was also very wasteful in terms of disk space. The solution to this was to implement a system kind of like ELF, where the assembler would generate a file that only contained the sections of code and data that were actually used, along with some metadata about where those sections should be loaded into memory. The VM would then read this file and load the sections into the appropriate places in memory before starting execution. This was a much more efficient way to handle things, as it only required writing the actual code and data to disk, rather than a giant file full of zeros. It also made it easier to manage the code and data, as I could just look at the generated file to see what was actually being loaded into memory. My format was called mmap.txt, and it was incredibly simple:


```
0x00000000: kernel.bin
0xFFFFFFFC: init.bin
```

If you'd believe it, this means to load `kernel.bin` at address `0x00000000`, and `init.bin` at address `0xFFFFFFFC`. The VM would read this file, parse the addresses and filenames, and load the corresponding files into memory at the specified addresses. This was a very simple format, but it was effective for my purposes, as it allowed me to easily manage the code and data that was being loaded into memory without having to worry about writing giant files full of zeros. 

However, it didn't feel very *proper*, and I ended up writing my own custom binary format, `.rosp`, that contained the same information as the mmap.txt file, but that was contained in a single file and was more efficient to read from the VM. 
The format is very simple, it has magic number of `ROSP`, followed by a version number, then the number of segments. Each segment has an address that it'll be loaded at, then the size of the segment, then the actual data for the segment. This format is very simple to read and write, and could easily be extended in the future if I wanted to add more features, such as support for debug info, metadata about the segments, compression, or similar. For now, it just serves as a more efficient way to load code and data into memory without having to worry about writing giant files full of zeros or juggling multiple files.

Apart from the address issue mentioned above, the assembler was fairly straightforward to implement. In the end, I had a multi-step process.

1. Handle `.INC` include directives, which just copy the contents verbatim into the file at the location of the directive. 
2. Parse the assembly code with Lark. This gives me an abstract syntax tree (AST), but it's not in a very useful format for generating machine code.
3. Transform the AST into a more useful format, which is basically just a list of instructions. At this point, it also tries to resolve `.DATA`, `.SPACE`, `.STR`, and similar directives, which just generate the appropriate bytes for those directives.
4. Lower the AST from a list of instructions with labels and pseudo-instructions into a list of actual instructions. 
   - For example, `LLI` is a pseudo-instruction that loads any immediate into a register, whether it's a label, an address, or just a large immediate value. The assembler will figure out which one it is and generate the appropriate instructions to load it into the register.
   - While there are no actual immediate equivalents for `SUB`, `MUL`, `DIV`, and `REM`, the assembler will automatically convert them into the appropriate instructions to handle the immediate value. For example, `SUBI r1, r2, imm` will be converted into `LLI r13, imm` followed by `SUB r1, r2, r13`. This is also where `r13` being a temporary register for the assembler comes into play, as it can be used for these kinds of transformations without having to worry about overwriting any values that the programmer is using in their code. Again, if you know how the assembler uses `r13`, it is technically possible to use it in your code, but it's best to just avoid it altogether, as it is meant to be a temporary register for the assembler's use.
5. Layout the IR in memory. This handles `.SEG` directives, labels, and similar. It lays out how large everything is, but at this point, the instructions and data still haven't been written in memory. 
6. Encode the instructions into their final byte form
  - This is where the actual machine code is generated, and where the final addresses for labels are resolved. At this point, the assembler's map of where everything is is finalized, so it can generate the final machine code with the correct addresses for labels and data. Any pseudo-instructions that require generating extra instructions were handled in step 4, so all that's left is to generate the final machine code for each instruction, which is a straightforward process of encoding the opcode and operands into the appropriate bits in the instruction encoding.
7. Finally, the generated machine code is written to a `.rosp` file, with the magic number, version, and segment information, as described. 

The whole process is a bit more complex than I initially anticipated, but it was a fun challenge to implement. It also made it much easier to write complex programs in RospOS, as I could just write assembly code in a more human-readable format, and let the assembler take care of generating the machine code and handling labels, pseudo-instructions, and similar. It also made it much easier to manage the code and data, as I could just look at the machine code to see what was being loaded into memory, rather than having to look at a giant file full of zeros with some bytes here and there that actually mattered.

The end assembly language ended up being fairly simple and easy to read, as I wanted to keep it as close to the actual machine code as possible, while still being human-readable. I also implemented some basic pseudo-instructions, such as `LLI`, for loading large immediates. The assembler is smart enough to know that if you try to load an immediate value that is greater than 16 bits, it will automatically generate the necessary instructions to load the full 32-bit value into a register, or just a single instruction if the value fits within 16 bits. This makes it much easier to write code that uses large immediate values without having to worry about the underlying instruction encoding. Similarly, `PUSH`/`POP` pseudo-instructions that load/store from the stack and change the stack pointer. 

Below is an example of the assembly code for the main program. 

#### Notes

1. LLI is a pseudo-instruction that loads a 32-bit immediate value into a register, using multiple instructions if necessary. In this case, it will load the address of the MOTD string into r1. 
2. CALL is a pseudo-instruction that jumps to the specified address and stores the return address in a register. In this case, it will jump to the PRINT_STRING function, which will print the MOTD string to the terminal. After the function is done, it will return to the next instruction.
3. LLI can be used for either immediates, labels, or addresses, the assembler will figure out which one it is and generate the appropriate instructions to load it into the register. If it can fit in 16 bits, it'll just generate a single ADDI instruction. If it's a label or an address that is greater than 16 bits, it'll generate multiple instructions to load the full 32-bit value into the register. This makes it very flexible and easy to use, as you don't have to worry about the underlying instruction encoding when writing assembly code.
4. There are no immediate break instructions, so we have to load the value into a register and then use that register for the comparison. This is a bit more verbose than having an immediate comparison, but it keeps the instruction encoding simple and consistent.
5. ADDI with an immediate value of 0 is effectively just a MOV instruction, which is useful for moving values between registers without having to worry about the underlying instruction encoding. In this case, we're just moving the X and Y coordinates into r2 and r3, which will be used for drawing the character to the display.

#### Example Assembly Code

```
.SEG 0xFFFF_FFFC
    .DATA 0x0000_0000 // Reset vector points to address 0x00000000
.SEG 0x00000000 // Address space starts at 0x00000000
LLI r1, MOTD  // (#1)

CALL PRINT_STRING // (#2)

LLI r1, PROMPT // Load the address of the prompt string into r1
CALL PRINT_STRING // Print the prompt string to the terminal 
// (#3)
LLI r4, 0 // X coordinate
LLI r5, 0 // Y coordinate
// Labels are markers that can be jumped to or used in a LLI pseudo-instruction. 
MAIN_LOOP:
    LLI r1, TTY_BUFFER
    CALL READ_CHAR
    //READ_CHAR puts the character in r1
    LLI r3, 0x0A // Newline character
    BEQ r1, r3, NEWLINE_LABEL  //(#4)

    LLI r3, 0x7E // "~" character, to clear screen
    BEQ r1, r3, CLEAR_DISPLAY_LABEL
    LLI r3, 0x08 // Backspace character
    BEQ r1, r3, BACKSPACE_LABEL
    // If lowercase, convert to uppercase if alphabetic
    PUSH r2 // Push registers that will be used for calculations.
    PUSH r3
    LLI r2, 0x61 // 'a'
    BLT r1, r2, SKIP_UPPERCASE_CONVERSION
    LLI r2, 0x7A // 'z'
    ADDI r2, r2, 1
    BGE r1, r2, SKIP_UPPERCASE_CONVERSION
    LLI r2, 0x20
    SUB r1, r1, r2 // Convert to uppercase
SKIP_UPPERCASE_CONVERSION:
    // (#5) Set up registers for drawing character to display
    ADDI r2, r4, 0 // X coordinate
    ADDI r3, r5, 0 // Y coordinate
    PUSH r1
    // Draw character to display
    CALL DRAW_CHAR_TO_DISPLAY
    POP r1
    ADDI r4, r4, 8 // Move X coordinate for next character
    POP r3
    POP r2
    LLI r2, 0x1000_0000 // TTY address
    SB r1, r2, 0 // Echo first character back to TTY
    JMP MAIN_LOOP

NEWLINE_LABEL:
    ADDI r5, r5, 8 // Move Y coordinate down for newline
    LLI r4, 0 // Reset X coordinate to 0
    LLI r1, PROMPT
    CALL PRINT_STRING
    JMP MAIN_LOOP
    
CLEAR_DISPLAY_LABEL:
    LLI r4, 0 // X coordinate
    LLI r5, 0 // Y coordinate
    CALL CLEAR_DISPLAY
    JMP MAIN_LOOP
BACKSPACE_LABEL:
    // Handle backspace: move cursor back and clear character
    ADDI r4, r4, -8
    ADDI r2, r4, 0
    ADDI r3, r5, 0
    CALL CLEAR_CHAR_ON_DISPLAY
    JMP MAIN_LOOP

BREAK_LABEL:
    BREAK


.INC "./common_functions.ros" // Relative to the current file


TTY:
    .DATA 0x1000_0000 // Memory-mapped TTY address
MOTD:
    .STR "WELCOME TO ROSPOS. Copyleft 2026 Erik Rospo\n"
PROMPT:
    .STR "\nROSPOS> "
TTY_BUFFER:
    .SPACE 256 // Buffer for TTY input
    

.SEG 0x0010_0000 
.INC "./font_bitmap.ros"
```
The font bitmap being at `0x0010_0000` is a bit of a hack, as it's to ensure that no matter what instructions get generated, the font bitmap remains aligned, which was an issue I ran into early on. 

At this point, the ABI was still very much in flux, and I was still trying to figure out what the best way to handle function calls and returns was. I eventually settled on a convention where the first 4 arguments to a function would be passed in registers, and any additional arguments would be passed on the stack. The return value would be stored in a register. 

You can also see the assembler directives I implemented, such as `.SEG` for specifying the segment to load code or data into, `.DATA` for specifying data to be loaded into memory, `.STR` for defining strings, and `.SPACE` for reserving space in memory. I also implemented an `.INC` directive for including other assembly files, which is useful for organizing code and reusing common functions.

Out of all of these, `.STR` directive was honestly the hardest to implement, as it required me to implement a way to encode strings into the binary format and to align strings to the 4-byte alignment. This was around the time I really started using Github Copilot to experiment with automating writing code. It ended up being completely useless for debugging issues related to this string issue, as it either hyper-fixated on something that was clearly correct or just generate completely wrong code. For context, the symptom of the issue was that after I would JMP to a label that was after a `.STR` directive, the VM would execute invalid instructions. Copilot was incapable of recognizing that all instructions that were written to the binary that were before the directive were aligned to 4 bytes, and all instructions that were written after the directive were not aligned to 4 bytes, which was the root cause of the issue. It was only after I manually looked at the generated binary in a hex editor that I was able to figure out what the issue was, and then I had to manually write the code to align the strings to 4 bytes, which fixed the issue.

Another issue I had to resolve was the fact that the assembler was taking hex immediates and treating them just like any other integer. That's fine for most cases, but if I'm using a hex value for the binary representation, such as the bitmap values used for the display font. If there were enough leading zeros in the number, it'd get shortened and the following characters would be misaligned. For example, `0x0000_0001` would get shortened to `0x1`, which would then be encoded as a single byte instead of 4 bytes, which would cause all the following data to be misaligned. The solution to this was to implement a special case for hex immediates, where if the immediate value is specified in hex, it will always be treated as the length of the hex value, rather than the actual integer value. This way, `0x0000_0001` would be treated as a 4-byte value, and it would be encoded as 4 bytes in the binary, which would keep everything aligned correctly.


### Implementing the Compiler

The compiler was by far the hardest part of the project. Initially, I tried using LLVM to generate the machine code, but I quickly realized that it was not a good fit for my needs. LLVM is a very powerful and flexible compiler infrastructure, but it is also very complex and difficult to use. I'm sure it is the "correct" tool for this, but it was just too hard to wrap my head around how to generate code.

After struggling with LLVM for a bit, I researched other ways to compile C to a custom ISA, as it seemed like a reasonably common problem that someone else must have solved before. I found a few projects that were similar to what I wanted to do, but they all had their own issues.

- [vbcc](http://www.compilers.de/vbcc.html)
  - VBCC was a very promising project, as it was a C compiler that was designed to be portable to different ISAs. However, it was also very old and had a very complex codebase that was difficult to understand and modify. It also seemed to be focused on compiling to x86, 6502, RISC-V, ARM, and a few other common ISAs. However, this generality (it works from 8-bit to 64-bit ISAs) also meant that it was not optimized for any particular ISA, which made it difficult to adapt to my custom ISA.it would have been a lot of work to adapt their code generation to my needs.
- [tcc](https://bellard.org/tcc/)
  - TCC was another promising project, as it was a very small and simple C compiler that was designed to be easy to understand and modify. However, it was also very focused on compiling to x86, and it was not particularly designed to be portable to other ISAs. 
- [lcc](https://drh.github.io/lcc/)
  - LCC is *old*. It was designed to be retargetable, but I found it to be difficult to understand and modify. 
  
Overall, this was of course, not helped by my lack of experience with compiler design and implementation, as well as my lack of familiarity with C in general. These factors combined to make it very difficult to find a suitable existing compiler that I could adapt to my needs, which ultimately led me to the decision to implement my own compiler from scratch.

To do this, I had to implement a full parser for the C-like language, as well as a way to generate the assembly code from the parsed AST. The parser wasn't trivial to implement, as C has a classically ambiguous grammar that requires lookahead and some amount of "smarts" to parse correctly. I ended up using Lark's Earley parser, which is a general context-free parser that can handle ambiguous grammars, which made possible to implement the parser for C. As of right now, the compiler is a work-in progress, but it is *almost* able to compile very basic programs. 
For example, the following rosc (RospOS C) code compiles to the following assembly:

```c
void print_string(char *str)
{
    int tty_addr = 0x10000000;
    while (*str)
    {
        __sb(tty_addr, *str);
        str = str + 1;
    }
}
```

Assembly:

```
.FUNC print_string:
  // prologue (minimal)
  PUSH r14
  LLI r2, 268435456    // init tty_addr
WHILE1:
  LB r3, r1, 0    // deref
  BEQ r3, r0, WHILE_END2
  LB r3, r1, 0    // load *str for __sb
  SB r3, r2, 0    // intrinsic __sb
  LLI r3, 1    // load immediate 1
  ADD r2, r1, r3    // binop +
  JMP WHILE1
WHILE_END2:
  // epilogue and return
  ADDI r1, r0, 0  // ensure r1=0
  POP r14
  RET
```

Even at this stage, you can still see how the compiler is able to generate assembly that matches the structure of the original C code. This is both an upside and a downside, as it makes it easier to understand the generated assembly, but it also means that the generated assembly is not very optimized. For example, the compiler generates a second `LB r3, r1, 0` instruction to load the value of `*str` for the `__sb` intrinsic, even though it already loaded that value in the previous instruction for the loop condition. Similarly, `LLI r3, 1` followed by `ADD r2, r1, r3` can be optimized to `ADDI r2, r1, 1`. Both are simple optimizations that I can implement in the future, but for now, I'm just focused on getting the basic functionality working.

One approach I didn't consider until very late in the process was to just hijack, say, a RISC-V compiler and then try to parse and patch that to work with my assembly. In hindsight, that may have been easier. It also would have likely just worked. However, I think it was a good learning experience to implement the compiler from scratch, as it forced me to really understand how compilers work and how to generate assembly code from a high-level language. It also gave me a lot of flexibility in terms of how I wanted to design the language and the features I wanted to support, without having to worry about the constraints of an existing compiler. My attempts to patch an existing compiler ended up being harder than anticipated, and given that I'd already spent a while working on my own compiler, sunk cost bias kept me from just switching to that approach, even though it may have been more efficient in the long run.