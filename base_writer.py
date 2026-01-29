print("Writing Fibonacci program...")
fib_program = [
    0b0001_0000, 0x10, 0x00, 0x0A,  # ADDI r1, r0, 10 (n = 10)
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
    0b0101_0001, 0x00, 0x00, 0x00   # BREAK
]

# Write the program to memory
print("Writing to kernel.bin...")
with open("kernel.bin", "wb") as f:
    f.write(bytearray(fib_program))
print("Done.")

mmap={
    0xFFFF0000: "kernel.bin"
}
with open("mmap.txt", "w") as f:
    for addr, fname in mmap.items():
        f.write(f"{addr:08X}: {fname}\n")