#ifndef VM_CONTROLLER_H
#define VM_CONTROLLER_H

#include <QString>
#include <cstdint>
#include <vector>

#include "VMControllerCore.h"

class RegisterView;

struct MallocBlockInfo
{
    uint32_t headerAddress = 0;
    uint32_t payloadAddress = 0;
    uint32_t size = 0;
    bool isFree = false;
};

struct MallocHeapSnapshot
{
    uint32_t baseAddress = 0;
    uint32_t size = 0;
    uint32_t used = 0;
    std::vector<MallocBlockInfo> blocks;
};

class VMController : public VMControllerCore
{
public:
    explicit VMController(QObject *parent = nullptr);
    ~VMController() override;

    QString getRegisterAllocationTooltip(int index) const;
    QString getRegisterAllocationTooltipAt(uint32_t address, int index) const;

    QString getCurrentSourceLocation() const;
    QString getCurrentOriginalInstruction() const;
    QString getSourceLocation(uint32_t address) const;
    bool getSourceReference(uint32_t address, QString &filePath, uint32_t &line) const;
    bool getMallocHeapSnapshot(MallocHeapSnapshot &snapshot) const;
    void setRegisterView(RegisterView *rv)
    {
        registerView = rv;
    };
    RegisterView *getRegisterView()
    {
        return registerView;
    }

private:
    RegisterView *registerView;
};

#endif // VM_CONTROLLER_H
