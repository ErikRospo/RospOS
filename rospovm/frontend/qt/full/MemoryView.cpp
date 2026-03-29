#include "MemoryView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QFont>
#include <QLabel>
#include <QColor>
#include <QPushButton>
#include <QFileDialog>
#include <QFileInfo>
#include <QDateTime>
#include <QMessageBox>

namespace {
bool parseAddressText(const QString &text, uint32_t &outAddress)
{
    bool ok = false;
    outAddress = text.startsWith("0x") || text.startsWith("0X")
                     ? text.mid(2).toUInt(&ok, 16)
                     : text.toUInt(&ok, 10);
    return ok;
}
}

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

    // Export range controls
    QHBoxLayout *exportLayout = new QHBoxLayout();
    exportLayout->addWidget(new QLabel("Export Range:"));

    exportStartInput = new QLineEdit();
    exportStartInput->setText("0x00000000");
    exportStartInput->setMaximumWidth(120);
    exportStartInput->setToolTip("Start address (hex or decimal)");
    exportLayout->addWidget(exportStartInput);

    exportLayout->addWidget(new QLabel("to"));

    exportEndInput = new QLineEdit();
    exportEndInput->setText("0x000000FF");
    exportEndInput->setMaximumWidth(120);
    exportEndInput->setToolTip("End address (inclusive)");
    exportLayout->addWidget(exportEndInput);

    QPushButton *exportButton = new QPushButton("Export .bin");
    exportLayout->addWidget(exportButton);
    exportLayout->addStretch();

    connect(exportButton, &QPushButton::clicked, this, &MemoryView::onExportRangeClicked);
    connect(exportStartInput, &QLineEdit::returnPressed, this, &MemoryView::onExportRangeClicked);
    connect(exportEndInput, &QLineEdit::returnPressed, this, &MemoryView::onExportRangeClicked);

    mainLayout->addLayout(exportLayout);

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

    memoryTable->setRowCount(16); // Display 16 rows of 16 bytes each

    mainLayout->addWidget(memoryTable);
    setLayout(mainLayout);
}

void MemoryView::onAddressChanged()
{
    const QString text = addressInput->text();
    uint32_t address = 0;

    if (parseAddressText(text, address)) {
        currentAddress = address;
        exportStartInput->setText(QString("0x%1").arg(currentAddress, 8, 16, QChar('0')));
        exportEndInput->setText(QString("0x%1").arg(currentAddress + 0xFFu, 8, 16, QChar('0')));
        populateMemory(currentAddress);
    }
}

void MemoryView::onExportRangeClicked()
{
    if (!vmController) {
        QMessageBox::warning(this, "Export Failed", "VM controller is not available.");
        return;
    }

    uint32_t startAddress = 0;
    uint32_t endAddress = 0;
    if (!parseAddressText(exportStartInput->text(), startAddress)) {
        QMessageBox::warning(this, "Invalid Address", "Start address is invalid.");
        return;
    }
    if (!parseAddressText(exportEndInput->text(), endAddress)) {
        QMessageBox::warning(this, "Invalid Address", "End address is invalid.");
        return;
    }

    if (endAddress < startAddress) {
        QMessageBox::warning(this, "Invalid Range", "End address must be greater than or equal to start address.");
        return;
    }

    const QString defaultName = QString("memory_%1_%2_%3.bin")
                                    .arg(startAddress, 8, 16, QChar('0'))
                                    .arg(endAddress, 8, 16, QChar('0'))
                                    .arg(QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss"));

    QString fileName = QFileDialog::getSaveFileName(
        this,
        "Export Memory Range",
        defaultName,
        "Binary Files (*.bin);;All Files (*)");

    if (fileName.isEmpty()) {
        return;
    }

    QFileInfo info(fileName);
    if (info.suffix().isEmpty()) {
        fileName += ".bin";
    }

    QString errorMessage;
    if (!vmController->exportMemoryRangeToBinary(startAddress, endAddress, fileName, &errorMessage)) {
        QMessageBox::warning(this, "Export Failed", errorMessage);
        return;
    }

    QMessageBox::information(this, "Export Complete", QString("Exported %1 bytes to:\n%2")
        .arg(static_cast<qulonglong>(endAddress) - static_cast<qulonglong>(startAddress) + 1ULL)
        .arg(fileName));
}

void MemoryView::populateMemory(uint32_t address)
{
    if (!vmController) {
        return;
    }

    memoryTable->setRowCount(0);

    // Display 32 rows of 16 bytes each
    for (int row = 0; row < 16; ++row) {
        memoryTable->insertRow(row);

        uint32_t rowAddress = address + (row * 16);

        // Address column
        QTableWidgetItem *addrItem = new QTableWidgetItem(
            QString("0x%1").arg(rowAddress, 8, 16, QChar('0')));
        memoryTable->setItem(row, 0, addrItem);

        // Memory bytes columns
        for (int col = 0; col < 16; ++col) {
            uint32_t byteAddress = rowAddress + col;
            uint8_t value = vmController->readMemoryByteForInspector(byteAddress);

            QTableWidgetItem *byteItem = new QTableWidgetItem(
                QString("%1").arg(value, 2, 16, QChar('0')));

            const bool inLastRange = hasLastHighlight &&
                byteAddress >= lastAddress &&
                byteAddress < (lastAddress + static_cast<uint32_t>(lastSize));
            const bool inPredictedRange = hasPredictedHighlight &&
                byteAddress >= predictedAddress &&
                byteAddress < (predictedAddress + static_cast<uint32_t>(predictedSize));

            if (inLastRange && inPredictedRange) {
                byteItem->setBackground(QColor(100, 95, 135));
            } else if (inPredictedRange) {
                if (predictedIsWrite) {
                    byteItem->setBackground(QColor(180, 80, 80));
                } else {
                    byteItem->setBackground(QColor(80, 130, 180));
                }
            } else if (inLastRange) {
                if (lastIsWrite) {
                    byteItem->setBackground(QColor(220, 120, 120));
                } else {
                    byteItem->setBackground(QColor(120, 170, 220));
                }
            }

            memoryTable->setItem(row, col + 1, byteItem);
        }
    }
}

void MemoryView::refresh()
{
    if (vmController) {
        uint32_t accessAddress = 0;
        uint8_t accessSize = 0;
        bool isWrite = false;
        hasLastHighlight = vmController->getLastMemoryAccess(accessAddress, accessSize, isWrite);
        if (hasLastHighlight) {
            lastAddress = accessAddress;
            lastSize = accessSize;
            lastIsWrite = isWrite;
        }

        uint32_t nextAddress = 0;
        uint8_t nextSize = 0;
        bool nextIsWrite = false;
        hasPredictedHighlight = vmController->getPredictedMemoryAccess(nextAddress, nextSize, nextIsWrite);
        if (hasPredictedHighlight) {
            predictedAddress = nextAddress;
            predictedSize = nextSize;
            predictedIsWrite = nextIsWrite;
        }

        uint32_t jumpBaseAddress = currentAddress;
        bool shouldJump = false;
        if (hasPredictedHighlight) {
            jumpBaseAddress = predictedAddress;
            shouldJump = true;
        } else if (hasLastHighlight) {
            jumpBaseAddress = lastAddress;
            shouldJump = true;
        }

        if (shouldJump) {
            const uint32_t blockSize = 16 * 16; // 16 rows of 16 bytes
            const uint32_t blockStart = (jumpBaseAddress / blockSize) * blockSize;
            if (currentAddress != blockStart) {
                currentAddress = blockStart;
                addressInput->setText(QString("0x%1").arg(currentAddress, 8, 16, QChar('0')));
            }
        }
    }

    populateMemory(currentAddress);
}
