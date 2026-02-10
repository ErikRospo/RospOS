Refactor MULI to shifts if 2^n

CHARACTER MISALIGNMENT IS FROM ASSEMBLER NOT PADDING

TESTS!
In CPP, write out the display memory to a PNG file and assert that it matches expected output
Then run it on every possible character input?

Better error handling in rospoas!

Evaluate simple constant expressions at compile time, esp for LLI. (e.g. 256-8 should be evaluated to 248 at compile time)

Branches that have a register and a constant should be pseudo-op'd to be a LLI, then a branch. 

Optimization?
```
.FUNC print_string:
  // prologue (minimal)
  PUSH r14
  LLI r2, 268435456    // init tty_addr
WHILE1:
  LB r3, r1, 0    // deref
  BEQ r3, r0, WHILE_END2  
  // This next instruction can be removed, as r3 already holds the value of *str.
  // WE CAN OPTIMIZE THIS!
  LB r3, r1, 0    // load *str for __sb 
  SB r3, r2, 0    // intrinsic __sb
  JMP WHILE1
WHILE_END2:
  // epilogue and return
  ADDI r1, r0, 0  // ensure r1=0
  POP r14
  RET
```

VSCode extension for rospoas? Syntax highlighting, error checking, etc. 

LLI followed by arith/logical op with the same register should be pseudo-op'd to a single instruction (e.g. LLI r1, 5 followed by ADD r1, r1, r2 should be converted to ADDI r1, r2, 5), if possible.