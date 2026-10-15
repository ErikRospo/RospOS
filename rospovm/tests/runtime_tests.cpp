#include "RospOSVM.h"
#include "TTY.h"
#include "TTYWidget.h"
#include "VMControllerCore.h"

#include <QApplication>
#include <QElapsedTimer>
#include <QEventLoop>
#include <QTemporaryDir>
#include <QTimer>

#include <iostream>
#include <stdexcept>
#include <chrono>
#include <thread>

namespace {
void require(bool condition, const char *message)
{
    if (!condition) throw std::runtime_error(message);
}

void waitForEvents(int ms)
{
    QEventLoop loop;
    QTimer::singleShot(ms, &loop, &QEventLoop::quit);
    loop.exec();
}

void loadProgram(RospOSVM &vm, std::initializer_list<uint32_t> words)
{
    std::vector<char> program;
    for (uint32_t word : words)
        for (int shift : {24, 16, 8, 0}) program.push_back(static_cast<char>(word >> shift));
    vm.resetCpuState();
    vm.loadBinaryAtAddress(program, 0x1000);
    vm.setProgramCounter(0x1000);
}

class TestController : public VMControllerCore
{
public:
    using VMControllerCore::VMControllerCore;
    RospOSVM &machine() { return *vmInstance(); }
};

void testInput(const QString &devicePath)
{
    RospOSVM vm(false, devicePath.toStdString());
    vm.setNonBlockingInput(true);
    // Signed/unsigned byte and halfword reads, plus word reads. An incomplete
    // read must neither consume a prefix nor change PC/registers/history.
    for (uint32_t subOp = 0; subOp <= 4; ++subOp) {
        TTYShutdown();
        int requests = 0;
        TTYSetReadRequestCallback([&]() { ++requests; });
        loadProgram(vm, {0x20210000U | (subOp << 24)}); // load r2, [r1]
        vm.setRegister(1, kTTYBase);
        vm.setRegister(2, 99);
        const uint32_t width = subOp <= 1 ? 1 : (subOp <= 3 ? 2 : 4);
        for (uint32_t byte = 1; byte < width; ++byte) TTYPush(static_cast<uint8_t>('A' + byte - 1));
        QElapsedTimer timer;
        timer.start();
        require(vm.runSteps(10) == 0, "an incomplete read executed");
        require(timer.elapsed() < 100, "TTY read blocked the GUI thread");
        vm.step();
        require(requests == 1, "input focus callback repeated while waiting");
        require(vm.isWaitingForInput() && vm.getProgramCounter() == 0x1000 && vm.getRegister(2) == 99,
                "waiting changed CPU state");
        require(!vm.canStepBackward(), "waiting created a history entry");
        require(TTYHasInput(width - 1), "waiting consumed partial input");
        TTYPush(static_cast<uint8_t>('A' + width - 1));
        require(vm.runSteps(1) == 1 && !vm.isWaitingForInput(), "input did not resume the instruction");
        require(vm.getRegister(2) == (width == 1 ? 0x41U : (width == 2 ? 0x4142U : 0x41424344U)),
                "TTY bytes were reordered or lost");
        require(vm.getProgramCounter() == 0x1004 && !TTYHasInput(1), "input instruction did not commit once");
    }

    TTYShutdown();
    // Reads that cross the TTY boundary count only the bytes inside TTY.
    loadProgram(vm, {0x24210000});
    vm.setRegister(1, kTTYEnd - 1);
    TTYPush('X');
    require(vm.runSteps(1) == 0 && TTYHasInput(1), "boundary read consumed partial input");
    TTYPush('Y');
    require(vm.runSteps(1) == 1 && vm.getRegister(2) == 0x58590000, "TTY boundary read failed");

    TTYShutdown();
    loadProgram(vm, {0x10100007, 0x21320000}); // addi r1, r0, 7; lbu r3, [r2]
    vm.setRegister(2, kTTYBase);
    require(vm.runSteps(10) == 1 && vm.getProgramCounter() == 0x1004, "stalled instruction was counted");
    TTYPush(0xFF);
    require(vm.runSteps(1) == 1 && vm.getRegister(3) == 255, "unsigned input byte was extended incorrectly");

    TTYShutdown();
    loadProgram(vm, {0x20210000});
    vm.setRegister(1, kTTYBase);
    vm.debugMode = true;
    require(vm.runSteps(1) == 0 && vm.isWaitingForInput(), "debug execution did not yield for input");
    vm.debugMode = false;
    TTYPush(0xFF);
    vm.step();
    require(vm.getRegister(2) == UINT32_MAX, "signed input byte was extended incorrectly");

    TTYShutdown();
    // Callbacks may safely replace themselves; they execute outside the lock.
    TTYSetReadRequestCallback([]() { TTYSetReadRequestCallback(nullptr); });
    TTYRequestInput();
    bool rejected = false;
    try { (void)TTYReadHandler(kTTYBase); }
    catch (const std::runtime_error &) { rejected = true; }
    require(rejected, "unexpected synchronous GUI input was not rejected");
}

void testController(const QString &devicePath)
{
    TestController controller(nullptr, devicePath);
    loadProgram(controller.machine(), {0x10220001, 0x3000FFFF}); // increment r2; branch back
    controller.setExecutionSpeedLevel(14);
    int bursts = 0;
    int refreshes = 0;
    QObject::connect(&controller, &VMControllerCore::executionAdvanced, [&]() { ++bursts; });
    QObject::connect(&controller, &VMControllerCore::stateChanged, [&]() { ++refreshes; });
    controller.run();
    waitForEvents(120);
    controller.pause();
    require(bursts > 1 && refreshes > 0 && refreshes <= 12, "UI refresh rate was not bounded");
    require(controller.getRegister(2) > 0, "controller did not execute");
    const uint32_t stoppedValue = controller.getRegister(2);
    const int stoppedRefreshes = refreshes;
    waitForEvents(30);
    require(controller.getRegister(2) == stoppedValue && refreshes == stoppedRefreshes,
            "execution or UI timer remained active after pause");

    // A breakpoint observer can pause immediately, without waiting for UI work.
    const auto breakpoint = QObject::connect(&controller, &VMControllerCore::executionAdvanced,
                                             &controller, &VMControllerCore::pause);
    bursts = refreshes = 0;
    controller.run();
    waitForEvents(30);
    require(!controller.isRunning() && bursts == 1 && refreshes == 1,
            "breakpoint pause failed to flush the final state");
    QObject::disconnect(breakpoint);

    // Browser-style asynchronous input must arrive while execution is waiting.
    TTYShutdown();
    loadProgram(controller.machine(), {0x21310000, 0x10220001, 0x3000FFFF});
    controller.machine().setRegister(1, kTTYBase);
    bursts = 0;
    controller.run();
    waitForEvents(40);
    require(controller.machine().isWaitingForInput() && bursts <= 5, "input wait spun at Max speed");
    QTimer::singleShot(5, []() { TTYPush('Z'); });
    waitForEvents(60);
    controller.pause();
    require(controller.getRegister(3) == 'Z' && controller.getRegister(2) > 0,
            "event-loop input did not resume execution");

    loadProgram(controller.machine(), {0x21310000});
    controller.machine().setRegister(1, kTTYBase);
    controller.step();
    require(controller.getProgramCounter() == 0x1000, "single-step consumed nonexistent input");
    TTYPush('Q');
    controller.step();
    require(controller.getProgramCounter() == 0x1004 && controller.getRegister(3) == 'Q',
            "single-step did not resume on available input");
}

void testDeviceBudget(const QString &devicePath)
{
    RospOSVM vm(false, devicePath.toStdString());
    vm.getMemory().addSpecialRange("SLOW", 0x30000000, 0x30000000,
        SpecialMemoryRange::Type::MMIO, true, false,
        [](uint32_t) -> uint8_t {
            std::this_thread::sleep_for(std::chrono::milliseconds(6));
            return 42;
        });
    loadProgram(vm, {0x21210000, 0x3000FFFF}); // lbu r2, [r1]; branch back
    vm.setRegister(1, 0x30000000);
    require(vm.runSteps(512, 1000) == 1 && vm.getRegister(2) == 42,
            "execution continued after a device operation exhausted the time slice");
}

void testOutput()
{
    TTYWidget widget;
    int edits = 0;
    QObject::connect(widget.document(), &QTextDocument::contentsChanged, [&]() { ++edits; });
    for (int i = 0; i < 8192; ++i) widget.appendOutputByte('x');
    require(widget.toPlainText().isEmpty(), "TTY output was not buffered");
    waitForEvents(40);
    require(widget.toPlainText() == QString(8192, QChar('x')) && edits <= 2,
            "TTY output was not inserted in a batch");
    for (char byte : QByteArray("a\rbc\bD\n")) widget.appendOutputByte(static_cast<uint8_t>(byte));
    waitForEvents(40);
    require(widget.toPlainText().endsWith("abD\n"), "batched TTY control characters changed behavior");
    widget.appendOutputByte('\b'); // Backspace across batches, including a newline.
    waitForEvents(40);
    require(widget.toPlainText().endsWith("abD"), "cross-batch backspace failed");
}
}

int main(int argc, char **argv)
{
    QApplication application(argc, argv);
    QTemporaryDir directory;
    try {
        require(directory.isValid(), "could not create test directory");
        const QString devicePath = directory.filePath("test.blockdev");
        testInput(devicePath);
        testController(devicePath);
        testDeviceBudget(devicePath);
        testOutput();
        TTYShutdown();
        std::cout << "Runtime regression tests passed\n";
    } catch (const std::exception &error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
