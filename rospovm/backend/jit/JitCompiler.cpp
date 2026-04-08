#include "JitCompiler.h"

#include "RospOSVM.h"

namespace jit {

JitCompiler::JitCompiler(RospOSVM &vmRef)
    : vm(vmRef)
{
}

void JitCompiler::invalidate()
{
    // Placeholder for future compiled-block cache invalidation.
}

bool JitCompiler::step()
{
    vm.step();
    return true;
}

uint64_t JitCompiler::runSteps(uint64_t maxSteps, uint32_t timeBudgetMicros)
{
    return vm.runSteps(maxSteps, timeBudgetMicros);
}

} // namespace jit
