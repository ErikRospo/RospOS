#ifndef JIT_COMPILER_H
#define JIT_COMPILER_H

#include <cstdint>

class RospOSVM;

namespace jit {

// Stage-0 JIT entry point: today it delegates to VM-native execution.
// This file exists to isolate JIT backend evolution from interpreter code.
class JitCompiler
{
public:
    explicit JitCompiler(RospOSVM &vm);

    void invalidate();
    bool step();
    uint64_t runSteps(uint64_t maxSteps, uint32_t timeBudgetMicros);

private:
    RospOSVM &vm;
};

} // namespace jit

#endif // JIT_COMPILER_H
