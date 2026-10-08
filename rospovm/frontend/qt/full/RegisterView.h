#ifndef REGISTER_VIEW_H
#define REGISTER_VIEW_H

#include "BreakpointEvaluator.h"

#include <QWidget>
#include <QTableWidget>
#include <QLabel>
#include <QLineEdit>

class VMController;

class RegisterView : public QWidget
{
    Q_OBJECT

public:
    RegisterView(QWidget *parent = nullptr);
    ~RegisterView();

    void setVMController(VMController *controller);
    void refresh();
    void checkBreakpoint();
    void addPCBkpt(uint32_t pc);
    void removePCBkpt(uint32_t pc);
private:
    void createUI();
    void populateRegisters();
    void onBkptEdited();
    void updateBkptCtx();

    VMController *vmController;
    QTableWidget *registerTable;
    QLabel *titleLabel;
    QLineEdit *bkptLineEditor;

    BreakpointEvaluator breakpointEvaluator;
};

#endif // REGISTER_VIEW_H
