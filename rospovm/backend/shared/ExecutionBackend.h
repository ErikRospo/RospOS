#ifndef EXECUTION_BACKEND_H
#define EXECUTION_BACKEND_H

#include <string>

enum class ExecutionBackend {
    Interpreter,
    Jit
};

inline const char *executionBackendName(ExecutionBackend backend)
{
    switch (backend) {
    case ExecutionBackend::Interpreter:
        return "interpreter";
    case ExecutionBackend::Jit:
        return "jit";
    default:
        return "interpreter";
    }
}

inline bool parseExecutionBackend(const std::string &value, ExecutionBackend &outBackend)
{
    if (value == "interpreter") {
        outBackend = ExecutionBackend::Interpreter;
        return true;
    }

    if (value == "jit") {
        outBackend = ExecutionBackend::Jit;
        return true;
    }

    return false;
}

#endif // EXECUTION_BACKEND_H