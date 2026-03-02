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

// AssemblySyntaxHighlighter implementation
AssemblySyntaxHighlighter::AssemblySyntaxHighlighter(QTextDocument *parent)
    : QSyntaxHighlighter(parent)
{
    // Address format (e.g., 0x00010000:)
    addressFormat.setForeground(QColor(100, 200, 255));  // Light blue
    addressFormat.setFontWeight(QFont::Bold);

    // Bytes format (hex)
    bytesFormat.setForeground(QColor(150, 150, 150));    // Gray
    
    // Instruction mnemonics (main instructions)
    instructionFormat.setForeground(QColor(200, 100, 255)); // Magenta
    instructionFormat.setFontWeight(QFont::Bold);
    
    // Registers
    registerFormat.setForeground(QColor(100, 255, 100)); // Light green
    
    // Immediate values
    immediateFormat.setForeground(QColor(255, 200, 100)); // Orange
    
    // Jump/Branch instructions
    jumpFormat.setForeground(QColor(255, 100, 100));      // Light red
    jumpFormat.setFontWeight(QFont::Bold);
    
    // Comments
    commentFormat.setForeground(QColor(128, 128, 128));   // Dark gray
    commentFormat.setFontItalic(true);
}

void AssemblySyntaxHighlighter::highlightBlock(const QString &text)
{
    // Pattern: Address Bytes Instruction Registers/Immediates [Comment]
    
    // Highlight address (starts line, contains 0x)
    QRegularExpression addressRegex("0x[0-9a-fA-F]+");
    auto addressMatch = addressRegex.globalMatch(text);
    while (addressMatch.hasNext()) {
        auto match = addressMatch.next();
        // Only highlight if it's at the start (address column)
        if (match.capturedStart() == 0 || 
            (match.capturedStart() > 0 && !text[match.capturedStart() - 1].isLetterOrNumber())) {
            setFormat(match.capturedStart(), match.capturedLength(), addressFormat);
        }
    }

    // Highlight registers (r0-r15)
    QRegularExpression registerRegex("\\br(\\d|1[0-5])\\b");
    auto registerMatch = registerRegex.globalMatch(text);
    while (registerMatch.hasNext()) {
        auto match = registerMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), registerFormat);
    }

    // Highlight jump instructions
    QRegularExpression jumpRegex("\\b(BEQ|BNE|BLT|BGE|BLTU|BGEU|JAL|JALR|JMP)\\b");
    auto jumpMatch = jumpRegex.globalMatch(text);
    while (jumpMatch.hasNext()) {
        auto match = jumpMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), jumpFormat);
    }

    // Highlight other instructions
    QRegularExpression instrRegex("\\b(ADD|SUB|AND|OR|XOR|MUL|MULH|NEG|NOT|SHL|SHR|SAR|DIV|DIVU|REM|REMU|"
                                   "ADDI|ANDI|ORI|XORI|SHLI|SHRI|SARI|"
                                   "LB|LBU|LH|LHU|LW|SB|SH|SW|"
                                   "ECALL|BREAK|NOP)\\b");
    auto instrMatch = instrRegex.globalMatch(text);
    while (instrMatch.hasNext()) {
        auto match = instrMatch.next();
        setFormat(match.capturedStart(), match.capturedLength(), instructionFormat);
    }

    // Highlight comments
    QRegularExpression commentRegex(";.*");
    auto commentMatch = commentRegex.match(text);
    if (commentMatch.hasMatch()) {
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

    codeDisplay = new QPlainTextEdit();
    codeDisplay->setReadOnly(true);

    // Set monospace font
    QFont monoFont("Courier New");
    monoFont.setPointSize(10);
    monoFont.setStyleStrategy(QFont::PreferAntialias);
    codeDisplay->setFont(monoFont);

    // Set up syntax highlighter
    highlighter = new AssemblySyntaxHighlighter(codeDisplay->document());

    // Dark theme
    codeDisplay->setStyleSheet(
        "QPlainTextEdit { background-color: #1e1e1e; color: #d4d4d4; }"
    );

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
    if (!vmController) {
        return;
    }

    uint32_t newPC = vmController->getProgramCounter();
    
    // Check if PC has changed significantly - if so, recenter view
    if (newPC != lastDisplayedPC || addressToLine.isEmpty()) {
        // Calculate new display window centered on PC
        uint32_t instructionOffset = INSTRUCTIONS_BEFORE_PC * 4;
        
        // Safely subtract (handle underflow)
        if (newPC >= instructionOffset) {
            codeStartAddress = newPC - instructionOffset;
        } else {
            codeStartAddress = 0;
        }
        
        codeEndAddress = codeStartAddress + (NUM_INSTRUCTIONS * 4);
        lastDisplayedPC = newPC;
        
        populateCode();
    } else {
        // Just highlight current instruction, no repopulation needed
        highlightCurrentInstruction();
    }
}

void CodeView::populateCode()
{
    if (!vmController) {
        return;
    }

    codeDisplay->clear();
    addressToLine.clear();

    QString codeText;
    int lineNum = 0;

    for (int i = 0; i < NUM_INSTRUCTIONS; ++i) {
        uint32_t addr = codeStartAddress + (static_cast<uint32_t>(i) * 4);
        
        // Stop if we exceed reasonable memory bounds
        if (addr > 0xFFFFFFFF - 4) {
            break;
        }
        
        // Get instruction
        auto instructions = vmController->getCodeRange(addr, 4);
        if (instructions.empty()) {
            continue;
        }

        uint32_t instruction = instructions[0];
        
        // Store address to line mapping
        addressToLine[addr] = lineNum;

        // Format: Address | Bytes | Instruction
        QString line = QString("0x%1  %2  %3\n")
            .arg(addr, 8, 16, QChar('0'))
            .arg(instruction, 8, 16, QChar('0'))
            .arg(vmController->disassembleInstruction(instruction));

        codeText += line;
        lineNum++;
    }

    codeDisplay->setPlainText(codeText);
    highlightCurrentInstruction();
}

void CodeView::highlightCurrentInstruction()
{
    if (!vmController) {
        return;
    }

    uint32_t currentPC = vmController->getProgramCounter();

    // Find the line with current PC
    if (addressToLine.contains(currentPC)) {
        int lineNum = addressToLine[currentPC];
        
        QTextDocument *doc = codeDisplay->document();
        QTextBlock block = doc->findBlockByLineNumber(lineNum);
        
        QTextCursor cursor(block);
        cursor.select(QTextCursor::LineUnderCursor);
        
        QTextEdit::ExtraSelection selection;
        selection.cursor = cursor;
        selection.format.setBackground(QColor(100, 100, 50));  // Dark yellow highlight
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
