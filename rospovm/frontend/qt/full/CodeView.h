#ifndef CODE_VIEW_H
#define CODE_VIEW_H

#include <QWidget>
#include <QPlainTextEdit>
#include <QMap>
#include <QStringList>
#include <QEvent>
#include <cstdint>

namespace KSyntaxHighlighting {
class Repository;
class SyntaxHighlighter;
}

class VMController;

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

protected:
    bool eventFilter(QObject *watched, QEvent *event) override;

private:
    void createUI();
    void setupSyntaxHighlighting();
    void populateCode();
    void drawJumpVisualization();
    void centerOnPC();
    void updateSourcePanel(uint32_t address);
    void loadSourceFile(const QString &sourceFilePath);
    void highlightSourceLine(uint32_t oneBasedLine);
    QString resolveCodeRegisterTooltip(const QPoint &viewportPos) const;

    VMController *vmController;
    QPlainTextEdit *codeDisplay;
    QPlainTextEdit *sourceInfoDisplay;  // Display for source location info
    QPlainTextEdit *sourceCodeDisplay;
    KSyntaxHighlighting::Repository *syntaxRepository;
    KSyntaxHighlighting::SyntaxHighlighter *codeHighlighter;
    KSyntaxHighlighting::SyntaxHighlighter *sourceHighlighter;
    
    uint32_t codeStartAddress;
    uint32_t codeEndAddress;
    uint32_t currentPC = 0;
    uint32_t lastDisplayedPC = 0;  // Track if PC changed significantly

    QString currentSourceFilePath;
    QMap<QString, QStringList> sourceFileCache;
    
    QMap<uint32_t, int> addressToLine;  // Maps code address to line number
    QMap<int, uint32_t> lineToAddress;  // Reverse map for hover lookups

    const int NUM_INSTRUCTIONS = 256;
    const int INSTRUCTIONS_BEFORE_PC = 64;  // Show 64 instructions before PC
};

#endif // CODE_VIEW_H
