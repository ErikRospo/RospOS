#ifndef DISASSEMBLY_VIEW_H
#define DISASSEMBLY_VIEW_H

#include <QWidget>
#include <QTableWidget>
#include <QLabel>

class VMController;

class DisassemblyView : public QWidget
{
    Q_OBJECT

public:
    explicit DisassemblyView(QWidget *parent = nullptr);
    ~DisassemblyView();

    void setVMController(VMController *controller);
    void refresh();

private:
    void createUI();
    void populateDisassembly();

    VMController *vmController;
    QTableWidget *disassemblyTable;
    QLabel *titleLabel;
};

#endif // DISASSEMBLY_VIEW_H
