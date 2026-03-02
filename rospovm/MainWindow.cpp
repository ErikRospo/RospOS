#include "MainWindow.h"
#include "VMController.h"
#include "DisassemblyView.h"
#include "RegisterView.h"
#include "MemoryView.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QSplitter>
#include <QMenuBar>
#include <QMenu>
#include <QToolBar>
#include <QFileDialog>
#include <QStatusBar>
#include <QGroupBox>
#include <QLabel>
#include <QSlider>
#include <QSpinBox>
#include <QMessageBox>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent),
      vmController(std::make_unique<VMController>(this)),
      disassemblyView(new DisassemblyView(this)),
      registerView(new RegisterView(this)),
      memoryView(new MemoryView(this))
{
    setWindowTitle("RospOS VM Debugger");
    setGeometry(100, 100, 1400, 900);

    createMenuBar();
    createToolBar();
    createCentralWidget();
    createStatusBar();
    setupConnections();
}

MainWindow::~MainWindow() = default;

void MainWindow::createMenuBar()
{
    QMenu *fileMenu = menuBar()->addMenu(tr("&File"));

    QAction *openAction = fileMenu->addAction(tr("&Open Binary..."));
    openAction->setShortcut(QKeySequence::Open);
    connect(openAction, &QAction::triggered, this, &MainWindow::onLoadFile);

    fileMenu->addSeparator();

    QAction *exitAction = fileMenu->addAction(tr("E&xit"));
    exitAction->setShortcut(QKeySequence::Quit);
    connect(exitAction, &QAction::triggered, this, &QWidget::close);

    QMenu *debugMenu = menuBar()->addMenu(tr("&Debug"));

    QAction *stepAction = debugMenu->addAction(tr("&Step"));
    stepAction->setShortcut(Qt::CTRL | Qt::Key_S);
    connect(stepAction, &QAction::triggered, this, &MainWindow::onStep);

    QAction *runAction = debugMenu->addAction(tr("&Run"));
    runAction->setShortcut(Qt::CTRL | Qt::Key_R);
    connect(runAction, &QAction::triggered, this, &MainWindow::onRun);

    QAction *pauseAction = debugMenu->addAction(tr("&Pause"));
    pauseAction->setShortcut(Qt::CTRL | Qt::Key_P);
    connect(pauseAction, &QAction::triggered, this, &MainWindow::onPause);

    debugMenu->addSeparator();

    QAction *resetAction = debugMenu->addAction(tr("&Reset"));
    resetAction->setShortcut(Qt::CTRL | Qt::Key_Backspace);
    connect(resetAction, &QAction::triggered, this, &MainWindow::onReset);

    QMenu *helpMenu = menuBar()->addMenu(tr("&Help"));
    QAction *aboutAction = helpMenu->addAction(tr("&About"));
    connect(aboutAction, &QAction::triggered, this, [this]() {
        QMessageBox::about(this, tr("About RospOS VM Debugger"),
            tr("RospOS Virtual Machine Debugger\n\n"
               "A graphical debugger for the RospOS VM with "
               "disassembly, register, and memory views."));
    });
}

void MainWindow::createToolBar()
{
    QToolBar *debugToolBar = addToolBar(tr("Debug Controls"));
    debugToolBar->setObjectName("DebugToolBar");

    QAction *loadAction = debugToolBar->addAction(tr("Load Binary"));
    connect(loadAction, &QAction::triggered, this, &MainWindow::onLoadFile);
    loadButton = loadAction;

    debugToolBar->addSeparator();

    QAction *stepAction = debugToolBar->addAction(tr("Step"));
    connect(stepAction, &QAction::triggered, this, &MainWindow::onStep);
    stepButton = stepAction;

    QAction *runAction = debugToolBar->addAction(tr("Run"));
    connect(runAction, &QAction::triggered, this, &MainWindow::onRun);
    runButton = runAction;

    QAction *pauseAction = debugToolBar->addAction(tr("Pause"));
    connect(pauseAction, &QAction::triggered, this, &MainWindow::onPause);
    pauseButton = pauseAction;
    pauseButton->setEnabled(false);

    debugToolBar->addSeparator();

    QAction *resetAction = debugToolBar->addAction(tr("Reset"));
    connect(resetAction, &QAction::triggered, this, &MainWindow::onReset);
    resetButton = resetAction;

    debugToolBar->addSeparator();
    debugToolBar->addWidget(new QLabel(tr("Speed:")));

    speedSlider = new QSlider(Qt::Horizontal);
    speedSlider->setMinimum(1);
    speedSlider->setMaximum(100);
    speedSlider->setValue(50);
    speedSlider->setMaximumWidth(150);
    debugToolBar->addWidget(speedSlider);
}

void MainWindow::createCentralWidget()
{
    // Main splitter for horizontal layout
    QSplitter *mainSplitter = new QSplitter(Qt::Horizontal);

    // Left side: Disassembly view
    mainSplitter->addWidget(disassemblyView);

    // Right side: Register and Memory views (vertical split)
    QSplitter *rightSplitter = new QSplitter(Qt::Vertical);
    rightSplitter->addWidget(registerView);
    rightSplitter->addWidget(memoryView);

    mainSplitter->setSizes({700, 700});
    rightSplitter->setSizes({400, 400});

    setCentralWidget(mainSplitter);
}

void MainWindow::createStatusBar()
{
    statusLabel = new QLabel(tr("Status: Ready"));
    pcLabel = new QLabel(tr("PC: 0x0000"));

    statusBar()->addWidget(statusLabel, 1);
    statusBar()->addPermanentWidget(pcLabel);
}

void MainWindow::setupConnections()
{
    // Connect VM controller signals
    connect(vmController.get(), &VMController::stateChanged, this, &MainWindow::onVMStateChanged);
    connect(vmController.get(), &VMController::error, this, &MainWindow::onVMError);
    connect(vmController.get(), &VMController::executionStarted, this, &MainWindow::onExecutionStarted);
    connect(vmController.get(), &VMController::executionStopped, this, &MainWindow::onExecutionStopped);

    // Connect views to controller
    disassemblyView->setVMController(vmController.get());
    registerView->setVMController(vmController.get());
    memoryView->setVMController(vmController.get());

    // Connect speed slider
    connect(speedSlider, QOverload<int>::of(&QSlider::valueChanged), this, &MainWindow::onSpeedChanged);
}

void MainWindow::onLoadFile()
{
    QString fileName = QFileDialog::getOpenFileName(this,
        tr("Open RospOS Binary"), "",
        tr("Binary Files (*.rosp);;All Files (*)"));

    if (!fileName.isEmpty()) {
        if (vmController->loadBinaryFile(fileName)) {
            statusLabel->setText(tr("Status: Binary loaded"));
        } else {
            statusLabel->setText(tr("Status: Failed to load binary"));
        }
        onVMStateChanged();
    }
}

void MainWindow::onStep()
{
    vmController->step();
}

void MainWindow::onRun()
{
    vmController->run();
}

void MainWindow::onPause()
{
    vmController->pause();
}

void MainWindow::onReset()
{
    vmController->reset();
    statusLabel->setText(tr("Status: VM Reset"));
}

void MainWindow::onVMStateChanged()
{
    // Update all views
    disassemblyView->refresh();
    registerView->refresh();
    memoryView->refresh();
}

void MainWindow::onVMError(const QString &message)
{
    statusLabel->setText(tr("Status: ") + message);
}

void MainWindow::onExecutionStarted()
{
    statusLabel->setText(tr("Status: Running..."));
    stepButton->setEnabled(false);
    runButton->setEnabled(false);
    pauseButton->setEnabled(true);
}

void MainWindow::onExecutionStopped()
{
    statusLabel->setText(tr("Status: Stopped"));
    stepButton->setEnabled(true);
    runButton->setEnabled(true);
    pauseButton->setEnabled(false);
}

void MainWindow::onSpeedChanged(int value)
{
    // Speed slider for continuous execution (future feature)
    Q_UNUSED(value);
}
