#ifndef VM_CONTROLLER_H
#define VM_CONTROLLER_H

#include <QObject>
#include <QString>
#include <vector>
#include <memory>
#include <cstdint>
#include "RospOSVM.h"

class VMController : public QObject
{
    Q_OBJECT

public:
    VMController(QObject *parent = nullptr);
    ~VMController();

    // File operations
    bool loadBinaryFile(const QString &filePath);

    // Execution control
    void step();
    void run();
    void pause();
    void reset();

    // State queries
    uint32_t getProgramCounter() const;
    uint32_t getRegister(int index) const;
    QString getRegisterName(int index) const;
    uint32_t readMemory(uint32_t address) const;
    void writeMemory(uint32_t address, uint32_t value);

    // Disassembly
    QString disassembleInstruction(uint32_t instruction);
    std::vector<uint32_t> getCodeRange(uint32_t start, uint32_t length) const;

    bool isRunning() const { return running; }

signals:
    void stateChanged();
    void executionStopped();
    void executionStarted();
    void error(const QString &message);

private:
    std::unique_ptr<RospOSVM> vm;
    bool running;
    uint32_t codeStartAddress = 0x10000;
    uint32_t codeEndAddress = 0x20000;
};

#endif // VM_CONTROLLER_H
