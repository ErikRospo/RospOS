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
    void stepBackward();
    void run();
    void pause();
    void reset();
    bool canStepBackward() const;

    // State queries
    uint32_t getProgramCounter() const;
    uint32_t getRegister(int index) const;
    QString getRegisterName(int index) const;
    uint32_t readMemory(uint32_t address) const;
    uint8_t readMemoryByte(uint32_t address) const;
    uint8_t readMemoryByteForInspector(uint32_t address) const;
    void writeMemory(uint32_t address, uint32_t value);
    bool getLastMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const;
    bool getPredictedMemoryAccess(uint32_t &address, uint8_t &size, bool &isWrite) const;

    // Disassembly
    QString disassembleInstruction(uint32_t instruction);
    std::vector<uint32_t> getCodeRange(uint32_t start, uint32_t length) const;
    
    // Debug information (Phase 6)
    /**
     * Get the source location for the current PC
     * @return String like "main.ros:42" or "unknown"
     */
    QString getCurrentSourceLocation() const;
    
    /**
     * Get the original instruction text for the current PC
     * @return Original source instruction or empty string
     */
    QString getCurrentOriginalInstruction() const;
    
    /**
     * Get source location for any address
     * @param address The memory address
     * @return String like "main.ros:42" or "unknown"
     */
    QString getSourceLocation(uint32_t address) const;

    /**
     * Resolve an address to source file path and 1-based source line.
     * @param address The memory address
     * @param filePath Output source path
     * @param line Output 1-based source line
     * @return true when source metadata exists
     */
    bool getSourceReference(uint32_t address, QString &filePath, uint32_t &line) const;

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
