#ifndef REGISTER_VIEW_H
#define REGISTER_VIEW_H

#include <QWidget>
#include <QTableWidget>
#include <QLabel>

class VMController;

class RegisterView : public QWidget
{
    Q_OBJECT

public:
    explicit RegisterView(QWidget *parent = nullptr);
    ~RegisterView();

    void setVMController(VMController *controller);
    void refresh();

private:
    void createUI();
    void populateRegisters();

    VMController *vmController;
    QTableWidget *registerTable;
    QLabel *titleLabel;
};

#endif // REGISTER_VIEW_H
