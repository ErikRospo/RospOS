#include "CodeView.h"
#include "VMController.h"

#include <QVBoxLayout>
#include <QFont>
#include <QTextEdit>
#include <QRegularExpression>
#include <QTextCursor>
#include <QTextBlock>
#include <QBrush>
#include <QColor>

namespace
{
const QColor kAddressColor(100, 200, 255);
const QColor kBytesColor(150, 150, 150);
const QColor kInstructionColor(200, 100, 255);
const QColor kRegisterColor(100, 255, 100);
const QColor kImmediateColor(255, 200, 100);
const QColor kJumpColor(255, 100, 100);
const QColor kCommentColor(128, 128, 128);
const QColor kBranchColor(255, 150, 100);
const QColor kMemoryColor(100, 200, 255);
const QColor kSystemColor(255, 200, 50);
const QColor kCurrentInstructionHighlightColor(100, 100, 50);

const QRegularExpression kAddressRegex(QStringLiteral("0x[0-9a-fA-F]+"));
const QRegularExpression kRawInstructionRegex(QStringLiteral("\\b([0-9a-fA-F]){8}I\\b"));
const QRegularExpression kRegisterRegex(QStringLiteral("\\br(\\d|1[0-5])\\b"));
const QRegularExpression kBranchRegex(QStringLiteral("\\b(BEQ|BNE|BLT|BGE|BLTU|BGEU)\\b"));
const QRegularExpression kJumpRegex(QStringLiteral("\\b(JAL|JALR|JMP)\\b"));
const QRegularExpression kAluRegex(QStringLiteral("\\b(ADD|SUB|AND|OR|XOR|MUL|MULH|NEG|NOT|SHL|SHR|SAR|DIV|DIVU|REM|REMU|"
                                                  "ADDI|ANDI|ORI|XORI|SHLI|SHRI|SARI)\\b"));
const QRegularExpression kMemRegex(QStringLiteral("\\b(LB|LBU|LH|LHU|LW|SB|SH|SW)\\b"));
const QRegularExpression kSysRegex(QStringLiteral("\\b(ECALL|BREAK|NOP)\\b"));
const QRegularExpression kCommentRegex(QStringLiteral(";.*"));

const QString kCodeDisplayStylesheet =
    QStringLiteral("QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }");
constexpr int kHexFieldWidth = 8;
constexpr int kHexBase = 16;
constexpr int kCodeFontSize = 10;
}

// AssemblySyntaxHighlighter implementation
AssemblySyntaxHighlighter::AssemblySyntaxHighlighter(QTextDocument *parent)
    : QSyntaxHighlighter(parent)
{
    // Address format (e.g., 0x00010000:)
    addressFormat.setForeground(kAddressColor); // Light blue
    addressFormat.setFontWeight(QFont::Bold);

    // Bytes format (hex)
    bytesFormat.setForeground(kBytesColor); // Gray

    // Instruction mnemonics (main instructions)
    instructionFormat.setForeground(kInstructionColor); // Magenta
    instructionFormat.setFontWeight(QFont::Bold);

    // Registers
    registerFormat.setForeground(kRegisterColor); // Light green

    // Immediate values
    immediateFormat.setForeground(kImmediateColor); // Orange

    // Jump/Branch instructions
    jumpFormat.setForeground(kJumpColor); // Light red
    jumpFormat.setFontWeight(QFont::Bold);

    // Comments
    commentFormat.setForeground(kCommentColor); // Dark gray
    commentFormat.setFontItalic(true);

    // Branch instructions (conditional)
    branchFormat.setForeground(kBranchColor); // Coral
    branchFormat.setFontWeight(QFont::Bold);

    // Arithmetic/logic instructions
    aluFormat.setForeground(kInstructionColor); // Magenta
    aluFormat.setFontWeight(QFont::Bold);

    // Memory instructions
    memFormat.setForeground(kMemoryColor); // Cyan
    memFormat.setFontWeight(QFont::Bold);

    // System/special instructions
    sysFormat.setForeground(kSystemColor); // Yellow
    sysFormat.setFontWeight(QFont::Bold);
}

void AssemblySyntaxHighlighter::highlightBlock(const QString &text)
{
    // Pattern: Address Bytes Instruction Registers/Immediates [Comment]

    // Highlight address (starts line, contains 0x)
    auto addressMatch = kAddressRegex.globalMatch(text);
    while (addressMatch.hasNext())
    {
        auto match = addressMatch.next();
        // Only highlight if it's at the start (address column)
        if (match.capturedStart() == 0 ||
            (match.capturedStart() > 0 && !text[match.capturedStart() - 1].isLetterOrNumber()))
        {
            setFormat(match.capturedStart(), match.capturedLength(), addressFormat);
        }
    }

    auto rawInstructionMatch = kRawInstructionRegex.globalMatch(text);
    while (rawInstructionMatch.hasNext())
    {
        auto match = rawInstructionMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), bytesFormat);
    }
    // Highlight registers (r0-r15)
    auto registerMatch = kRegisterRegex.globalMatch(text);
    while (registerMatch.hasNext())
    {
        auto match = registerMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), registerFormat);
    }

    // Highlight branch instructions (conditional)
    auto branchMatch = kBranchRegex.globalMatch(text);
    while (branchMatch.hasNext())
    {
        auto match = branchMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), branchFormat);
    }

    // Highlight jump instructions (unconditional)
    auto jumpMatch = kJumpRegex.globalMatch(text);
    while (jumpMatch.hasNext())
    {
        auto match = jumpMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), jumpFormat);
    }

    // Highlight arithmetic/logic instructions
    auto aluMatch = kAluRegex.globalMatch(text);
    while (aluMatch.hasNext())
    {
        auto match = aluMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), aluFormat);
    }

    // Highlight memory instructions
    auto memMatch = kMemRegex.globalMatch(text);
    while (memMatch.hasNext())
    {
        auto match = memMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), memFormat);
    }

    // Highlight system/special instructions
    auto sysMatch = kSysRegex.globalMatch(text);
    while (sysMatch.hasNext())
    {
        auto match = sysMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), sysFormat);
    }

    // Highlight comments
    auto commentMatch = kCommentRegex.match(text);
    if (commentMatch.hasMatch())
    {
        setFormat(commentMatch.capturedStart(), commentMatch.capturedLength(), commentFormat);
    }
}

// CodeView implementation
CodeView::CodeView(QWidget *parent)
    : QWidget(parent), vmController(nullptr), currentPC(0)
{
    createUI();
}

CodeView::~CodeView() = default;

void CodeView::createUI()
{
    QVBoxLayout *layout = new QVBoxLayout(this);
    layout->setContentsMargins(0, 0, 0, 0);
    
    // Add source location info display at the top
    sourceInfoDisplay = new QPlainTextEdit();
    sourceInfoDisplay->setReadOnly(true);
    sourceInfoDisplay->setMaximumHeight(40);
    QFont monoFont("Courier New");
    monoFont.setPointSize(9);
    sourceInfoDisplay->setFont(monoFont);
    sourceInfoDisplay->setStyleSheet(kCodeDisplayStylesheet);
    layout->addWidget(sourceInfoDisplay);

    codeDisplay = new QPlainTextEdit();
    codeDisplay->setReadOnly(true);

    // Set monospace font
    monoFont.setPointSize(kCodeFontSize);
    monoFont.setStyleStrategy(QFont::PreferAntialias);
    codeDisplay->setFont(monoFont);

    // Set up syntax highlighter
    highlighter = new AssemblySyntaxHighlighter(codeDisplay->document());

    // Dark theme
    codeDisplay->setStyleSheet(kCodeDisplayStylesheet);

    layout->addWidget(codeDisplay);
    setLayout(layout);

    // Initialize code range - will be updated based on PC
    codeStartAddress = 0x00000000;
    codeEndAddress = 0xFFFFFFFF;
}

void CodeView::setVMController(VMController *controller)
{
    vmController = controller;
}

void CodeView::setCodeRange(uint32_t startAddr, uint32_t endAddr)
{
    codeStartAddress = startAddr;
    codeEndAddress = endAddr;
}

void CodeView::refresh()
{
    if (!vmController)
    {
        return;
    }

    uint32_t newPC = vmController->getProgramCounter();

    // Check if PC has changed significantly - if so, recenter view
    if (newPC != lastDisplayedPC || addressToLine.isEmpty())
    {
        // Calculate new display window centered on PC
        uint32_t instructionOffset = INSTRUCTIONS_BEFORE_PC * 4;

        // Safely subtract (handle underflow)
        if (newPC >= instructionOffset)
        {
            codeStartAddress = newPC - instructionOffset;
        }
        else
        {
            codeStartAddress = 0;
        }

        codeEndAddress = codeStartAddress + (NUM_INSTRUCTIONS * 4);
        lastDisplayedPC = newPC;

    };
    populateCode();
    highlightCurrentInstruction();
    
    // Update source info display
    QString sourceLocation = vmController->getCurrentSourceLocation();
    QString originalInstruction = vmController->getCurrentOriginalInstruction();
    QString sourceInfo = QString("PC: 0x%1 | Source: %2 | Instruction: %3")
        .arg(newPC, 8, 16, QChar('0'))
        .arg(sourceLocation)
        .arg(originalInstruction.isEmpty() ? "<no debug info>" : originalInstruction);
    sourceInfoDisplay->setPlainText(sourceInfo);
}

void CodeView::populateCode()
{
    if (!vmController)
    {
        return;
    }

    codeDisplay->clear();
    addressToLine.clear();

    QString codeText;
    int lineNum = 0;

    for (int i = 0; i < NUM_INSTRUCTIONS; ++i)
    {
        uint32_t addr = codeStartAddress + (static_cast<uint32_t>(i) * 4);

        // Stop if we exceed reasonable memory bounds
        if (addr > 0xFFFFFFFF - 4)
        {
            break;
        }

        // Get instruction
        auto instructions = vmController->getCodeRange(addr, 4);
        if (instructions.empty())
        {
            continue;
        }

        uint32_t instruction = instructions[0];

        // Store address to line mapping
        addressToLine[addr] = lineNum;

        // Get source location if available
        QString sourceLocation = vmController->getSourceLocation(addr);
        QString sourceComment = (sourceLocation != "unknown") 
            ? QString(" ; [%1]").arg(sourceLocation)
            : "";

        // Format: Address | Bytes | Instruction | Source Location
        QString line = QString("0x%1  %2I  %3%4\n")
                           .arg(addr, kHexFieldWidth, kHexBase, QChar('0'))
                           .arg(instruction, kHexFieldWidth, kHexBase, QChar('0'))
                           .arg(vmController->disassembleInstruction(instruction))
                           .arg(sourceComment);

        codeText += line;
        lineNum++;
    }

    codeDisplay->setPlainText(codeText);
    highlightCurrentInstruction();
}

void CodeView::highlightCurrentInstruction()
{
    if (!vmController)
    {
        return;
    }

    uint32_t currentPC = vmController->getProgramCounter();

    // Find the line with current PC
    if (addressToLine.contains(currentPC))
    {
        int lineNum = addressToLine[currentPC];

        QTextDocument *doc = codeDisplay->document();
        QTextBlock block = doc->findBlockByLineNumber(lineNum);

        QTextCursor cursor(block);
        cursor.select(QTextCursor::LineUnderCursor);

        QTextEdit::ExtraSelection selection;
        selection.cursor = cursor;
        selection.format.setBackground(kCurrentInstructionHighlightColor); // Dark yellow highlight
        selection.format.setProperty(QTextFormat::FullWidthSelection, true);

        codeDisplay->setExtraSelections({selection});

        // Scroll view to center on this instruction
        // Add some margin so it stays roughly in the middle
        QTextCursor centralCursor = cursor;
        codeDisplay->setTextCursor(centralCursor);
        codeDisplay->ensureCursorVisible();
    }
}

void CodeView::centerOnPC()
{
    highlightCurrentInstruction();
}
