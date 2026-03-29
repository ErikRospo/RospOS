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
    void onExportRangeClicked();

private:
    void createUI();
    void populateMemory(uint32_t address);

    VMController *vmController;
    QTableWidget *memoryTable;
    QLabel *titleLabel;
    QLineEdit *addressInput;
    QLineEdit *exportStartInput;
    QLineEdit *exportEndInput;
    uint32_t currentAddress;
    uint32_t lastAddress = 0;
    uint8_t lastSize = 0;
    bool lastIsWrite = false;
    bool hasLastHighlight = false;
    uint32_t predictedAddress = 0;
    uint8_t predictedSize = 0;
    bool predictedIsWrite = false;
    bool hasPredictedHighlight = false;
};

#endif // MEMORY_VIEW_H
