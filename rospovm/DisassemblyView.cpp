#include "DisassemblyView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHeaderView>
#include <QFont>
#include <QScrollBar>

DisassemblyView::DisassemblyView(QWidget *parent)
    : QWidget(parent), vmController(nullptr)
{
    createUI();
}

DisassemblyView::~DisassemblyView() = default;

void DisassemblyView::setVMController(VMController *controller)
{
    vmController = controller;
}

void DisassemblyView::createUI()
{
    QVBoxLayout *layout = new QVBoxLayout(this);

    titleLabel = new QLabel("Disassembly (0x10000 - 0x20000)");
    QFont titleFont = titleLabel->font();
    titleFont.setBold(true);
    titleFont.setPointSize(titleFont.pointSize() + 2);
    titleLabel->setFont(titleFont);
    layout->addWidget(titleLabel);

    disassemblyTable = new QTableWidget();
    disassemblyTable->setColumnCount(4);
    disassemblyTable->setHorizontalHeaderLabels({"Address", "Bytes", "Instruction", "Comment"});
    disassemblyTable->setColumnWidth(0, 100);
    disassemblyTable->setColumnWidth(1, 80);
    disassemblyTable->setColumnWidth(2, 200);
    disassemblyTable->setColumnWidth(3, 200);

    // Make the table read-only
    disassemblyTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    disassemblyTable->setSelectionBehavior(QAbstractItemView::SelectRows);

    // Monospace font for disassembly
    QFont monoFont("Courier");
    monoFont.setPointSize(9);
    disassemblyTable->setFont(monoFont);

    layout->addWidget(disassemblyTable);
    setLayout(layout);
}

void DisassemblyView::populateDisassembly()
{
    if (!vmController) {
        return;
    }

    disassemblyTable->setRowCount(0);

    // Load 64 instructions starting from 0x10000
    const uint32_t startAddr = 0x10000;
    const uint32_t numInstructions = 64;

    for (uint32_t i = 0; i < numInstructions; ++i) {
        uint32_t addr = startAddr + (i * 4);
        
        // Get code from VM
        auto instructions = vmController->getCodeRange(addr, 4);
        if (instructions.empty()) {
            continue;
        }

        uint32_t instruction = instructions[0];

        // Create row in table
        int row = disassemblyTable->rowCount();
        disassemblyTable->insertRow(row);

        // Address column
        QTableWidgetItem *addrItem = new QTableWidgetItem(
            QString("0x%1").arg(addr, 8, 16, QChar('0')));
        disassemblyTable->setItem(row, 0, addrItem);

        // Bytes column
        QTableWidgetItem *bytesItem = new QTableWidgetItem(
            QString("0x%1").arg(instruction, 8, 16, QChar('0')));
        disassemblyTable->setItem(row, 1, bytesItem);

        // Instruction column
        QString disasm = vmController->disassembleInstruction(instruction);
        QTableWidgetItem *instrItem = new QTableWidgetItem(disasm);
        disassemblyTable->setItem(row, 2, instrItem);

        // Comment column (placeholder)
        QTableWidgetItem *commentItem = new QTableWidgetItem("");
        disassemblyTable->setItem(row, 3, commentItem);
    }
}

void DisassemblyView::refresh()
{
    populateDisassembly();
}
