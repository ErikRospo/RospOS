#include "MemoryView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QFont>
#include <QLabel>

MemoryView::MemoryView(QWidget *parent)
    : QWidget(parent), vmController(nullptr), currentAddress(0x0000)
{
    createUI();
}

MemoryView::~MemoryView() = default;

void MemoryView::setVMController(VMController *controller)
{
    vmController = controller;
}

void MemoryView::createUI()
{
    QVBoxLayout *mainLayout = new QVBoxLayout(this);

    titleLabel = new QLabel("Memory Inspector");
    QFont titleFont = titleLabel->font();
    titleFont.setBold(true);
    titleFont.setPointSize(titleFont.pointSize() + 2);
    titleLabel->setFont(titleFont);
    mainLayout->addWidget(titleLabel);

    // Address input layout
    QHBoxLayout *addressLayout = new QHBoxLayout();
    addressLayout->addWidget(new QLabel("Start Address:"));

    addressInput = new QLineEdit();
    addressInput->setText("0x00000000");
    addressInput->setMaximumWidth(150);
    addressLayout->addWidget(addressInput);
    addressLayout->addStretch();

    connect(addressInput, &QLineEdit::returnPressed, this, &MemoryView::onAddressChanged);

    mainLayout->addLayout(addressLayout);

    // Memory table
    memoryTable = new QTableWidget();
    memoryTable->setColumnCount(17); // Address + 16 bytes

    // Set up header
    QStringList headers;
    headers << "Address";
    for (int i = 0; i < 16; ++i) {
        headers << QString("+%1").arg(i, 1, 16, QChar('0'));
    }
    memoryTable->setHorizontalHeaderLabels(headers);

    // Configure header to stretch columns to available width
    memoryTable->horizontalHeader()->setStretchLastSection(false);
    memoryTable->horizontalHeader()->setSectionResizeMode(0, QHeaderView::ResizeToContents);
    for (int i = 1; i < 17; ++i) {
        memoryTable->horizontalHeader()->setSectionResizeMode(i, QHeaderView::Stretch);
    }

    // Make the table read-only
    memoryTable->setEditTriggers(QAbstractItemView::NoEditTriggers);
    memoryTable->setSelectionBehavior(QAbstractItemView::SelectRows);

    // Monospace font
    QFont monoFont("Courier");
    monoFont.setPointSize(9);
    memoryTable->setFont(monoFont);

    memoryTable->setRowCount(32); // Display 32 rows of 16 bytes each

    mainLayout->addWidget(memoryTable);
    setLayout(mainLayout);
}

void MemoryView::onAddressChanged()
{
    QString text = addressInput->text();
    bool ok;
    uint32_t address = text.startsWith("0x") || text.startsWith("0X")
                           ? text.mid(2).toUInt(&ok, 16)
                           : text.toUInt(&ok, 10);

    if (ok) {
        currentAddress = address;
        populateMemory(currentAddress);
    }
}

void MemoryView::populateMemory(uint32_t address)
{
    if (!vmController) {
        return;
    }

    memoryTable->setRowCount(0);

    // Display 32 rows of 16 bytes each
    for (int row = 0; row < 32; ++row) {
        memoryTable->insertRow(row);

        uint32_t rowAddress = address + (row * 16);

        // Address column
        QTableWidgetItem *addrItem = new QTableWidgetItem(
            QString("0x%1").arg(rowAddress, 8, 16, QChar('0')));
        memoryTable->setItem(row, 0, addrItem);

        // Memory bytes columns
        for (int col = 0; col < 16; ++col) {
            uint32_t byteAddress = rowAddress + col;
            uint8_t value = vmController->readMemory(byteAddress) & 0xFF;

            QTableWidgetItem *byteItem = new QTableWidgetItem(
                QString("%1").arg(value, 2, 16, QChar('0')));
            memoryTable->setItem(row, col + 1, byteItem);
        }
    }
}

void MemoryView::refresh()
{
    populateMemory(currentAddress);
}
