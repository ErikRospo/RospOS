#include "VMController.h"
#include "InstructionDecoder.h"
#include "Binary.h"
#include <QFile>
#include <QDebug>
#include <fstream>

VMController::VMController(QObject *parent)
    : QObject(parent), vm(std::make_unique<RospOSVM>(true)), running(false)
{
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

void VMController::run()
{
    running = true;
    emit executionStarted();
    // Note: For a real implementation, you'd run this in a separate thread
    // to avoid blocking the UI
}

void VMController::pause()
{
    running = false;
    emit executionStopped();
}

void VMController::reset()
{
    vm = std::make_unique<RospOSVM>(true);
    running = false;
    emit stateChanged();
    emit executionStopped();
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

uint32_t VMController::readMemory(uint32_t address) const
{
    try {
        return vm->readMemory(address);
    } catch (...) {
        return 0;
    }
}

void VMController::writeMemory(uint32_t address, uint32_t value)
{
    try {
        vm->writeMemory(address, value);
    } catch (...) {
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
