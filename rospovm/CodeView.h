#ifndef CODE_VIEW_H
#define CODE_VIEW_H

#include <QWidget>
#include <QPlainTextEdit>
#include <QSyntaxHighlighter>
#include <QTextDocument>
#include <QRegularExpression>
#include <QMap>
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

    VMController *vmController;
    QPlainTextEdit *codeDisplay;
    AssemblySyntaxHighlighter *highlighter;
    
    uint32_t codeStartAddress = 0x10000;
    uint32_t codeEndAddress = 0x20000;
    uint32_t currentPC = 0;
    
    QMap<uint32_t, int> addressToLine;  // Maps code address to line number

    const int NUM_INSTRUCTIONS = 128;
};

#endif // CODE_VIEW_H
