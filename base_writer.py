print("Writing Fibonacci program...")
fib_program = [
    # Get user input
    0b0001_0000, 0x20, 0x00, 0x01,  # ADDI r2, r0, 1 (r2 = 1 for shifting)
    0b0001_0100, 0x22, 0x00, 0x1C,  # SHLI r2, r2, 28 (prepare TTY address)
    # r2 now holds the TTY address
    0x0001_0000, 0x30, 0x00, 10,  # ADDI r3, r0, 10 (set r3 for CMP to newline and for multiplication)
    0b0001_0000, 0x10, 0x00, 0x00,  # ADDI r1, r0, 0 (initialize r1 to 0 for accumulating input number)
    
    
    0b0010_0000, 0x12, 0x00, 0x00,  # LW r1, r2, 0 (read input from TTY)
    # r1 now has the input character
    # if r1 == newline (10), end reading. r1 will hold the final number.
    0b0011_0000, 0x13, 0x00, +3,  # If r1==10 (newline), end reading and jump forward 3
    #
    0b0001_0000, 0x11, 0xFF, 0xD0,  # ADDI r1, r1, -48 (convert ASCII to number)
    
    0b0000_1110, 0x43, 0x10, 0x00,  # MUL r4, r3, r1 (r4 = r1 * 10)
    
    0b0001_0000, 0x10, 0x00, 10,  # ADDI r1, r0, 10 (n = 10)
    0b0001_0000, 0x20, 0x00, 0x00,  # ADDI r2, r0, 0 (a = 0)
    0b0001_0000, 0x30, 0x00, 0x01,  # ADDI r3, r0, 1 (b = 1)
    0b0001_0000, 0x40, 0x00, 0x01,  # ADDI r4, r0, 1 (i = 1)
    # Loop:
    0b0000_0000, 0x52, 0x30, 0x00,  # ADD r5, r2, r3 (c = a + b)
    0b0000_0000, 0x23, 0x00, 0x00,  # ADD r2, r3, r0 (a = b)
    0b0000_0000, 0x35, 0x00, 0x00,  # ADD r3, r5, r0 (b = c)
    0b0001_0000, 0x44, 0x00, 0x01,  # ADDI r4, r4, 1 (i++)
    0b0011_0010, 0x41, 0xFF, 0xF0 + (15-4),  # BLT r4, r1, -8 (if i < n, loop)
    # Write result to memory:
    0b0010_0111, 0x50, 0x00, 0x00,  # SW r5, r0, 0 (write c to address 0)
    # Write to TTY (must convert to decimal ASCII):
    0b0001_0000, 0x60, 0x00, 10, # ADDI r6, r0, 10 (r6=10 for division/modulo)
    # 0x10000000 is TTY MMIO address
    0b0001_0000, 0x20, 0x00, 0x01,  # ADDI r2, r0, 1 (r2 = 1 for shifting)
    0b0001_0100, 0x22, 0x00, 0x1C,  # SHLI r2, r2, 28 (prepare TTY address) 
    # r2 now holds the TTY address
    # r5 holds the number to print
    
    # Convert to ASCII loop:
    0b0000_1110, 0x15, 0x60, 0x00,  # REM r1, r5, r6 (r1 = r5 % 10)
    0b0001_0000, 0x11, 0x00, 0x30,  # ADDI r1, r1, 48 (convert to ASCII)
    0b0000_1100, 0x55, 0x60, 0x00,  # DIV r5, r5, r6 (r5 = r5 / 10)
    # Store low byte in r1 to memory location at r2+0
    0b0010_0101, 0x12, 0x00, 0x00,  # SW r1, r2, 0 (write ASCII to TTY)
    0b0011_0001, 0x05, 0xFF, 0xF0 + (15-4),  # BNE r5, r0, -12 (if r5 != 0, repeat)
    
    0b0101_0001, 0x00, 0x00, 0x00   # BREAK
]

checkerboard_program=[
    # 0x20000000-0x20000FFF is Display MMIO address
    0b0001_0000, 0x20, 0x00, 0x02,  # ADDI r2, r0, 2 (r2 = 2 for shifting)
    0b0001_0100, 0x22, 0x00, 0x1C,  # SHLI r2, r2, 28 (prepare Display address) 
    # 2 bit monochrome display
    0b0001_0000, 0x10, 0b1100, 0b1100,  # ADDI r1, r0, 0b11001100
    # Loop to fill display
    0b0010_0100, 0x42, 0x00, 0x00,  # SW r1, r2, 0 (write pattern to display)
    0b0001_0000, 0x10, 0x10, 0x01,  # SHLI r1, r1,  (shift pattern left)
    0b0011_0000, 0x00, 0xFF, 0xF0, # Jump back to start of loop or somewhere near there, 0*s are effective NOPS
]
# Write the program to memory
print("Writing to kernel.bin...")
with open("kernel.bin", "wb") as f:
    f.write(bytearray(checkerboard_program))
print("Done.")

mmap={
    0xFFFF0000: "kernel.bin"
}
with open("mmap.txt", "w") as f:
    for addr, fname in mmap.items():
        f.write(f"{addr:08X}: {fname}\n")