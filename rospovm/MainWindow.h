#ifndef MAIN_WINDOW_H
#define MAIN_WINDOW_H

#include <QMainWindow>
#include <QLabel>
#include <QAction>
#include <memory>

class VMController;
class CodeView;
class DebugControlPanel;
class RegisterView;
class MemoryView;
class VMDisplay;
class LogView;
class TTYWidget;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();
    void loadBinaryFile(const QString &filePath);

private slots:
    void onLoadFile();
    void onStep();
    void onStepBack();
    void onRun();
    void onPause();
    void onReset();
    void onVMStateChanged();
    void onVMError(const QString &message);
    void onExecutionStarted();
    void onExecutionStopped();
    void onSpeedChanged(int value);

private:
    void createMenuBar();
    void createToolBar();
    void createCentralWidget();
    void createStatusBar();
    void setupConnections();

    // Member variables
    std::unique_ptr<VMController> vmController;
    CodeView *codeView;
    DebugControlPanel *debugPanel;
    RegisterView *registerView;
    MemoryView *memoryView;
    VMDisplay *displayWidget;
    TTYWidget *ttyWidget;
    LogView *logView;

    // UI Controls
    QAction *loadButton;
    QAction *stepAction;
    QAction *stepBackAction;
    QAction *runAction;
    QAction *pauseAction;
    QAction *resetAction;
    QLabel *statusLabel;
};

#endif // MAIN_WINDOW_H
