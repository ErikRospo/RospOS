#include "RegisterView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QHeaderView>
#include <QFont>
#include <QLineEdit>
#include <QRegularExpression>

RegisterView::RegisterView(QWidget *parent)
    : QWidget(parent), vmController(nullptr)
{
    createUI();
}

RegisterView::~RegisterView() = default;

void RegisterView::setVMController(VMController *controller)
{
    vmController = controller;
    vmController->setRegisterView(this);
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
    breakpointEvaluator.compile(bkptLineEditor->text().toStdString());
}
void RegisterView::updateBkptCtx()
{
    std::array<uint32_t, 16> registers;
    for (int i = 0; i < 16; ++i)
    {
        registers[i] = vmController->getRegister(i);
    }

    breakpointEvaluator.updateContext(registers, vmController->getProgramCounter());
}
void RegisterView::checkBreakpoint()
{
    if (bkptLineEditor->text().length() == 0)
    {
        return;
    }
    updateBkptCtx();

    if (breakpointEvaluator.matches() && vmController->isRunning())
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
void RegisterView::addPCBkpt(uint32_t pc)
{
    const QString value = QString::number(pc, 10);
    const QString clause = QStringLiteral(R"(\(?\s*pc\s*==\s*%1\s*\)?)").arg(value);
    QString expression = bkptLineEditor->text().trimmed();

    // Treat equivalent whitespace and parenthesized forms as the same clause.
    const QRegularExpression alreadyPresent(
        QStringLiteral(R"((^|\bor\b)\s*%1(?=\s*(?:\bor\b|$)))").arg(clause),
        QRegularExpression::CaseInsensitiveOption);
    if (alreadyPresent.match(expression).hasMatch())
        return;

    if (!expression.isEmpty())
        expression += QStringLiteral(" or ");
    expression += QStringLiteral("(pc==%1)").arg(value);
    bkptLineEditor->setText(expression);
}
void RegisterView::removePCBkpt(uint32_t pc)
{
    const QString value = QString::number(pc, 10);
    const QString clause = QStringLiteral(R"(\(?\s*pc\s*==\s*%1\s*\)?)").arg(value);
    QString expression = bkptLineEditor->text().trimmed();

    // Remove the clause together with the adjacent operator, regardless of
    // whether it is the first, middle, or last operand.
    QRegularExpression first(
        QStringLiteral(R"(^%1\s+or\s+)").arg(clause),
        QRegularExpression::CaseInsensitiveOption);
    QRegularExpression last(
        QStringLiteral(R"(\s+or\s+%1$)").arg(clause),
        QRegularExpression::CaseInsensitiveOption);
    QRegularExpression middle(
        QStringLiteral(R"(\s+or\s+%1\s+or\s+)").arg(clause),
        QRegularExpression::CaseInsensitiveOption);
    QRegularExpression only(
        QStringLiteral(R"(^%1$)").arg(clause),
        QRegularExpression::CaseInsensitiveOption);

    if (only.match(expression).hasMatch())
        expression.clear();
    else if (first.match(expression).hasMatch())
        expression.remove(first);
    else if (last.match(expression).hasMatch())
        expression.remove(last);
    else
        expression.replace(middle, QStringLiteral(" or "));

    expression = expression.trimmed();
    if (expression != bkptLineEditor->text())
        bkptLineEditor->setText(expression);
}
