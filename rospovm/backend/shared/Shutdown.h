#ifndef SHUTDOWN_H
#define SHUTDOWN_H

#include <atomic>

void requestShutdown();
bool shouldShutdown();

// Install a simple SIGINT handler that requests shutdown
void installSigintHandler();

#endif // SHUTDOWN_H
