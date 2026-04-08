#ifndef MAIN_WINDOW_H
#define MAIN_WINDOW_H

#include <QMainWindow>
#include <QLabel>
#include <QAction>
#include <QString>
#include <QCloseEvent>
#include <memory>

#include "ExecutionBackend.h"

class VMController;
class CodeView;
class DebugControlPanel;
class RegisterView;
class MemoryView;
class VMDisplay;
class LogView;
class TTYWidget;
class QSplitter;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr, ExecutionBackend backend = ExecutionBackend::Interpreter);
    ~MainWindow();
    void loadBinaryFile(const QString &filePath);

private slots:
    void onLoadFile();
    void onExportDisplayPng();
    void onStep();
    void onStepBack();
    void onRun();
    void onPause();
    void onRestart();
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
    void restoreWindowSettings();
    void saveWindowSettings() const;

protected:
    void closeEvent(QCloseEvent *event) override;

    // Member variables
    std::unique_ptr<VMController> vmController;
    CodeView *codeView;
    DebugControlPanel *debugPanel;
    RegisterView *registerView;
    MemoryView *memoryView;
    VMDisplay *displayWidget;
    TTYWidget *ttyWidget;
    LogView *logView;
    QSplitter *horizontalSplitter;
    QSplitter *verticalSplitter;
    QSplitter *rightSidebarSplitter;

    // UI Controls
    QAction *loadButton;
    QAction *exportDisplayAction;
    QAction *stepAction;
    QAction *stepBackAction;
    QAction *runAction;
    QAction *pauseAction;
    QAction *restartAction;
    QAction *resetAction;
    QLabel *statusLabel;
    bool hasExecutionError = false;
    QString lastExecutionError;
};

#endif // MAIN_WINDOW_H
