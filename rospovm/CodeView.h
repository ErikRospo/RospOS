#ifndef CODE_VIEW_H
#define CODE_VIEW_H

#include <QWidget>
#include <QPlainTextEdit>
#include <QSyntaxHighlighter>
#include <QTextDocument>
#include <QRegularExpression>
#include <QMap>
#include <QStringList>
#include <cstdint>

class VMController;

// Syntax highlighter for RospOS assembly
class AssemblySyntaxHighlighter : public QSyntaxHighlighter
{
    Q_OBJECT

public:
    explicit AssemblySyntaxHighlighter(QTextDocument *parent = nullptr);

protected:
    void highlightBlock(const QString &text) override;

private:
    struct HighlightRule
    {
        QRegularExpression pattern;
        QTextCharFormat format;
    };

    QVector<HighlightRule> highlightRules;
    QTextCharFormat addressFormat;
    QTextCharFormat bytesFormat;
    QTextCharFormat instructionFormat;
    QTextCharFormat registerFormat;
    QTextCharFormat immediateFormat;
    QTextCharFormat jumpFormat;
    QTextCharFormat commentFormat;
    QTextCharFormat branchFormat;
    QTextCharFormat aluFormat;
    QTextCharFormat memFormat;
    QTextCharFormat sysFormat;
};

// Code display widget with jump visualization
class CodeView : public QWidget
{
    Q_OBJECT

public:
    explicit CodeView(QWidget *parent = nullptr);
    ~CodeView();

    void setVMController(VMController *controller);
    void refresh();
    void highlightCurrentInstruction();
    void setCodeRange(uint32_t startAddr, uint32_t endAddr);

private:
    void createUI();
    void populateCode();
    void drawJumpVisualization();
    void centerOnPC();
    void updateSourcePanel(uint32_t address);
    void loadSourceFile(const QString &sourceFilePath);
    void highlightSourceLine(uint32_t oneBasedLine);

    VMController *vmController;
    QPlainTextEdit *codeDisplay;
    QPlainTextEdit *sourceInfoDisplay;  // Display for source location info
    QPlainTextEdit *sourceCodeDisplay;
    AssemblySyntaxHighlighter *highlighter;
    
    uint32_t codeStartAddress;
    uint32_t codeEndAddress;
    uint32_t currentPC = 0;
    uint32_t lastDisplayedPC = 0;  // Track if PC changed significantly

    QString currentSourceFilePath;
    QMap<QString, QStringList> sourceFileCache;
    
    QMap<uint32_t, int> addressToLine;  // Maps code address to line number

    const int NUM_INSTRUCTIONS = 128;
    const int INSTRUCTIONS_BEFORE_PC = 32;  // Show 32 instructions before PC
};

#endif // CODE_VIEW_H
