#include <cstdint>
#include <iostream>
#include <string>
#include <vector>

#include "Binary.h"
#include "RospOSVM.h"
#include "Shutdown.h"
#include "TTY.h"

int main(int argc, char *argv[])
{
    std::cerr << "RospOS Virtual Machine starting..." << std::endl;
    if (argc < 2)
    {
        std::cerr << "Usage: " << argv[0] << " <file.rosp> [--verbose] [--step]" << std::endl;
        return 1;
    }

    std::string rospFile = argv[1];
    
    bool verboseMode = false;
    bool stepMode = false;
    for (int i = 2; i < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--verbose") {
            verboseMode = true;
        } else if (arg == "--step") {
            stepMode = true;
        }
    }

    Binary binary;
    binary = binary.load_binary(rospFile);

    RospOSVM vm(verboseMode);
    // Install SIGINT handler to request shutdown on Ctrl+C from the terminal
    installSigintHandler();
    // Start TTY background reader
    TTYStart();
    for (const auto &segment : binary.segments)
    {
        if (verboseMode)
        {
            std::cout << "Loading segment at address 0x" << std::hex << segment.address
                      << " with size " << std::dec << segment.data.size() << " bytes." << std::endl;
        }
        vm.loadBinaryAtAddress(std::vector<char>(segment.data.begin(), segment.data.end()), segment.address);
    }
    std::cout << "Loaded. Starting execution..." << std::endl;

    if (stepMode) {
        std::cout << "Press Enter to step, 'q' to quit." << std::endl;
    }
    
    char ch = 0;
    while (!shouldShutdown()) {
        // SDL events are handled in the display thread; main loop just steps the VM
        if (stepMode) {
            std::cin.get(ch);
            if (ch == 'q') {
                break;
            }
        }
        vm.step();
    }
    
    // Shutdown helpers
    TTYShutdown();
    std::cout << "Shutdown complete." << std::endl;
    
    return 0;
}