Refactor MULI to shifts if 2^n

CHARACTER MISALIGNMENT IS FROM ASSEMBLER NOT PADDING

TESTS!
In CPP, write out the display memory to a PNG file and assert that it matches expected output
Then run it on every possible character input?

Better error handling in rospoas!

Evaluate simple constant expressions at compile time, esp for LLI. (e.g. 256-8 should be evaluated to 248 at compile time)

Branches that have a register and a constant should be pseudo-op'd to be a LLI, then a branch. 

Optimization?


VSCode extension for rospoas? Syntax highlighting, error checking, etc. 

LLI followed by arith/logical op with the same register should be pseudo-op'd to a single instruction (e.g. LLI r1, 5 followed by ADD r1, r1, r2 should be converted to ADDI r1, r2, 5), if possible.