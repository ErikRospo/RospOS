
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
  LB r4, r1, 0    // load *str for __sb
  SB r4, r2, 0    // intrinsic __sb
  // This will be hard to guarantee that there will be no side effects, but in cases where we just loaded a value into a register and then need that value again, we can reuse the register instead of loading it again from memory. In this case, we loaded *str into r3, and then we need to use that value again for the __sb intrinsic. Instead of loading it again into r4, we can just reuse r3 for the __sb intrinsic, which would eliminate the redundant load instruction.
  
  LLI r5, 1    // load immediate 1
  ADD r6, r1, r5    // binop +
  ADDI r1, r6, 0    // assign str
  // ^ These three lines can be optimized into just one line: ADDI r1, r1, 1 --- we can directly add the immediate to the register without needing to load the immediate into another register and then add it. This is a common optimization for simple arithmetic operations with constants, and it would eliminate the need for the LLI and the additional ADD instruction, resulting in more efficient code.
  // Because we're the compiler, we know that we just allocated r5 and r6 for this specific purpose and they aren't used anywhere else, so we can safely eliminate them and just do the addition directly on r1 with the immediate value.
  JMP WHILE1
WHILE_END2:
  // epilogue and return
  ADDI r1, r0, 0  // ensure r1=0
  POP r14
  RET
```


```

.FUNC main:
  PUSH r14
  LLI r2, 5    // init x
  LLI r3, 10    // init y
  LLI r4, 0    // zero init result
  PUSH r2    // save caller temp
  PUSH r3    // save caller temp
  PUSH r4    // save caller temp
  LLI r1, str_7    // load immediate str_7
  CALL print_string
  //These duplicate lines can be optimized out.
  POP r4    // restore caller temp
  POP r3    // restore caller temp
  POP r2    // restore caller temp
  PUSH r2    // save caller temp
  PUSH r3    // save caller temp
  PUSH r4    // save caller temp
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


## Compiler optimization

How do we optimize the compiler itself? The current implementation barely works, but it's quite slow, even for small programs. Some ideas for improving the performance of the compiler include:
- Parallelizing certain parts of the compilation process 
  - Parsing and code generation could potentially be done in parallel for different functions or modules?
  - Would require careful handling of shared data and register allocation, but could significantly reduce compilation time for larger programs.
- Caching files
  - Incremental compilation (only recompile files that have changed since the last compilation)
  - Caching intermediate results (e.g. the AST or the generated code for a function) so that if the same function is compiled again with the same source code, we can reuse the cached result instead of recompiling it from scratch.
  - This would require changing how includes are handled, as we would need to track dependencies between files and invalidate the cache when a file changes. But it could significantly speed up compilation for larger projects where only a few files are changed at a time.