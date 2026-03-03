#include "MainWindow.h"
#include "VMController.h"
#include "CodeView.h"
#include "DebugControlPanel.h"
#include "RegisterView.h"
#include "MemoryView.h"
#include "Display.h"
#include "LogView.h"

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
#include <QMessageBox>
#include <QTimer>
#include <QScrollArea>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent),
      vmController(std::make_unique<VMController>(this)),
      codeView(new CodeView(this)),
      debugPanel(new DebugControlPanel(this)),
      registerView(new RegisterView(this)),
      memoryView(new MemoryView(this)),
      displayWidget(new VMDisplay(this)),
      logView(new LogView(this))
{
    setWindowTitle("RospOS VM Debugger");
    setGeometry(100, 100, 1600, 1000);

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
    stepAction->setShortcut(Qt::Key_F10);
    connect(stepAction, &QAction::triggered, this, &MainWindow::onStep);

    QAction *runAction = debugMenu->addAction(tr("&Run"));
    runAction->setShortcut(Qt::Key_F5);
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
               "code analysis, registers, and memory views."));
    });
}

void MainWindow::createToolBar()
{
    QToolBar *toolBar = addToolBar(tr("File Tools"));
    toolBar->setObjectName("FileToolBar");

    QAction *loadAction = toolBar->addAction(tr("Load Binary"));
    connect(loadAction, &QAction::triggered, this, &MainWindow::onLoadFile);
    loadButton = loadAction;
}

void MainWindow::createCentralWidget()
{
    // Main layout structure:
    // Top: File operations toolbar (already in toolbar)
    // Center: Vertical splitter with:
    //   - Top: Horizontal splitter with:
    //     - Left: Debug control panel
    //     - Center: Code view (primary)
    //     - Right: Register, Memory, Display views
    //   - Bottom: Log view

    QWidget *centralWidget = new QWidget(this);
    QVBoxLayout *mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // Main vertical splitter (top content vs logs)
    QSplitter *verticalSplitter = new QSplitter(Qt::Vertical);
    verticalSplitter->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // Top horizontal splitter (debug panel | code | sidebar)
    QSplitter *horizontalSplitter = new QSplitter(Qt::Horizontal);
    horizontalSplitter->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // Left sidebar: Debug control panel
    debugPanel->setMaximumWidth(280);
    debugPanel->setMinimumWidth(250);
    horizontalSplitter->addWidget(debugPanel);

    // Center: Code view (main focus)
    codeView->setMinimumWidth(400);
    horizontalSplitter->addWidget(codeView);

    // Right sidebar: Register, Memory, Display
    QSplitter *rightSidebar = new QSplitter(Qt::Vertical);
    rightSidebar->addWidget(registerView);
    rightSidebar->addWidget(memoryView);

    QScrollArea *displayScrollArea = new QScrollArea(this);
    displayScrollArea->setWidget(displayWidget);
    displayScrollArea->setWidgetResizable(false);
    displayScrollArea->setAlignment(Qt::AlignTop | Qt::AlignLeft);
    displayScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    displayScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rightSidebar->addWidget(displayScrollArea);
    rightSidebar->setMaximumWidth(350);
    rightSidebar->setMinimumWidth(250);
    rightSidebar->setCollapsible(0, false);
    rightSidebar->setCollapsible(1, false);
    rightSidebar->setCollapsible(2, false);

    horizontalSplitter->addWidget(rightSidebar);

    // Set splitter sizes (left panel, code view, right sidebar)
    horizontalSplitter->setSizes({250, 800, 300});
    // Configure horizontal splitter stretch factors for smooth resizing
    horizontalSplitter->setStretchFactor(0, 0);  // Debug panel: fixed size
    horizontalSplitter->setStretchFactor(1, 1);  // Code view: flexible
    horizontalSplitter->setStretchFactor(2, 0);  // Right sidebar: fixed size
    horizontalSplitter->setCollapsible(0, false);
    horizontalSplitter->setCollapsible(1, false);
    horizontalSplitter->setCollapsible(2, false);

    verticalSplitter->addWidget(horizontalSplitter);
    verticalSplitter->addWidget(logView);
    logView->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    // DON'T call setSizes() before widget is shown - let stretch factors handle initial layout
    // Configure vertical splitter stretch factors for smooth resizing
    verticalSplitter->setStretchFactor(0, 4);  // Main content: flexible (4x weight)
    verticalSplitter->setStretchFactor(1, 1);  // Log view: flexible (1x weight)
    verticalSplitter->setCollapsible(0, false);
    verticalSplitter->setCollapsible(1, false);

    QTimer::singleShot(0, this, [horizontalSplitter, rightSidebar, verticalSplitter]() {
        horizontalSplitter->setSizes({250, 800, 300});
        rightSidebar->setSizes({1, 1, 1});
        verticalSplitter->setSizes({800, 200});
    });

    mainLayout->addWidget(verticalSplitter);

    setCentralWidget(centralWidget);
}

void MainWindow::createStatusBar()
{
    statusLabel = new QLabel(tr("Status: Ready"));
    statusBar()->addWidget(statusLabel, 1);
}

void MainWindow::setupConnections()
{
    // Connect VM controller signals to main window
    connect(vmController.get(), &VMController::stateChanged, this, &MainWindow::onVMStateChanged);
    connect(vmController.get(), &VMController::error, this, &MainWindow::onVMError);
    connect(vmController.get(), &VMController::executionStarted, this, &MainWindow::onExecutionStarted);
    connect(vmController.get(), &VMController::executionStopped, this, &MainWindow::onExecutionStopped);

    // Connect views to controller
    codeView->setVMController(vmController.get());
    registerView->setVMController(vmController.get());
    memoryView->setVMController(vmController.get());
    debugPanel->setVMController(vmController.get());

    // Connect debug panel signals
    connect(debugPanel, &DebugControlPanel::stepClicked, this, &MainWindow::onStep);
    connect(debugPanel, &DebugControlPanel::runClicked, this, &MainWindow::onRun);
    connect(debugPanel, &DebugControlPanel::pauseClicked, this, &MainWindow::onPause);
    connect(debugPanel, &DebugControlPanel::resetClicked, this, &MainWindow::onReset);
    connect(debugPanel, &DebugControlPanel::speedChanged, this, &MainWindow::onSpeedChanged);
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
    onVMStateChanged();
}

void MainWindow::onVMStateChanged()
{
    // Update all views
    codeView->refresh();
    registerView->refresh();
    memoryView->refresh();
    
    // Update debug panel
    uint32_t pc = vmController->getProgramCounter();
    debugPanel->setPCLabel(pc);
}

void MainWindow::onVMError(const QString &message)
{
    statusLabel->setText(tr("Status: ") + message);
    debugPanel->setStatus(message);
}

void MainWindow::onExecutionStarted()
{
    statusLabel->setText(tr("Status: Running..."));
    debugPanel->setStatus("Running");
    debugPanel->setStepEnabled(false);
    debugPanel->setRunEnabled(false);
    debugPanel->setPauseEnabled(true);
}

void MainWindow::onExecutionStopped()
{
    statusLabel->setText(tr("Status: Stopped"));
    debugPanel->setStatus("Stopped");
    debugPanel->setStepEnabled(true);
    debugPanel->setRunEnabled(true);
    debugPanel->setPauseEnabled(false);
    onVMStateChanged();
}

void MainWindow::onSpeedChanged(int value)
{
    // Speed slider for continuous execution (future feature)
    Q_UNUSED(value);
}
