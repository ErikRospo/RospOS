#include "MainWindow.h"
#include "VMController.h"
#include "CodeView.h"
#include "DebugControlPanel.h"
#include "RegisterView.h"
#include "MemoryView.h"
#include "Display.h"
#include "TTYWidget.h"
#include "TTY.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QSplitter>
#include <QMenuBar>
#include <QMenu>
#include <QToolBar>
#include <QFileDialog>
#include <QStatusBar>
#include <QStyle>
#include <QGroupBox>
#include <QLabel>
#include <QMessageBox>
#include <QMetaObject>
#include <QTimer>
#include <QScrollArea>
#include <QInputDialog>
#include <QFileInfo>
#include <QDateTime>
#include <QSettings>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent),
      vmController(std::make_unique<VMController>(this)),
      codeView(new CodeView(this)),
      debugPanel(new DebugControlPanel(this)),
      registerView(new RegisterView(this)),
      memoryView(new MemoryView(this)),
      displayWidget(new VMDisplay(this)),
    ttyWidget(new TTYWidget(this)),
    horizontalSplitter(nullptr),
    verticalSplitter(nullptr),
    rightSidebarSplitter(nullptr)
{
    setWindowTitle("RospOS VM Debugger");
    setGeometry(100, 100, 1600, 1000);

    createMenuBar();
    createToolBar();
    createCentralWidget();
    createStatusBar();
    setupConnections();
    restoreWindowSettings();
}

MainWindow::~MainWindow()
{
    TTYSetWriteCallback(nullptr);
    TTYSetReadRequestCallback(nullptr);
}

void MainWindow::closeEvent(QCloseEvent *event)
{
    saveWindowSettings();
    QMainWindow::closeEvent(event);
}

void MainWindow::restoreWindowSettings()
{
    QSettings settings("RospOS", "RospOSVMFullQt");
    const QByteArray geometry = settings.value("window/geometry").toByteArray();
    const QByteArray state = settings.value("window/state").toByteArray();
    const QByteArray horizontalState = settings.value("window/splitterHorizontal").toByteArray();
    const QByteArray verticalState = settings.value("window/splitterVertical").toByteArray();
    const QByteArray rightSidebarState = settings.value("window/splitterRightSidebar").toByteArray();

    if (!geometry.isEmpty()) {
        restoreGeometry(geometry);
    }
    if (!state.isEmpty()) {
        restoreState(state);
    }
    if (horizontalSplitter != nullptr && !horizontalState.isEmpty()) {
        horizontalSplitter->restoreState(horizontalState);
    }
    if (verticalSplitter != nullptr && !verticalState.isEmpty()) {
        verticalSplitter->restoreState(verticalState);
    }
    if (rightSidebarSplitter != nullptr && !rightSidebarState.isEmpty()) {
        rightSidebarSplitter->restoreState(rightSidebarState);
    }
}

void MainWindow::saveWindowSettings() const
{
    QSettings settings("RospOS", "RospOSVMFullQt");
    settings.setValue("window/geometry", saveGeometry());
    settings.setValue("window/state", saveState());
    if (horizontalSplitter != nullptr) {
        settings.setValue("window/splitterHorizontal", horizontalSplitter->saveState());
    }
    if (verticalSplitter != nullptr) {
        settings.setValue("window/splitterVertical", verticalSplitter->saveState());
    }
    if (rightSidebarSplitter != nullptr) {
        settings.setValue("window/splitterRightSidebar", rightSidebarSplitter->saveState());
    }
}

void MainWindow::loadBinaryFile(const QString &filePath)
{
    if (vmController->loadBinaryFile(filePath)) {
        statusLabel->setText(tr("Status: Binary loaded"));
    } else {
        statusLabel->setText(tr("Status: Failed to load binary"));
    }
    onVMStateChanged();
}

void MainWindow::createMenuBar()
{
    QMenu *fileMenu = menuBar()->addMenu(tr("&File"));

    QAction *openAction = fileMenu->addAction(tr("&Open Binary..."));
    openAction->setShortcut(QKeySequence::Open);
    connect(openAction, &QAction::triggered, this, &MainWindow::onLoadFile);

    QAction *exportAction = fileMenu->addAction(tr("Export Display as &PNG..."));
    exportAction->setShortcut(QKeySequence(Qt::CTRL | Qt::SHIFT | Qt::Key_S));
    connect(exportAction, &QAction::triggered, this, &MainWindow::onExportDisplayPng);

    fileMenu->addSeparator();

    QAction *exitAction = fileMenu->addAction(tr("&Exit"));
    exitAction->setShortcut(QKeySequence::Quit);
    connect(exitAction, &QAction::triggered, this, &QWidget::close);

    QMenu *debugMenu = menuBar()->addMenu(tr("&Debug"));

    QAction *stepAction = debugMenu->addAction(tr("&Step"));
    stepAction->setShortcut(Qt::Key_F10);
    connect(stepAction, &QAction::triggered, this, &MainWindow::onStep);

    QAction *stepBackAction = debugMenu->addAction(tr("Step &Back"));
    stepBackAction->setShortcut(QKeySequence(Qt::SHIFT | Qt::Key_F10));
    connect(stepBackAction, &QAction::triggered, this, &MainWindow::onStepBack);

    QAction *runAction = debugMenu->addAction(tr("&Run"));
    runAction->setShortcut(Qt::Key_F5);
    connect(runAction, &QAction::triggered, this, &MainWindow::onRun);

    QAction *pauseAction = debugMenu->addAction(tr("&Pause"));
    pauseAction->setShortcut(Qt::CTRL | Qt::Key_P);
    connect(pauseAction, &QAction::triggered, this, &MainWindow::onPause);

    debugMenu->addSeparator();

    QAction *restartAction = debugMenu->addAction(tr("&Restart"));
    restartAction->setShortcut(Qt::CTRL | Qt::Key_R);
    connect(restartAction, &QAction::triggered, this, &MainWindow::onRestart);

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
    toolBar->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

    QAction *loadAction = toolBar->addAction(tr("Load Binary"));
    loadAction->setIcon(style()->standardIcon(QStyle::SP_DirOpenIcon));
    connect(loadAction, &QAction::triggered, this, &MainWindow::onLoadFile);
    loadButton = loadAction;

    exportDisplayAction = toolBar->addAction(tr("Export PNG"));
    exportDisplayAction->setIcon(style()->standardIcon(QStyle::SP_DialogSaveButton));
    exportDisplayAction->setToolTip(tr("Export display framebuffer to a PNG file"));
    connect(exportDisplayAction, &QAction::triggered, this, &MainWindow::onExportDisplayPng);

    toolBar->addSeparator();

    stepBackAction = toolBar->addAction(tr("Step Back"));
    stepBackAction->setIcon(style()->standardIcon(QStyle::SP_MediaSkipBackward));
    stepBackAction->setShortcut(QKeySequence(Qt::SHIFT | Qt::Key_F10));
    stepBackAction->setToolTip(tr("Step the program backward 1 instruction (Shift + F10)"));
    connect(stepBackAction, &QAction::triggered, this, &MainWindow::onStepBack);
    stepBackAction->setEnabled(false);
    
    // Add step control buttons to toolbar
    stepAction = toolBar->addAction(tr("Step"));
    stepAction->setIcon(style()->standardIcon(QStyle::SP_MediaSkipForward));
    stepAction->setShortcut(Qt::Key_F10);
    stepAction->setToolTip(tr("Step the program forward 1 instruction (F10)"));
    connect(stepAction, &QAction::triggered, this, &MainWindow::onStep);



    runAction = toolBar->addAction(tr("Run"));
    runAction->setIcon(style()->standardIcon(QStyle::SP_MediaPlay));
    runAction->setShortcut(Qt::Key_F5);
    runAction->setToolTip(tr("Run the program continuously (F5)"));
    connect(runAction, &QAction::triggered, this, &MainWindow::onRun);

    pauseAction = toolBar->addAction(tr("Pause"));
    pauseAction->setIcon(style()->standardIcon(QStyle::SP_MediaPause));
    pauseAction->setShortcut(Qt::CTRL | Qt::Key_P);
    pauseAction->setToolTip(tr("Pause the program (Ctrl + P)"));
    connect(pauseAction, &QAction::triggered, this, &MainWindow::onPause);
    pauseAction->setEnabled(false);

    restartAction = toolBar->addAction(tr("Restart"));
    restartAction->setIcon(style()->standardIcon(QStyle::SP_BrowserReload));
    restartAction->setShortcut(Qt::CTRL | Qt::Key_R);
    restartAction->setToolTip(tr("Reload the current binary without clearing memory (Ctrl + R)"));
    connect(restartAction, &QAction::triggered, this, &MainWindow::onRestart);

    resetAction = toolBar->addAction(tr("Reset"));
    resetAction->setIcon(style()->standardIcon(QStyle::SP_DialogResetButton));
    resetAction->setShortcut(Qt::CTRL | Qt::Key_Backspace);
    resetAction->setToolTip(tr("Hard reset the VM and clear loaded state (Ctrl + Backspace)"));
    connect(resetAction, &QAction::triggered, this, &MainWindow::onReset);
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
    //   - Bottom: TTY view

    QWidget *centralWidget = new QWidget(this);
    QVBoxLayout *mainLayout = new QVBoxLayout(centralWidget);
    mainLayout->setContentsMargins(0, 0, 0, 0);
    mainLayout->setSpacing(0);

    // Main vertical splitter (top content vs tty)
    verticalSplitter = new QSplitter(Qt::Vertical);
    verticalSplitter->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // Top horizontal splitter (debug panel | code | sidebar)
    horizontalSplitter = new QSplitter(Qt::Horizontal);
    horizontalSplitter->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    // Left sidebar: Debug control panel
    debugPanel->setMaximumWidth(280);
    debugPanel->setMinimumWidth(250);
    horizontalSplitter->addWidget(debugPanel);

    // Center: Code view (main focus)
    codeView->setMinimumWidth(400);
    horizontalSplitter->addWidget(codeView);

    // Right sidebar: Register, Memory, Display
    rightSidebarSplitter = new QSplitter(Qt::Vertical);
    rightSidebarSplitter->addWidget(registerView);
    rightSidebarSplitter->addWidget(memoryView);

    QScrollArea *displayScrollArea = new QScrollArea(this);
    displayScrollArea->setWidget(displayWidget);
    displayScrollArea->setWidgetResizable(false);
    displayScrollArea->setAlignment(Qt::AlignTop | Qt::AlignLeft);
    displayScrollArea->setHorizontalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    displayScrollArea->setVerticalScrollBarPolicy(Qt::ScrollBarAsNeeded);
    rightSidebarSplitter->addWidget(displayScrollArea);

    rightSidebarSplitter->setMaximumWidth(350);
    rightSidebarSplitter->setMinimumWidth(250);
    rightSidebarSplitter->setCollapsible(0, false);
    rightSidebarSplitter->setCollapsible(1, false);
    rightSidebarSplitter->setCollapsible(2, false);

    horizontalSplitter->addWidget(rightSidebarSplitter);

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
    verticalSplitter->addWidget(ttyWidget);
    ttyWidget->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);
    // DON'T call setSizes() before widget is shown - let stretch factors handle initial layout
    // Configure vertical splitter stretch factors for smooth resizing
    verticalSplitter->setStretchFactor(0, 4);  // Main content: flexible (4x weight)
    verticalSplitter->setStretchFactor(1, 1);  // tty view: flexible (1x weight)
    verticalSplitter->setCollapsible(0, false);
    verticalSplitter->setCollapsible(1, false);

    QSettings settings("RospOS", "RospOSVMFullQt");
    const bool hasSavedHorizontal = settings.contains("window/splitterHorizontal");
    const bool hasSavedVertical = settings.contains("window/splitterVertical");
    const bool hasSavedRightSidebar = settings.contains("window/splitterRightSidebar");

    if (!hasSavedHorizontal || !hasSavedVertical || !hasSavedRightSidebar) {
        QTimer::singleShot(0, this, [this]() {
            if (!horizontalSplitter || !rightSidebarSplitter || !verticalSplitter) {
                return;
            }
            horizontalSplitter->setSizes({250, 800, 300});
            rightSidebarSplitter->setSizes({1, 1, 1});
            verticalSplitter->setSizes({800, 200});
        });
    }

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
    TTYSetWriteCallback([this](uint8_t value) {
        QMetaObject::invokeMethod(ttyWidget, [this, value]() {
            ttyWidget->appendOutputByte(value);
        }, Qt::QueuedConnection);
    });

    TTYSetReadRequestCallback([this]() {
        QMetaObject::invokeMethod(ttyWidget, [this]() {
            ttyWidget->requestInputFocusHighlight();
        }, Qt::QueuedConnection);
    });

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

void MainWindow::onExportDisplayPng()
{
    bool ok = false;
    const int scaleFactor = QInputDialog::getInt(
        this,
        tr("Export Display as PNG"),
        tr("Scale factor:"),
        4,
        1,
        32,
        1,
        &ok);

    if (!ok) {
        return;
    }

    const QString defaultName = QString("display_%1_x%2.png")
                                    .arg(QDateTime::currentDateTime().toString("yyyyMMdd_HHmmss"))
                                    .arg(scaleFactor);

    QString fileName = QFileDialog::getSaveFileName(
        this,
        tr("Save Display PNG"),
        defaultName,
        tr("PNG Image (*.png)"));

    if (fileName.isEmpty()) {
        return;
    }

    QFileInfo info(fileName);
    if (info.suffix().isEmpty()) {
        fileName += ".png";
    }

    QString errorMessage;
    if (!displayWidget->exportToPng(fileName, scaleFactor, &errorMessage)) {
        QMessageBox::warning(this, tr("Export Failed"), errorMessage);
        return;
    }

    statusLabel->setText(tr("Status: Display exported to %1").arg(fileName));
}

void MainWindow::onStepBack()
{
    vmController->stepBackward();
}

void MainWindow::onRun()
{
    vmController->run();
}

void MainWindow::onPause()
{
    vmController->pause();
}

void MainWindow::onRestart()
{
    if (vmController->restart()) {
        statusLabel->setText(tr("Status: VM Restarted (binary reloaded)"));
    } else {
        statusLabel->setText(tr("Status: Restart failed"));
    }
    onVMStateChanged();
}

void MainWindow::onReset()
{
    vmController->reset();
    statusLabel->setText(tr("Status: VM Reset (hard)"));
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
    const bool canStepBack = vmController->canStepBackward();
    debugPanel->setPCLabel(pc);
    debugPanel->setStepBackEnabled(canStepBack);
    stepBackAction->setEnabled(canStepBack);
}

void MainWindow::onVMError(const QString &message)
{
    hasExecutionError = true;
    lastExecutionError = message;
    statusLabel->setText(tr("Status: ") + message);
    debugPanel->setStatus(message);
}

void MainWindow::onExecutionStarted()
{
    hasExecutionError = false;
    lastExecutionError.clear();
    statusLabel->setText(tr("Status: Running..."));
    debugPanel->setStatus("Running");
    stepAction->setEnabled(false);
    stepBackAction->setEnabled(false);
    runAction->setEnabled(false);
    pauseAction->setEnabled(true);
}

void MainWindow::onExecutionStopped()
{
    if (hasExecutionError && !lastExecutionError.isEmpty()) {
        statusLabel->setText(tr("Status: Stopped (Error: %1)").arg(lastExecutionError));
        debugPanel->setStatus(tr("Stopped (Error: %1)").arg(lastExecutionError));
    } else {
        statusLabel->setText(tr("Status: Stopped"));
        debugPanel->setStatus("Stopped");
    }
    stepAction->setEnabled(true);
    stepBackAction->setEnabled(vmController->canStepBackward());
    runAction->setEnabled(true);
    pauseAction->setEnabled(false);
    onVMStateChanged();
}

void MainWindow::onSpeedChanged(int value)
{
    vmController->setExecutionSpeedLevel(value);
}
