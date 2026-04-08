#include "Shutdown.h"
#include <signal.h>
#include <atomic>

static std::atomic<bool> g_shutdownRequested{false};

void requestShutdown()
{
    g_shutdownRequested.store(true);
}

bool shouldShutdown()
{
    return g_shutdownRequested.load();
}

static void sigint_handler(int)
{
    requestShutdown();
}

void installSigintHandler()
{
#if defined(SIGINT)
    struct sigaction sa{};
    sa.sa_handler = sigint_handler;
    sigemptyset(&sa.sa_mask);
    sa.sa_flags = 0;
    sigaction(SIGINT, &sa, nullptr);
#endif
}
