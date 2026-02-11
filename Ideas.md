
TESTS!

Branches that have a register and a constant should be pseudo-op'd to be a LLI, then a branch. 


## Ideas:
Evaluate simple constant expressions at compile time, esp for LLI. (e.g. 256-8 should be evaluated to 248 at compile time)

## Optimizations
### Peephole optimizations
#### LLI + arith/logical op
LLI followed by arith/logical op with the same register should be pseudo-op'd to a single instruction (e.g. LLI r1, 5 followed by ADD r1, r1, r2 should be converted to ADDI r1, r2, 5), if possible.


#### Unneeded generated instructions

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

### Other optimizations
- Remove redundant loads/stores (e.g. if a value is already in a register, don't load it again from memory)
- Remove redundant moves (e.g. if a value is already in a register, don't move it to another register unnecessarily)
- Constant folding (e.g. if an expression can be evaluated at compile time, do so and replace it with the result)
  - This also also be integrated with the constant expression evaluation mentioned above for LLI.
- Very simple dead code elimination
  -  If a value is computed but never used, remove the computation
  -  If a branch is always taken or never taken based on constant conditions, remove the branch and the unreachable code
  -  This is, again, *very basic* dead code elimination, but it can still catch some simple cases and improve performance.


## Tooling:

### VSCode extension
VSCode extension for ros assembly? Syntax highlighting, error checking, etc. 
rosc is just a subset of C, so VSCode's C features just sort of work by default.
 
### Error handling

Better error handling in rospoas/rospocc, with more informative error messages and line numbers.

This includes passing down line number information from the lexer to the parser and then to the code generator, so that errors can be reported with accurate line numbers. Currently, it seems that only directives and labels have line number information, but it would be beneficial to have this for all tokens (even ones generated from pseudo-ops) especially for error reporting in the code generator.