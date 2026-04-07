#include "VMControllerCore.h"

#include "InstructionDecoder.h"
#include "Shutdown.h"

#include <QElapsedTimer>
#include <QFile>

VMControllerCore::VMControllerCore(QObject *parent)
    : QObject(parent), vm(std::make_unique<RospOSVM>(false)), running(false)
{
    executionTimer.setSingleShot(true);
    connect(&executionTimer, &QTimer::timeout, this, &VMControllerCore::onExecutionTick);
}

VMControllerCore::~VMControllerCore() = default;

bool VMControllerCore::loadBinaryFile(const QString &filePath)
{
    try {
        vm->loadBinaryFromFile(filePath.toStdString());
        loadedBinaryPath = filePath;

        emit stateChanged();
        emit error(QString("Binary loaded successfully"));
        return true;
    } catch (const std::exception &e) {
        emit error(QString("Failed to load binary: %1").arg(e.what()));
        return false;
    }
}

uint32_t VMControllerCore::step()
{
    try {
        const uint32_t executedInstructions = vm->step();
        emit stateChanged();
        return executedInstructions;
    } catch (const std::exception &e) {
        emit error(QString("Execution error: %1").arg(e.what()));
        emit executionStopped();
        running = false;
        return 0;
    }
}

void VMControllerCore::stepBackward()
{
    try {
        if (!vm->stepBackward()) {
            emit error("No previous VM state available.");
            return;
        }
        emit stateChanged();
    } catch (const std::exception &e) {
        emit error(QString("Reverse execution error: %1").arg(e.what()));
        emit executionStopped();
        running = false;
    }
}

void VMControllerCore::run()
{
    if (running) {
        return;
    }

    running = true;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();
    emit executionStarted();
    scheduleNextExecutionTick();
}

void VMControllerCore::pause()
{
    executionTimer.stop();
    running = false;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();
    emit executionStopped();
}

bool VMControllerCore::restart()
{
    executionTimer.stop();
    running = false;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();

    if (loadedBinaryPath.isEmpty()) {
        emit error(QString("No binary loaded to restart"));
        emit executionStopped();
        return false;
    }

    try {
        vm->loadBinaryFromFile(loadedBinaryPath.toStdString());
        emit stateChanged();
        emit executionStopped();
        return true;
    } catch (const std::exception &e) {
        emit error(QString("Failed to restart binary: %1").arg(e.what()));
        emit executionStopped();
        return false;
    }
}

void VMControllerCore::reset()
{
    executionTimer.stop();
    vm = std::make_unique<RospOSVM>(false);
    running = false;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();
    loadedBinaryPath.clear();
    emit stateChanged();
    emit executionStopped();
}

void VMControllerCore::setExecutionSpeedLevel(int level)
{
    if (level < 0) {
        level = 0;
    } else if (level > 10) {
        level = 10;
    }

    speedLevel = level;
    if (running) {
        executionTimer.stop();
        pendingBurstSteps = 0.0;
        throughputTimer.invalidate();
        scheduleNextExecutionTick();
    }
}

bool VMControllerCore::canStepBackward() const
{
    return vm->canStepBackward();
}

int VMControllerCore::executionIntervalMs() const
{
    if (usesBurstExecutor()) {
        return (speedLevel == 10) ? 0 : 8;
    }

    switch (speedLevel) {
    case 0:
        return 500;
    case 1:
        return 1000;
    case 2:
        return 200;
    case 3:
        return 100;
    case 4:
        return 40;
    case 5:
        return 20;
    case 6:
        return 10;
    default:
        return 200;
    }
}

bool VMControllerCore::usesBurstExecutor() const
{
    return speedLevel >= 7;
}

int VMControllerCore::targetInstructionsPerSecond() const
{
    switch (speedLevel) {
    case 0:
        return 2;
    case 1:
        return 1;
    case 2:
        return 5;
    case 3:
        return 10;
    case 4:
        return 25;
    case 5:
        return 50;
    case 6:
        return 100;
    case 7:
        return 250;
    case 8:
        return 1000;
    case 9:
        return 2500;
    case 10:
        return 0;
    default:
        return 10;
    }
}

void VMControllerCore::scheduleNextExecutionTick()
{
    if (!running) {
        return;
    }

    executionTimer.start(executionIntervalMs());
}

void VMControllerCore::onExecutionTick()
{
    if (!running) {
        return;
    }

    if (shouldShutdown()) {
        running = false;
        emit executionStopped();
        return;
    }

    try {
        if (usesBurstExecutor()) {
            constexpr int kMaxBurstInstructions = 2500;
            int instructionsToRun = kMaxBurstInstructions;

            if (speedLevel != 10) {
                const int targetIps = targetInstructionsPerSecond();
                if (!throughputTimer.isValid()) {
                    throughputTimer.start();
                }

                qint64 elapsedMs = throughputTimer.restart();
                if (elapsedMs <= 0) {
                    elapsedMs = executionIntervalMs();
                }

                pendingBurstSteps += (static_cast<double>(targetIps) * static_cast<double>(elapsedMs)) / 1000.0;
                instructionsToRun = static_cast<int>(pendingBurstSteps);
                if (instructionsToRun <= 0) {
                    if (running) {
                        scheduleNextExecutionTick();
                    }
                    return;
                }

                pendingBurstSteps -= static_cast<double>(instructionsToRun);
                if (instructionsToRun > kMaxBurstInstructions) {
                    pendingBurstSteps += static_cast<double>(instructionsToRun - kMaxBurstInstructions);
                    instructionsToRun = kMaxBurstInstructions;
                }
            }

            QElapsedTimer burstTimer;
            burstTimer.start();
            int executedInBurst = 0;
            while (executedInBurst < instructionsToRun) {
                executedInBurst += static_cast<int>(vm->step());
                if (shouldShutdown()) {
                    running = false;
                    emit stateChanged();
                    emit executionStopped();
                    return;
                }
                if (burstTimer.elapsed() >= 8) {
                    if (speedLevel != 10 && executedInBurst < instructionsToRun) {
                        pendingBurstSteps += static_cast<double>(instructionsToRun - executedInBurst);
                    }
                    break;
                }
            }
            emit stateChanged();
        } else {
            vm->step();
            emit stateChanged();
        }
    } catch (const std::exception &e) {
        running = false;
        emit error(QString("Execution error: %1").arg(e.what()));
        emit executionStopped();
        return;
    }

    if (running) {
        scheduleNextExecutionTick();
    }
}

uint32_t VMControllerCore::getProgramCounter() const
{
    return vm->getProgramCounter();
}

uint32_t VMControllerCore::getRegister(int index) const
{
    try {
        return vm->getRegister(index);
    } catch (...) {
        return 0;
    }
}

QString VMControllerCore::getRegisterName(int index) const
{
    static const char *names[] = {
        "R0", "R1", "R2", "R3", "R4", "R5", "R6", "R7",
        "R8", "R9", "R10", "R11", "R12", "R13", "R14", "R15"
    };

    if (index >= 0 && index < 16) {
        return QString(names[index]);
    }
    return QString("R%1").arg(index);
}

uint32_t VMControllerCore::readMemory(uint32_t address) const
{
    try {
        return vm->readMemory(address);
    } catch (...) {
        return 0;
    }
}

uint8_t VMControllerCore::readMemoryByte(uint32_t address) const
{
    try {
        return vm->readMemoryByte(address);
    } catch (...) {
        return 0;
    }
}

uint8_t VMControllerCore::readMemoryByteForInspector(uint32_t address) const
{
    try {
        return vm->readMemoryByteForInspector(address);
    } catch (...) {
        return 0;
    }
}

bool VMControllerCore::exportMemoryRangeToBinary(uint32_t startAddress, uint32_t endAddress, const QString &filePath, QString *errorMessage) const
{
    if (endAddress < startAddress) {
        if (errorMessage) {
            *errorMessage = QString("End address must be greater than or equal to start address.");
        }
        return false;
    }

    QFile outputFile(filePath);
    if (!outputFile.open(QIODevice::WriteOnly)) {
        if (errorMessage) {
            *errorMessage = QString("Failed to open file for writing: %1").arg(outputFile.errorString());
        }
        return false;
    }

    constexpr uint32_t kChunkSize = 4096;
    uint64_t current = startAddress;
    const uint64_t last = endAddress;

    while (current <= last) {
        const uint64_t remaining = (last - current) + 1;
        const int chunkLen = static_cast<int>(remaining < kChunkSize ? remaining : kChunkSize);

        QByteArray buffer;
        buffer.resize(chunkLen);

        for (int i = 0; i < chunkLen; ++i) {
            const uint32_t byteAddress = static_cast<uint32_t>(current + static_cast<uint64_t>(i));
            try {
                buffer[i] = static_cast<char>(vm->readMemoryByteForInspector(byteAddress));
            } catch (...) {
                if (errorMessage) {
                    *errorMessage = QString("Failed to read memory at address 0x%1")
                                        .arg(byteAddress, 8, 16, QChar('0'));
                }
                outputFile.close();
                return false;
            }
        }

        const qint64 bytesWritten = outputFile.write(buffer);
        if (bytesWritten != chunkLen) {
            if (errorMessage) {
                *errorMessage = QString("Failed while writing output file: %1").arg(outputFile.errorString());
            }
            outputFile.close();
            return false;
        }

        current += static_cast<uint64_t>(chunkLen);
    }

    return true;
}

void VMControllerCore::writeMemory(uint32_t address, uint32_t value)
{
    try {
        vm->writeMemory(address, value);
    } catch (...) {
    }
}

bool VMControllerCore::getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const
{
    try {
        return vm->getLastMemoryAccess(address, size, isWrite);
    } catch (...) {
        return false;
    }
}

bool VMControllerCore::getPredictedMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const
{
    try {
        const uint32_t pc = vm->getProgramCounter();
        const uint32_t instruction = vm->readMemory(pc);
        const uint32_t opcode = (instruction >> 28) & 0x0F;
        if (opcode != 0x2) {
            return false;
        }

        const uint32_t subOp = (instruction >> 24) & 0x0F;
        const uint32_t rs = (instruction >> 16) & 0x0F;
        const int32_t offset = static_cast<int16_t>(instruction & 0xFFFF);
        const uint32_t base = vm->getRegister(static_cast<int>(rs));
        address = base + offset;

        switch (subOp)
        {
        case 0x0:
        case 0x1:
            size = 1;
            isWrite = false;
            return true;
        case 0x2:
        case 0x3:
            size = 2;
            isWrite = false;
            return true;
        case 0x4:
            size = 4;
            isWrite = false;
            return true;
        case 0x5:
            size = 1;
            isWrite = true;
            return true;
        case 0x6:
            size = 2;
            isWrite = true;
            return true;
        case 0x7:
            size = 4;
            isWrite = true;
            return true;
        default:
            return false;
        }
    } catch (...) {
        return false;
    }
}

QString VMControllerCore::disassembleInstruction(uint32_t instruction)
{
    RegisterFile regFile;
    std::string disasm = decodeInstruction(instruction, regFile);
    return QString::fromStdString(disasm);
}

std::vector<uint32_t> VMControllerCore::getCodeRange(uint32_t start, uint32_t length) const
{
    std::vector<uint32_t> instructions;
    try {
        for (uint32_t i = 0; i < length; i += 4) {
            uint32_t instruction = vm->readMemory(start + i);
            instructions.push_back(instruction);
        }
    } catch (...) {
    }
    return instructions;
}