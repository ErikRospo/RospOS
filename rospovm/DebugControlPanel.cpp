#include "DebugControlPanel.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QGroupBox>
#include <QLabel>
#include <QFont>
#include <QStyle>
#include <QApplication>
#include <QSignalBlocker>

DebugControlPanel::DebugControlPanel(QWidget *parent)
    : QWidget(parent), vmController(nullptr), currentSpeed(50)
{
    createUI();
    setupConnections();
}

DebugControlPanel::~DebugControlPanel() = default;

void DebugControlPanel::createUI()
{
    QVBoxLayout *mainLayout = new QVBoxLayout(this);
    mainLayout->setSpacing(10);
    mainLayout->setContentsMargins(10, 10, 10, 10);

    // ===== Status =====
    QGroupBox *statusGroup = new QGroupBox(tr("VM Status"), this);
    QVBoxLayout *statusLayout = new QVBoxLayout(statusGroup);

    statusLabel = new QLabel(tr("Status: Ready"));
    QFont statusFont = statusLabel->font();
    statusFont.setPointSize(10);
    statusFont.setBold(true);
    statusLabel->setFont(statusFont);
    statusLayout->addWidget(statusLabel);

    pcLabel = new QLabel(tr("PC: 0x00000000"));
    QFont pcFont = pcLabel->font();
    pcFont.setPointSize(9);
    pcFont.setFamily("Courier New");
    pcLabel->setFont(pcFont);
    statusLayout->addWidget(pcLabel);

    mainLayout->addWidget(statusGroup);

    // ===== Speed Control =====
    QGroupBox *speedGroup = new QGroupBox(tr("Execution Speed"), this);
    QVBoxLayout *speedLayout = new QVBoxLayout(speedGroup);

    QHBoxLayout *speedControlLayout = new QHBoxLayout();
    speedControlLayout->addWidget(new QLabel(tr("Speed:")));
    
    speedValueLabel = new QLabel(tr("50%"));
    speedControlLayout->addWidget(speedValueLabel);
    
    speedSlider = new QSlider(Qt::Horizontal);
    speedSlider->setMinimum(1);
    speedSlider->setMaximum(100);
    speedSlider->setValue(50);
    speedSlider->setTickPosition(QSlider::TicksBelow);
    speedSlider->setTickInterval(10);
    speedControlLayout->addWidget(speedSlider);

    speedLayout->addLayout(speedControlLayout);
    mainLayout->addWidget(speedGroup);

    // ===== Navigation =====
    QGroupBox *navGroup = new QGroupBox(tr("Navigation"), this);
    QVBoxLayout *navLayout = new QVBoxLayout(navGroup);

    QHBoxLayout *addressLayout = new QHBoxLayout();
    addressLayout->addWidget(new QLabel(tr("Jump to Address:")));

    addressSpinBox = new QSpinBox();
    addressSpinBox->setMinimum(0);
    addressSpinBox->setMaximum(0xFFFFFFFF);
    addressSpinBox->setDisplayIntegerBase(16);
    addressSpinBox->setMaximumWidth(150);
    addressLayout->addWidget(addressSpinBox);

    navLayout->addLayout(addressLayout);
    mainLayout->addWidget(navGroup);

    // ===== Breakpoints (placeholder) =====
    QGroupBox *breakpointGroup = new QGroupBox(tr("Breakpoints"), this);
    QVBoxLayout *breakpointLayout = new QVBoxLayout(breakpointGroup);

    breakpointLabel = new QLabel(tr("(Not yet implemented)"));
    breakpointLabel->setStyleSheet("color: #999999;");
    breakpointLayout->addWidget(breakpointLabel);

    mainLayout->addWidget(breakpointGroup);

    // ===== Number Converter =====
    QGroupBox *converterGroup = new QGroupBox(tr("Number Converter"), this);
    QVBoxLayout *converterLayout = new QVBoxLayout(converterGroup);

    QHBoxLayout *hexLayout = new QHBoxLayout();
    hexLayout->addWidget(new QLabel(tr("HEX:")));
    hexInput = new QLineEdit();
    hexInput->setPlaceholderText(tr("FF"));
    hexInput->setToolTip(tr("Hexadecimal value"));
    hexLayout->addWidget(hexInput);
    converterLayout->addLayout(hexLayout);

    QHBoxLayout *decLayout = new QHBoxLayout();
    decLayout->addWidget(new QLabel(tr("DEC:")));
    decInput = new QLineEdit();
    decInput->setPlaceholderText(tr("255"));
    decInput->setToolTip(tr("Decimal value"));
    decLayout->addWidget(decInput);
    converterLayout->addLayout(decLayout);

    QHBoxLayout *binLayout = new QHBoxLayout();
    binLayout->addWidget(new QLabel(tr("BIN:")));
    binInput = new QLineEdit();
    binInput->setPlaceholderText(tr("11111111"));
    binInput->setToolTip(tr("Binary value"));
    binLayout->addWidget(binInput);
    converterLayout->addLayout(binLayout);

    QHBoxLayout *asciiLayout = new QHBoxLayout();
    asciiLayout->addWidget(new QLabel(tr("ASCII:")));
    asciiInput = new QLineEdit();
    asciiInput->setPlaceholderText(tr("ASCII Text"));
    asciiInput->setToolTip(tr("Binary value"));
    asciiLayout->addWidget(asciiInput);
    converterLayout->addLayout(asciiLayout);

    
    mainLayout->addWidget(converterGroup);

    // Add stretch to push everything to top
    mainLayout->addStretch();

    setLayout(mainLayout);
}

void DebugControlPanel::setupConnections()
{
    connect(speedSlider, QOverload<int>::of(&QSlider::valueChanged), this, &DebugControlPanel::speedChanged);
    
    connect(addressSpinBox, QOverload<int>::of(&QSpinBox::valueChanged),
            this, [this](int value) {
                emit addressChanged(static_cast<uint32_t>(value));
                if (currentSpeed==100){
                    speedValueLabel->setText(tr("Max"));                    
                }else{
                    speedValueLabel->setText(QString("%1%").arg(currentSpeed));
                }
            });

    connect(hexInput, &QLineEdit::textChanged, this, &DebugControlPanel::updateConverterFromHex);
    connect(decInput, &QLineEdit::textChanged, this, &DebugControlPanel::updateConverterFromDec);
    connect(binInput, &QLineEdit::textChanged, this, &DebugControlPanel::updateConverterFromBin);
    connect(asciiInput, &QLineEdit::textChanged, this, &DebugControlPanel::updateConverterFromAscii);
}

void DebugControlPanel::setVMController(VMController *controller)
{
    vmController = controller;
}

void DebugControlPanel::setStepEnabled(bool enabled)
{
    Q_UNUSED(enabled);
}

void DebugControlPanel::setStepBackEnabled(bool enabled)
{
    Q_UNUSED(enabled);
}

void DebugControlPanel::setRunEnabled(bool enabled)
{
    Q_UNUSED(enabled);
}

void DebugControlPanel::setPauseEnabled(bool enabled)
{
    Q_UNUSED(enabled);
}

void DebugControlPanel::setResetEnabled(bool enabled)
{
    Q_UNUSED(enabled);
}

void DebugControlPanel::setStatus(const QString &status)
{
    statusLabel->setText(tr("Status: ") + status);
}

void DebugControlPanel::setPCLabel(uint32_t pc)
{
    pcLabel->setText(QString(tr("PC: 0x%1")).arg(pc, 8, 16, QChar('0')));
}

void DebugControlPanel::updateConverterFromHex(const QString &text)
{
    if (converterUpdating) {
        return;
    }

    bool ok = false;
    const QString trimmed = text.trimmed();
    const uint32_t value = trimmed.toUInt(&ok, 16);
    if (!ok) {
        return;
    }

    converterUpdating = true;
    {
        QSignalBlocker decBlocker(decInput);
        QSignalBlocker binBlocker(binInput);
        QSignalBlocker asciiBlocker(asciiInput);
        decInput->setText(QString::number(value));
        binInput->setText(QString::number(value, 2));
        asciiInput->setText(QString::fromUtf8(reinterpret_cast<const char*>(&value), 4));
    }
    converterUpdating = false;
}

void DebugControlPanel::updateConverterFromDec(const QString &text)
{
    if (converterUpdating) {
        return;
    }

    bool ok = false;
    const QString trimmed = text.trimmed();
    const uint32_t value = trimmed.toUInt(&ok, 10);
    if (!ok) {
        return;
    }

    converterUpdating = true;
    {
        QSignalBlocker hexBlocker(hexInput);
        QSignalBlocker binBlocker(binInput);
        QSignalBlocker asciiBlocker(asciiInput);
        hexInput->setText(QString::number(value, 16).toUpper());
        binInput->setText(QString::number(value, 2));
        asciiInput->setText(QString::fromUtf8(reinterpret_cast<const char*>(&value), 4));
    }
    converterUpdating = false;
}

void DebugControlPanel::updateConverterFromBin(const QString &text)
{
    if (converterUpdating) {
        return;
    }

    QString trimmed = text.trimmed();
    if (trimmed.isEmpty()) {
        return;
    }

    for (const QChar c : trimmed) {
        if (c != '0' && c != '1') {
            return;
        }
    }

    bool ok = false;
    const uint32_t value = trimmed.toUInt(&ok, 2);
    if (!ok) {
        return;
    }

    converterUpdating = true;
    {
        QSignalBlocker hexBlocker(hexInput);
        QSignalBlocker decBlocker(decInput);
        QSignalBlocker asciiBlocker(asciiInput);
        hexInput->setText(QString::number(value, 16).toUpper());
        decInput->setText(QString::number(value));
        asciiInput->setText(QString::fromUtf8(reinterpret_cast<const char*>(&value), 4));
    }
    converterUpdating = false;
}

void DebugControlPanel::updateConverterFromAscii(const QString &text)
{
    if (converterUpdating) {
        return;
    }

    if (text.isEmpty()) {
        return;
    }

    const QByteArray asciiBytes = text.toUtf8();
    uint32_t value = 0;
    for (int i = 0; i < asciiBytes.size() && i < 4; ++i) {
        value |= static_cast<uint32_t>(asciiBytes[i]) << ((3 - i) * 8);
    }

    converterUpdating = true;
    {
        QSignalBlocker hexBlocker(hexInput);
        QSignalBlocker decBlocker(decInput);
        QSignalBlocker binBlocker(binInput);
        hexInput->setText(QString::number(value, 16).toUpper());
        decInput->setText(QString::number(value));
        binInput->setText(QString::number(value, 2));
    }
    converterUpdating = false;
}