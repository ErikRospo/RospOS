#include "RegisterView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHeaderView>
#include <QFont>

RegisterView::RegisterView(QWidget *parent)
    : QWidget(parent), vmController(nullptr)
{
    createUI();
}

RegisterView::~RegisterView() = default;

void RegisterView::setVMController(VMController *controller)
{
    vmController = controller;
}

void RegisterView::createUI()
{
    QVBoxLayout *layout = new QVBoxLayout(this);

    titleLabel = new QLabel("Registers");
    QFont titleFont = titleLabel->font();
    titleFont.setBold(true);
    titleFont.setPointSize(titleFont.pointSize() + 2);
    titleLabel->setFont(titleFont);
    layout->addWidget(titleLabel);

    registerTable = new QTableWidget();
    registerTable->setColumnCount(3);
    registerTable->setHorizontalHeaderLabels({"Register", "Hex", "Decimal"});
    
    // Configure header to stretch columns to available width
    registerTable->horizontalHeader()->setStretchLastSection(false);
    registerTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    registerTable->horizontalHeader()->setSectionResizeMode(1, QHeaderView::Stretch);
    registerTable->horizontalHeader()->setSectionResizeMode(2, QHeaderView::Stretch);

    // Make the table read-only
    registerTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    registerTable->setSelectionBehavior(QAbstractItemView::SelectRows);

    // Monospace font
    QFont monoFont("Courier");
    monoFont.setPointSize(9);
    registerTable->setFont(monoFont);

    // Set number of rows
    registerTable->setRowCount(16);

    layout->addWidget(registerTable);
    setLayout(layout);
}

void RegisterView::populateRegisters()
{
    if (!vmController) {
        return;
    }

    for (int i = 0; i < 16; ++i) {
        uint32_t value = vmController->getRegister(i);
        QString regName = vmController->getRegisterName(i);

        // Register name column
        QTableWidgetItem *nameItem = new QTableWidgetItem(regName);
        registerTable->setItem(i, 0, nameItem);

        // Hex value column
        QTableWidgetItem *hexItem = new QTableWidgetItem(
            QString("0x%1").arg(value, 8, 16, QChar('0')));
        registerTable->setItem(i, 1, hexItem);

        // Decimal value column
        QTableWidgetItem *decItem = new QTableWidgetItem(QString::number(value));
        registerTable->setItem(i, 2, decItem);
    }
}

void RegisterView::refresh()
{
    populateRegisters();
}
