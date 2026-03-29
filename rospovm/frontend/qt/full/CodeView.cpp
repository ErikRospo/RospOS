#include "CodeView.h"
#include "VMController.h"

#include <KSyntaxHighlighting/Definition>
#include <KSyntaxHighlighting/Repository>
#include <KSyntaxHighlighting/SyntaxHighlighter>
#include <KSyntaxHighlighting/Theme>

#include <QCoreApplication>
#include <QGuiApplication>
#include <QStyleHints>
#include <QDir>
#include <QVBoxLayout>
#include <QFont>
#include <QTextEdit>
#include <QTextCursor>
#include <QTextBlock>
#include <QColor>
#include <QFile>
#include <QFileInfo>
#include <QSplitter>
#include <QTextStream>
#include <QHelpEvent>
#include <QToolTip>
#include <QRegularExpression>
#include <QDebug>

namespace
{
const QColor kCurrentInstructionHighlightColor(35, 72, 128);

const QString kCodeDisplayStylesheet =
    QStringLiteral("QPlainTextEdit { background-color: #11151b; color: #d8dee9; }");
const QString kSourceDisplayStylesheet =
    QStringLiteral("QPlainTextEdit { background-color: #11151b; color: #d8dee9; }");
constexpr int kHexFieldWidth = 8;
constexpr int kHexBase = 16;
constexpr int kCodeFontSize = 10;
const QColor kCurrentSourceLineHighlightColor(35, 72, 128);

QString resolveHighlightingPath()
{
#ifdef ROSPOSVM_HIGHLIGHTING_DIR
    const QString configuredPath = QStringLiteral(ROSPOSVM_HIGHLIGHTING_DIR);
    if (QDir(configuredPath).exists())
    {
        return configuredPath;
    }
#endif

    const QDir appDir(QCoreApplication::applicationDirPath());
    const QString localPath = appDir.filePath(QStringLiteral("highlighting"));
    if (QDir(localPath).exists())
    {
        return localPath;
    }

    const QString buildPath = appDir.filePath(QStringLiteral("../highlighting"));
    if (QDir(buildPath).exists())
    {
        return buildPath;
    }

    return QString();
}

} // namespace

// CodeView implementation
CodeView::CodeView(QWidget *parent)
    : QWidget(parent), vmController(nullptr), codeDisplay(nullptr), sourceInfoDisplay(nullptr),
      sourceCodeDisplay(nullptr), syntaxRepository(nullptr), codeHighlighter(nullptr),
      sourceHighlighter(nullptr), currentPC(0)
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

    QSplitter *centerSplitter = new QSplitter(Qt::Horizontal, this);
    centerSplitter->setChildrenCollapsible(false);

    codeDisplay = new QPlainTextEdit();
    codeDisplay->setReadOnly(true);
    codeDisplay->setMouseTracking(true);
    codeDisplay->viewport()->setMouseTracking(true);
    codeDisplay->viewport()->installEventFilter(this);

    // Set monospace font
    monoFont.setPointSize(kCodeFontSize);
    monoFont.setStyleStrategy(QFont::PreferAntialias);
    codeDisplay->setFont(monoFont);

    // Dark theme
    codeDisplay->setStyleSheet(kCodeDisplayStylesheet);

    sourceCodeDisplay = new QPlainTextEdit();
    sourceCodeDisplay->setReadOnly(true);
    sourceCodeDisplay->setFont(monoFont);
    sourceCodeDisplay->setStyleSheet(kSourceDisplayStylesheet);
    sourceCodeDisplay->setPlaceholderText("Source file for current instruction will appear here");

    setupSyntaxHighlighting();

    centerSplitter->addWidget(codeDisplay);
    centerSplitter->addWidget(sourceCodeDisplay);
    centerSplitter->setStretchFactor(0, 1);
    centerSplitter->setStretchFactor(1, 1);
    centerSplitter->setSizes({1, 1});

    layout->addWidget(centerSplitter);
    setLayout(layout);

    // Initialize code range - will be updated based on PC
    codeStartAddress = 0x00000000;
    codeEndAddress = 0xFFFFFFFF;
}

void CodeView::setupSyntaxHighlighting()
{
    syntaxRepository = new KSyntaxHighlighting::Repository();

    const QString highlightingRoot = resolveHighlightingPath();
    if (!highlightingRoot.isEmpty())
    {
        syntaxRepository->addCustomSearchPath(highlightingRoot);
    }
    Qt::ColorScheme colorScheme = QGuiApplication::styleHints()->colorScheme();
    KSyntaxHighlighting::Theme theme = syntaxRepository->defaultTheme(KSyntaxHighlighting::Repository::DarkTheme);
    // May be good to make this user-configurable in the future, but for now just match the system theme as best we can
    if (colorScheme==Qt::ColorScheme::Light)
    {
        qInfo() << "Inferior color scheme detected!";
        theme = syntaxRepository->defaultTheme(KSyntaxHighlighting::Repository::LightTheme);
    }
    codeHighlighter = new KSyntaxHighlighting::SyntaxHighlighter(codeDisplay->document());
    codeHighlighter->setTheme(theme);
    KSyntaxHighlighting::Definition codeDefinition =
        syntaxRepository->definitionForName(QStringLiteral("RospOS Assembly"));
    if (!codeDefinition.isValid())
    {
        qWarning() << "RospOS Assembly syntax definition not found. Code will not be highlighted.";
    }
    codeHighlighter->setDefinition(codeDefinition);

    sourceHighlighter = new KSyntaxHighlighting::SyntaxHighlighter(sourceCodeDisplay->document());
    sourceHighlighter->setTheme(theme);
    sourceHighlighter->setDefinition(syntaxRepository->definitionForName(QStringLiteral("C")));
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
    updateSourcePanel(newPC);
}

void CodeView::populateCode()
{
    if (!vmController)
    {
        return;
    }

    codeDisplay->clear();
    addressToLine.clear();
    lineToAddress.clear();

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
        lineToAddress[lineNum] = addr;

        // Format: Address | Bytes | Instruction | Source Location
        QString line = QString("0x%1  %2  %3\n")
                           .arg(addr, kHexFieldWidth, kHexBase, QChar('0'))
                           .arg(instruction, kHexFieldWidth, kHexBase, QChar('0'))
                           .arg(vmController->disassembleInstruction(instruction));
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
    else
    {
        codeDisplay->setExtraSelections({});
    }
}

void CodeView::updateSourcePanel(uint32_t address)
{
    if (!vmController) {
        return;
    }

    QString sourceFilePath;
    uint32_t sourceLine = 0;
    if (!vmController->getSourceReference(address, sourceFilePath, sourceLine)) {
        sourceCodeDisplay->setExtraSelections({});
        if (sourceCodeDisplay->toPlainText().isEmpty() || !currentSourceFilePath.isEmpty()) {
            currentSourceFilePath.clear();
            sourceCodeDisplay->setPlainText("No source mapping available for the current instruction.");
        }
        return;
    }

    if (sourceFilePath != currentSourceFilePath) {
        loadSourceFile(sourceFilePath);
    }

    highlightSourceLine(sourceLine);
}

void CodeView::loadSourceFile(const QString &sourceFilePath)
{
    if (!sourceFileCache.contains(sourceFilePath)) {
        QFile sourceFile(sourceFilePath);
        if (!sourceFile.open(QIODevice::ReadOnly | QIODevice::Text)) {
            currentSourceFilePath = sourceFilePath;
            sourceCodeDisplay->setPlainText(
                QString("Unable to open source file:\n%1").arg(QFileInfo(sourceFilePath).absoluteFilePath()));
            sourceCodeDisplay->setExtraSelections({});
            return;
        }

        QTextStream stream(&sourceFile);
        QStringList lines;
        while (!stream.atEnd()) {
            lines.append(stream.readLine());
        }
        sourceFileCache.insert(sourceFilePath, lines);
    }

    currentSourceFilePath = sourceFilePath;
    sourceCodeDisplay->setPlainText(sourceFileCache.value(sourceFilePath).join("\n"));
}

void CodeView::highlightSourceLine(uint32_t oneBasedLine)
{
    if (oneBasedLine == 0) {
        sourceCodeDisplay->setExtraSelections({});
        return;
    }

    int zeroBasedLine = static_cast<int>(oneBasedLine - 1);
    QTextBlock block = sourceCodeDisplay->document()->findBlockByLineNumber(zeroBasedLine);
    if (!block.isValid()) {
        sourceCodeDisplay->setExtraSelections({});
        return;
    }

    QTextCursor cursor(block);
    cursor.select(QTextCursor::LineUnderCursor);

    QTextEdit::ExtraSelection selection;
    selection.cursor = cursor;
    selection.format.setBackground(kCurrentSourceLineHighlightColor);
    selection.format.setProperty(QTextFormat::FullWidthSelection, true);
    sourceCodeDisplay->setExtraSelections({selection});

    sourceCodeDisplay->setTextCursor(cursor);
    sourceCodeDisplay->ensureCursorVisible();
}

void CodeView::centerOnPC()
{
    highlightCurrentInstruction();
}

bool CodeView::eventFilter(QObject *watched, QEvent *event)
{
    if (watched == codeDisplay->viewport() && event->type() == QEvent::ToolTip)
    {
        QHelpEvent *helpEvent = static_cast<QHelpEvent *>(event);
        const QString tooltipText = resolveCodeRegisterTooltip(helpEvent->pos());
        if (!tooltipText.isEmpty())
        {
            QToolTip::showText(helpEvent->globalPos(), tooltipText, codeDisplay);
            return true;
        }

        QToolTip::hideText();
        event->ignore();
        return true;
    }

    return QWidget::eventFilter(watched, event);
}

QString CodeView::resolveCodeRegisterTooltip(const QPoint &viewportPos) const
{
    if (!vmController)
    {
        return QString();
    }

    const QTextCursor cursor = codeDisplay->cursorForPosition(viewportPos);
    const QTextBlock block = cursor.block();
    if (!block.isValid())
    {
        return QString();
    }

    const int lineNumber = block.blockNumber();
    if (!lineToAddress.contains(lineNumber))
    {
        return QString();
    }

    const QString lineText = block.text();
    const int col = cursor.positionInBlock();

    static const QRegularExpression regPattern(
        QStringLiteral("\\br(1[0-5]|[0-9])\\b"),
        QRegularExpression::CaseInsensitiveOption);

    QRegularExpressionMatchIterator it = regPattern.globalMatch(lineText);
    while (it.hasNext())
    {
        const QRegularExpressionMatch match = it.next();
        const int start = match.capturedStart();
        const int end = start + match.capturedLength();
        if (col < start || col >= end)
        {
            continue;
        }

        bool ok = false;
        const int regIndex = match.captured(1).toInt(&ok);
        if (!ok)
        {
            return QString();
        }

        const uint32_t address = lineToAddress.value(lineNumber);
        return vmController->getRegisterAllocationTooltipAt(address, regIndex);
    }

    return QString();
}
