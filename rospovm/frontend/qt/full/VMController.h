#ifndef VM_CONTROLLER_H
#define VM_CONTROLLER_H

#include <QString>
#include <cstdint>

#include "VMControllerCore.h"
#include "ExecutionBackend.h"

class VMController : public VMControllerCore
{
public:
    explicit VMController(QObject *parent = nullptr, ExecutionBackend backend = ExecutionBackend::Interpreter);
    ~VMController() override;

    QString getRegisterAllocationTooltip(int index) const;
    QString getRegisterAllocationTooltipAt(uint32_t address, int index) const;

    QString getCurrentSourceLocation() const;
    QString getCurrentOriginalInstruction() const;
    QString getSourceLocation(uint32_t address) const;
    bool getSourceReference(uint32_t address, QString &filePath, uint32_t &line) const;
};

#endif // VM_CONTROLLER_H
