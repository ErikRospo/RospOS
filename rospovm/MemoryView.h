#ifndef MEMORY_VIEW_H
#define MEMORY_VIEW_H

#include <QWidget>
#include <QTableWidget>
#include <QLabel>
#include <QLineEdit>
#include <cstdint>

class VMController;

class MemoryView : public QWidget
{
    Q_OBJECT

public:
    explicit MemoryView(QWidget *parent = nullptr);
    ~MemoryView();

    void setVMController(VMController *controller);
    void refresh();

private slots:
    void onAddressChanged();

private:
    void createUI();
    void populateMemory(uint32_t address);

    VMController *vmController;
    QTableWidget *memoryTable;
    QLabel *titleLabel;
    QLineEdit *addressInput;
    uint32_t currentAddress;
};

#endif // MEMORY_VIEW_H
