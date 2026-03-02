#ifndef MAIN_WINDOW_H
#define MAIN_WINDOW_H

#include <QMainWindow>
#include <QLabel>
#include <QAction>
#include <QSlider>
#include <memory>

class VMController;
class DisassemblyView;
class RegisterView;
class MemoryView;

class MainWindow : public QMainWindow
{
    Q_OBJECT

public:
    MainWindow(QWidget *parent = nullptr);
    ~MainWindow();

private slots:
    void onLoadFile();
    void onStep();
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
    DisassemblyView *disassemblyView;
    RegisterView *registerView;
    MemoryView *memoryView;

    // UI Controls
    QAction *loadButton;
    QAction *stepButton;
    QAction *runButton;
    QAction *pauseButton;
    QAction *resetButton;
    QSlider *speedSlider;
    QLabel *statusLabel;
    QLabel *pcLabel;
};

#endif // MAIN_WINDOW_H
