#ifndef VM_CONTROLLER_CORE_H
#define VM_CONTROLLER_CORE_H

#include <QObject>
#include <QString>
#include <QElapsedTimer>
#include <QTimer>
#include <cstdint>
#include <memory>
#include <vector>

#include "RospOSVM.h"
#include "ExecutionBackend.h"

class VMControllerCore : public QObject
{
    Q_OBJECT

public:
    explicit VMControllerCore(
        QObject *parent = nullptr,
        ExecutionBackend backend = ExecutionBackend::Interpreter);
    ~VMControllerCore() override;

    bool loadBinaryFile(const QString &filePath);

    void step();
    void stepBackward();
    void run();
    void pause();
    bool restart();
    void reset();
    void setExecutionSpeedLevel(int level);
    bool canStepBackward() const;

    uint32_t getProgramCounter() const;
    uint32_t getRegister(int index) const;
    QString getRegisterName(int index) const;
    uint32_t readMemory(uint32_t address) const;
    uint8_t readMemoryByte(uint32_t address) const;
    uint8_t readMemoryByteForInspector(uint32_t address) const;
    bool exportMemoryRangeToBinary(uint32_t startAddress, uint32_t endAddress, const QString &filePath, QString *errorMessage = nullptr) const;
    void writeMemory(uint32_t address, uint32_t value);
    bool getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const;
    bool getPredictedMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const;

    QString disassembleInstruction(uint32_t instruction);
    std::vector<uint32_t> getCodeRange(uint32_t start, uint32_t length) const;

    bool isRunning() const { return running; }

signals:
    void stateChanged();
    void executionStopped();
    void executionStarted();
    void error(const QString &message);

protected:
    RospOSVM *vmInstance() { return vm.get(); }
    const RospOSVM *vmInstance() const { return vm.get(); }

private:
    void onExecutionTick();
    void scheduleNextExecutionTick();
    int executionIntervalMs() const;
    bool usesBurstExecutor() const;
    int targetInstructionsPerSecond() const;

    std::unique_ptr<RospOSVM> vm;
    ExecutionBackend backendMode = ExecutionBackend::Interpreter;
    QTimer executionTimer;
    bool running;
    int speedLevel = 4;
    QElapsedTimer throughputTimer;
    double pendingBurstSteps = 0.0;
    QString loadedBinaryPath;
};

#endif // VM_CONTROLLER_CORE_H