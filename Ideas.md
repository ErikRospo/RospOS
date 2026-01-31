## Assembly
### Psuedo instructions
PUSH: SW rs, sp, -4,
     ADDI, sp, sp, -4
ex: PUSH r1

POP: ADDI, sp, sp, 4,
    LW rd, sp, 0
ex: POP r1

LLI: ADDI rd, rd, imm_high
     SHLI rd, rd, 16
     ADDI rd, rd, imm_low
(Load Large Immediate)     

ex: LLI r1, 0x12345678



### Directives
.RAND n
    - Generate n random bytes in the current segment
    - Useful for e.g. seeding RNGs
- ex: .RAND 16  # generates 16 random bytes

.STR "string"
    - Store a null-terminated string in the current segment
    - ex: .STR "Hello, World!"
    - Will generate the bytes for "Hello, World!" followed by a null byte (0x00)
        - 0x48 0x65 0x6C 0x6C 0x6F 0x2C 0x20 0x57 0x6F 0x72 0x6C 0x64 0x21 0x00 
    - Quotes are not included in the stored string. To store a quote character, use the escape sequence \"
    - Single quotes are not special and will be included as-is in the string.
    - Supports standard escape sequences: \n, \t, \\, \", \', \r, \0
  
.SEG address
    - Start a new segment at the specified address
    - All subsequent data and instructions will be placed in this segment until another .SEG directive is encountered
    - ex: .SEG 0x10000000
Idea: if two segs overlap or are contiguous, merge them
"contiguous" of course includes if two are exactly adjacent, but could also include small gaps (e.g. less than 16 bytes) to reduce fragmentation
    - This would require more complex logic to manage segment merging

.FUNC name
    - Defines the start of a function named 'name'
    - A label is automatically created at this point
    - Returns are handled with the JAL and JALR instructions
    - ex: .FUNC my_function
        - This creates a label 'my_function' at the current address
    - To call the function, use JAL r14, my_function
    - The return address is stored in r14 by convention
    - The function can return using JALR r0, r14, 0

.INC "filename"
    - Includes the contents of another assembly file at this point.
    - Filename is relative to the current file's location
    - The included file is processed as if its contents were written directly in place of the .INC directive
    - ex: .INC "common_functions.ros"
        - This will include and assemble the contents of common_functions.ros at this point in the current file
    - This is processed first, before any other assembly or directives in the current file
    - This can be nested, i.e. included files can themselves contain .INC directives
    - Circular includes should be detected and reported as an error
    - Included files share the same namespace for labels and functions as the including file
  