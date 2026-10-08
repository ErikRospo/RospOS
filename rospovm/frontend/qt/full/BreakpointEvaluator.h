#ifndef BREAKPOINT_EVALUATOR_H
#define BREAKPOINT_EVALUATOR_H

#include <array>
#include <cstdint>
#include <memory>
#include <string>

// Keep ExprTk's template definitions out of the UI compilation units.
class BreakpointEvaluator
{
public:
    BreakpointEvaluator();
    ~BreakpointEvaluator();

    // Failed compilation keeps the last valid condition active.
    bool compile(const std::string &condition);
    void updateContext(const std::array<uint32_t, 16> &registers, uint32_t pc);
    bool matches() const;

private:
    struct Impl;
    std::unique_ptr<Impl> impl;
};

#endif // BREAKPOINT_EVALUATOR_H
