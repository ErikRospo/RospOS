#ifndef REGISTER_VIEW_H
#define REGISTER_VIEW_H

#include "exprtk.hpp"

#include <QWidget>
#include <QTableWidget>
#include <QLabel>
#include <QLineEdit>

class VMController;

struct BreakpointContext {
    // must be double for exprtk, even as cursed as it is.
    std::array<double, 16> regs;
    double pc;
};

typedef exprtk::expression<double> expression_t;
typedef exprtk::parser<double> parser_t;
typedef exprtk::symbol_table<double> symbol_table_t;
class RegisterView : public QWidget
{
    Q_OBJECT

public:
    explicit RegisterView(QWidget *parent = nullptr);
    ~RegisterView();

    void setVMController(VMController *controller);
    void refresh();
    void checkBreakpoint();
private:
    void createUI();
    void populateRegisters();
    void initExprtk();
    void onBkptEdited();
    void updateBkptCtx();

    VMController *vmController;
    QTableWidget *registerTable;
    QLabel *titleLabel;
    QLineEdit *bkptLineEditor;

    BreakpointContext breakpointCtx;
    expression_t expression;
    parser_t parser;
    symbol_table_t symbol_table;
};

#endif // REGISTER_VIEW_H
