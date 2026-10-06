#include "RegisterView.h"
#include "VMController.h"
#include "exprtk.hpp"

#include <QVBoxLayout>
#include <QHeaderView>
#include <QFont>
#include <QLineEdit>
#include <string>

RegisterView::RegisterView(QWidget *parent)
    : QWidget(parent), vmController(nullptr)
{
    createUI();
}

RegisterView::~RegisterView() = default;

void RegisterView::setVMController(VMController *controller)
{
    vmController = controller;
    populateRegisters();
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

    bkptLineEditor = new QLineEdit();
    bkptLineEditor->setFont(monoFont);
    connect(bkptLineEditor, &QLineEdit::textChanged,
            this, &RegisterView::onBkptEdited);
    layout->addWidget(bkptLineEditor);
    setLayout(layout);
}

void RegisterView::initExprtk()
{
    if (!vmController)
    {
        return;
    }
    for (int reg = 0; reg < 16; ++reg)
    {
        symbol_table.add_variable("r" + std::to_string(reg), breakpointCtx.regs[reg]);
    }
    symbol_table.add_variable("pc", breakpointCtx.pc);
    expression.register_symbol_table(symbol_table);
}

void RegisterView::populateRegisters()
{
    if (!vmController)
    {
        return;
    }

    for (int i = 0; i < 16; ++i)
    {
        uint32_t value = vmController->getRegister(i);
        QString regName = vmController->getRegisterName(i);
        QString tooltip = vmController->getRegisterAllocationTooltip(i);

        // Register name column
        QTableWidgetItem *nameItem = new QTableWidgetItem(regName);
        nameItem->setToolTip(tooltip);
        nameItem->setFlags(nameItem->flags() & ~Qt::ItemIsEditable);
        registerTable->setItem(i, 0, nameItem);

        // Hex value column
        QTableWidgetItem *hexItem = new QTableWidgetItem(
            QString("0x%1").arg(value, 8, 16, QChar('0')));
        hexItem->setFlags(hexItem->flags() & ~Qt::ItemIsEditable);
        hexItem->setToolTip(tooltip);

        registerTable->setItem(i, 1, hexItem);

        // Decimal value column
        QTableWidgetItem *decItem = new QTableWidgetItem(QString::number(value));
        decItem->setToolTip(tooltip);
        decItem->setFlags(decItem->flags() & ~Qt::ItemIsEditable);
        registerTable->setItem(i, 2, decItem);
    }
}

void RegisterView::refresh()
{
    populateRegisters();
    checkBreakpoint();
}

void RegisterView::onBkptEdited()
{
    expression_t new_expression;
    new_expression.register_symbol_table(symbol_table);

    if (!parser.compile(bkptLineEditor->text().toStdString(), new_expression))
        return;

    expression = new_expression;
    return;
}
void RegisterView::updateBkptCtx()
{
    for (int i = 0; i < 16; ++i)
    {
        breakpointCtx.regs[i] = (float)vmController->getRegister(i);
    }

    breakpointCtx.pc = (float)vmController->getProgramCounter();
}
void RegisterView::checkBreakpoint()
{
    if (bkptLineEditor->text().length() == 0)
    {
        return;
    }
    updateBkptCtx();

    if (expression.value() > 0)
    {
        vmController->pause();
    }
    // // vmController->pause();
    // for (int i = 0; i < 16; i++)
    // {

    //     if bkpt and bkpt triggered
    //     pause
    // }
}

/*
 **************************************************************
 *         C++ Mathematical Expression Toolkit Library        *
 *                                                            *
 * Simple Example 07                                          *
 * Author: Arash Partow (1999-2025)                           *
 * URL: https://www.partow.net/programming/exprtk/index.html  *
 *                                                            *
 * Copyright notice:                                          *
 * Free use of the Mathematical Expression Toolkit Library is *
 * permitted under the guidelines and in accordance with the  *
 * most current version of the MIT License.                   *
 * https://www.opensource.org/licenses/MIT                    *
 * SPDX-License-Identifier: MIT                               *
 *                                                            *
 **************************************************************
 */

// // #include <cstdio>
// // #include <string>

// #include "exprtk.hpp"

// template <typename T>
// void logic()
// {
//     typedef exprtk::symbol_table<T> symbol_table_t;
//     typedef exprtk::expression<T> expression_t;
//     typedef exprtk::parser<T> parser_t;

//     const std::string expression_string = "not(A and B) or C";

//     symbol_table_t symbol_table;
//     symbol_table.create_variable("A");
//     symbol_table.create_variable("B");
//     symbol_table.create_variable("C");

//     expression_t expression;
//     expression.register_symbol_table(symbol_table);

//     parser_t parser;
//     parser.compile(expression_string, expression);

//     printf(" # | A | B | C | %s\n"
//            "---+---+---+---+-%s\n",
//            expression_string.c_str(),
//            std::string(expression_string.size(), '-').c_str());

//     for (int i = 0; i < 8; ++i)
//     {
//         symbol_table.get_variable("A")->ref() = T((i & 0x01) ? 1 : 0);
//         symbol_table.get_variable("B")->ref() = T((i & 0x02) ? 1 : 0);
//         symbol_table.get_variable("C")->ref() = T((i & 0x04) ? 1 : 0);

//         const int result = static_cast<int>(expression.value());

//         printf(" %d | %d | %d | %d | %d \n",
//                i,
//                static_cast<int>(symbol_table.get_variable("A")->value()),
//                static_cast<int>(symbol_table.get_variable("B")->value()),
//                static_cast<int>(symbol_table.get_variable("C")->value()),
//                result);
//     }
// }

// int main()
// {
//     logic<double>();
//     return 0;
// }
