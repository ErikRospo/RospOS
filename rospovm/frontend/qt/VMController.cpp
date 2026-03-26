#include "VMController.h"
#include "InstructionDecoder.h"
#include "Binary.h"
#include "Shutdown.h"
#include <QFile>
#include <QDebug>
#include <QElapsedTimer>
#include <fstream>

VMController::VMController(QObject *parent)
    : QObject(parent), vm(std::make_unique<RospOSVM>(true)), running(false)
{
    executionTimer.setSingleShot(true);
    connect(&executionTimer, &QTimer::timeout, this, &VMController::onExecutionTick);
}

VMController::~VMController() = default;

bool VMController::loadBinaryFile(const QString &filePath)
{
    try {
        std::string path = filePath.toStdString();
        
        // Use the new loadBinaryFromFile method which loads debug info
        vm->loadBinaryFromFile(path);
        
        emit stateChanged();
        emit error(QString("Binary loaded successfully"));
        return true;
    } catch (const std::exception &e) {
        emit error(QString("Failed to load binary: %1").arg(e.what()));
        return false;
    }
}

void VMController::step()
{
    try {
        vm->step();
        emit stateChanged();
    } catch (const std::exception &e) {
        emit error(QString("Execution error: %1").arg(e.what()));
        emit executionStopped();
        running = false;
    }
}

void VMController::stepBackward()
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

void VMController::run()
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

void VMController::pause()
{
    executionTimer.stop();
    running = false;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();
    emit executionStopped();
}

void VMController::reset()
{
    executionTimer.stop();
    vm = std::make_unique<RospOSVM>(true);
    running = false;
    pendingBurstSteps = 0.0;
    throughputTimer.invalidate();
    emit stateChanged();
    emit executionStopped();
}

void VMController::setExecutionSpeedLevel(int level)
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

bool VMController::canStepBackward() const
{
    return vm->canStepBackward();
}

int VMController::executionIntervalMs() const
{
    if (usesBurstExecutor()) {
        // Burst-mode speeds are paced by instruction quotas, not per-instruction delay.
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

bool VMController::usesBurstExecutor() const
{
    return speedLevel >= 7;
}

int VMController::targetInstructionsPerSecond() const
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

void VMController::scheduleNextExecutionTick()
{
    if (!running) {
        return;
    }

    executionTimer.start(executionIntervalMs());
}

void VMController::onExecutionTick()
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
            int stepsToRun = kMaxBurstInstructions;

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
                stepsToRun = static_cast<int>(pendingBurstSteps);
                if (stepsToRun <= 0) {
                    if (running) {
                        scheduleNextExecutionTick();
                    }
                    return;
                }

                pendingBurstSteps -= static_cast<double>(stepsToRun);
                if (stepsToRun > kMaxBurstInstructions) {
                    pendingBurstSteps += static_cast<double>(stepsToRun - kMaxBurstInstructions);
                    stepsToRun = kMaxBurstInstructions;
                }
            }

            QElapsedTimer burstTimer;
            burstTimer.start();
            for (int i = 0; i < stepsToRun; ++i) {
                vm->step();
                if (shouldShutdown()) {
                    running = false;
                    emit stateChanged();
                    emit executionStopped();
                    return;
                }
                if (burstTimer.elapsed() >= 8) { // Limit bursts to ~8ms to keep UI responsive
                    if (speedLevel != 10 && i + 1 < stepsToRun) {
                        pendingBurstSteps += static_cast<double>(stepsToRun - (i + 1));
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

uint32_t VMController::getProgramCounter() const
{
    return vm->getProgramCounter();
}

uint32_t VMController::getRegister(int index) const
{
    try {
        return vm->getRegister(index);
    } catch (...) {
        return 0;
    }
}

QString VMController::getRegisterName(int index) const
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

QString VMController::getRegisterAllocationTooltip(int index) const
{
    try {
        const uint32_t pc = vm->getProgramCounter();
        const RegisterAllocationInfo *alloc = vm->getRegisterAllocation(pc, index);
        if (!alloc) {
            return QString();
        }

        QString kind = QString::fromStdString(alloc->var_kind);
        if (kind.isEmpty()) {
            kind = "local";
        }
        QString text = QString("%1 (%2)")
                           .arg(QString::fromStdString(alloc->variable_name), kind);

        const QString type = QString::fromStdString(alloc->variable_type);
        if (!type.isEmpty()) {
            text += QString("\nType: %1").arg(type);
        }

        const QString origin = QString::fromStdString(alloc->origin);
        if (!origin.isEmpty()) {
            text += QString("\nOrigin: %1").arg(origin);
        }

        if (kind == "temp") {
            text += "\nTemporary calculation";
        }

        return text;
    } catch (...) {
        return QString();
    }
}

QString VMController::getRegisterAllocationTooltipAt(uint32_t address, int index) const
{
    try {
        const RegisterAllocationInfo *alloc = vm->getRegisterAllocation(address, index);
        if (!alloc) {
            return QString();
        }

        QString kind = QString::fromStdString(alloc->var_kind);
        if (kind.isEmpty()) {
            kind = "local";
        }
        QString text = QString("%1 (%2)")
                           .arg(QString::fromStdString(alloc->variable_name), kind);

        const QString type = QString::fromStdString(alloc->variable_type);
        if (!type.isEmpty()) {
            text += QString("\nType: %1").arg(type);
        }

        const QString origin = QString::fromStdString(alloc->origin);
        if (!origin.isEmpty()) {
            text += QString("\nOrigin: %1").arg(origin);
        }

        if (kind == "temp") {
            text += "\nTemporary calculation";
        }

        return text;
    } catch (...) {
        return QString();
    }
}

uint32_t VMController::readMemory(uint32_t address) const
{
    try {
        return vm->readMemory(address);
    } catch (...) {
        return 0;
    }
}

uint8_t VMController::readMemoryByte(uint32_t address) const
{
    try {
        return vm->readMemoryByte(address);
    } catch (...) {
        return 0;
    }
}

uint8_t VMController::readMemoryByteForInspector(uint32_t address) const
{
    try {
        return vm->readMemoryByteForInspector(address);
    } catch (...) {
        return 0;
    }
}

bool VMController::exportMemoryRangeToBinary(uint32_t startAddress, uint32_t endAddress, const QString &filePath, QString *errorMessage) const
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

void VMController::writeMemory(uint32_t address, uint32_t value)
{
    try {
        vm->writeMemory(address, value);
    } catch (...) {
    }
}

bool VMController::getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const
{
    try {
        return vm->getLastMemoryAccess(address, size, isWrite);
    } catch (...) {
        return false;
    }
}

bool VMController::getPredictedMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const
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
        case 0x0: // LB
        case 0x1: // LBU
            size = 1;
            isWrite = false;
            return true;
        case 0x2: // LH
        case 0x3: // LHU
            size = 2;
            isWrite = false;
            return true;
        case 0x4: // LW
            size = 4;
            isWrite = false;
            return true;
        case 0x5: // SB
            size = 1;
            isWrite = true;
            return true;
        case 0x6: // SH
            size = 2;
            isWrite = true;
            return true;
        case 0x7: // SW
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

QString VMController::disassembleInstruction(uint32_t instruction)
{
    // Call the C function directly
    RegisterFile regFile;
    std::string disasm = decodeInstruction(instruction, regFile);
    return QString::fromStdString(disasm);
}

std::vector<uint32_t> VMController::getCodeRange(uint32_t start, uint32_t length) const
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

QString VMController::getCurrentSourceLocation() const
{
    return getSourceLocation(vm->getProgramCounter());
}

QString VMController::getCurrentOriginalInstruction() const
{
    std::string text = vm->getOriginalInstruction(vm->getProgramCounter());
    return QString::fromStdString(text);
}

QString VMController::getSourceLocation(uint32_t address) const
{
    std::string location = vm->formatSourceLocation(address);
    return QString::fromStdString(location);
}

bool VMController::getSourceReference(uint32_t address, QString &filePath, uint32_t &line) const
{
    const DebugEntry *entry = vm->getDebugInfo(address);
    if (!entry) {
        return false;
    }

    std::shared_ptr<Binary> loadedBinary = vm->getLoadedBinary();
    if (!loadedBinary || loadedBinary->debug_map.empty()) {
        return false;
    }

    for (const auto &debugPair : loadedBinary->debug_map) {
        const auto &debugInfo = debugPair.second;
        auto fileIt = debugInfo->file_table.find(entry->file_id);
        if (fileIt != debugInfo->file_table.end()) {
            filePath = QString::fromStdString(fileIt->second);
            line = entry->line;
            return true;
        }
    }

    return false;
}
