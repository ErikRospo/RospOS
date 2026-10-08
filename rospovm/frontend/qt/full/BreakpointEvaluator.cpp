#include "BreakpointEvaluator.h"

#include "exprtk.hpp"

struct BreakpointEvaluator::Impl
{
    // ExprTk binds variables by reference, so their storage must stay alive
    // until after the expression and symbol table have been destroyed.
    std::array<double, 16> registers{};
    double pc = 0;
    exprtk::symbol_table<double> symbolTable;
    exprtk::expression<double> expression;
    exprtk::parser<double> parser;

    Impl()
    {
        for (std::size_t reg = 0; reg < registers.size(); ++reg)
        {
            symbolTable.add_variable("r" + std::to_string(reg), registers[reg]);
        }
        symbolTable.add_variable("pc", pc);
        expression.register_symbol_table(symbolTable);
    }
};

BreakpointEvaluator::BreakpointEvaluator()
    : impl(std::make_unique<Impl>())
{
}

BreakpointEvaluator::~BreakpointEvaluator() = default;

bool BreakpointEvaluator::compile(const std::string &condition)
{
    exprtk::expression<double> expression;
    expression.register_symbol_table(impl->symbolTable);
    if (!impl->parser.compile(condition, expression))
        return false;

    impl->expression = expression;
    return true;
}

void BreakpointEvaluator::updateContext(const std::array<uint32_t, 16> &registers,
                                      uint32_t pc)
{
    for (std::size_t reg = 0; reg < registers.size(); ++reg)
    {
        impl->registers[reg] = static_cast<double>(registers[reg]);
    }
    impl->pc = static_cast<double>(pc);
}

bool BreakpointEvaluator::matches() const
{
    return impl->expression.value() > 0;
}
