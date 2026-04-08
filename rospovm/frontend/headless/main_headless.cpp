#include "RospOSVM.h"
#include "Logger.h"
#include "Shutdown.h"
#include "ExecutionBackend.h"

#include <cstdint>
#include <iostream>
#include <stdexcept>
#include <string>

namespace {

void printUsage(const char *argv0)
{
    std::cerr << "Usage: " << argv0 << " <program.rosp> [--max-steps N] [--debug] [--backend interpreter|jit]\n";
}

} // namespace

int main(int argc, char *argv[])
{
    if (argc < 2) {
        printUsage(argv[0]);
        return 2;
    }

    std::string binaryPath;
    uint64_t maxSteps = 10000000ULL;
    bool debugMode = false;
    ExecutionBackend backend = ExecutionBackend::Interpreter;

    for (int i = 1; i < argc; ++i) {
        const std::string arg(argv[i]);
        if (arg == "--max-steps") {
            if (i + 1 >= argc) {
                std::cerr << "Missing value for --max-steps\n";
                return 2;
            }
            try {
                maxSteps = std::stoull(argv[++i]);
            } catch (const std::exception &) {
                std::cerr << "Invalid numeric value for --max-steps\n";
                return 2;
            }
        } else if (arg == "--debug") {
            debugMode = true;
        } else if (arg == "--jit") {
            backend = ExecutionBackend::Jit;
        } else if (arg == "--interpreter") {
            backend = ExecutionBackend::Interpreter;
        } else if (arg == "--backend") {
            if (i + 1 >= argc) {
                std::cerr << "Missing value for --backend\n";
                return 2;
            }
            const std::string value(argv[++i]);
            if (!parseExecutionBackend(value, backend)) {
                std::cerr << "Invalid backend value: " << value << " (expected interpreter|jit)\n";
                return 2;
            }
        } else if (!arg.empty() && arg[0] == '-') {
            std::cerr << "Unknown option: " << arg << "\n";
            printUsage(argv[0]);
            return 2;
        } else if (binaryPath.empty()) {
            binaryPath = arg;
        } else {
            std::cerr << "Unexpected argument: " << arg << "\n";
            printUsage(argv[0]);
            return 2;
        }
    }

    if (binaryPath.empty()) {
        printUsage(argv[0]);
        return 2;
    }

    installSigintHandler();
    Logger::instance().setLogLevel(debugMode ? Logger::DEBUG : Logger::INFO);

    try {
        RospOSVM vm(debugMode, backend);
        vm.loadBinaryFromFile(binaryPath);

        uint64_t steps = 0;
        constexpr uint64_t kHeadlessBatchSize = 4096;
        while (!shouldShutdown()) {
            if (steps >= maxSteps) {
                Logger::instance().error(
                    QString::fromStdString("Step limit reached before shutdown: " + std::to_string(maxSteps))
                );
                return 124;
            }

            const uint64_t remaining = maxSteps - steps;
            const uint64_t batch = (remaining < kHeadlessBatchSize) ? remaining : kHeadlessBatchSize;
            const uint64_t executed = vm.runSteps(batch);
            steps += executed;

            if (executed == 0) {
                break;
            }
        }

        Logger::instance().info(
            QString::fromStdString("Headless run completed in " + std::to_string(steps) + " steps")
        );
        return 0;
    } catch (const std::exception &e) {
        Logger::instance().error(QString("Headless run failed: %1").arg(e.what()));
        return 1;
    }
}
