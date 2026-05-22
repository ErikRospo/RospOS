#include "Display.h"
#include "TTY.h"
#include "TTYWidget.h"
#include "VMControllerCore.h"

#include <QApplication>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QHBoxLayout>
#include <QLabel>
#include <QMetaObject>
#include <QPushButton>
#include <QSlider>
#include <QTemporaryFile>
#include <QVBoxLayout>
#include <QWidget>

class HtmlWindow : public QWidget
{
public:
    explicit HtmlWindow(QWidget *parent = nullptr)
        : QWidget(parent),
          controller(new VMControllerCore(this)),
          display(new VMDisplay(this)),
          tty(new TTYWidget(this)),
          status(new QLabel(tr("Status: Ready"), this))
    {
        setWindowTitle(tr("RospOS VM"));
        setMinimumSize(900, 900);

        auto *loadButton = new QPushButton(tr("Load"), this);
        auto *stepButton = new QPushButton(tr("Step"), this);
        auto *runButton = new QPushButton(tr("Run"), this);
        auto *pauseButton = new QPushButton(tr("Pause"), this);
        auto *resetButton = new QPushButton(tr("Reset"), this);

        auto *speedSlider = new QSlider(Qt::Horizontal, this);
        speedSlider->setMinimum(0);
        speedSlider->setMaximum(14);
        speedSlider->setValue(4);

        auto *controls = new QHBoxLayout();
        controls->addWidget(loadButton);
        controls->addWidget(stepButton);
        controls->addWidget(runButton);
        controls->addWidget(pauseButton);
        controls->addWidget(resetButton);
        controls->addWidget(new QLabel(tr("Speed"), this));
        controls->addWidget(speedSlider, 1);

        auto *layout = new QVBoxLayout(this);
        layout->addLayout(controls);
        layout->addWidget(status);
        layout->addWidget(display, 1, Qt::AlignCenter);
        layout->addWidget(tty, 1);
        setLayout(layout);

        connect(loadButton, &QPushButton::clicked, this, [this]() {
#ifdef __EMSCRIPTEN__
            QFileDialog::getOpenFileContent(
                QStringLiteral("Binary Files (*.rosp);;All Files (*)"),
                [this](const QString &fileName, const QByteArray &fileContent) {
                    if (fileName.isEmpty() || fileContent.isEmpty()) {
                        status->setText(tr("Status: No file selected"));
                        return;
                    }

                    QTemporaryFile tempFile(QDir::tempPath() + QStringLiteral("/rospovm-web-XXXXXX.rosp"));
                    tempFile.setAutoRemove(false);
                    if (!tempFile.open()) {
                        status->setText(tr("Status: Failed to prepare browser upload"));
                        return;
                    }

                    if (tempFile.write(fileContent) != fileContent.size()) {
                        status->setText(tr("Status: Failed to stage uploaded binary"));
                        return;
                    }

                    const QString stagedPath = tempFile.fileName();
                    tempFile.close();
                    loadBinaryFile(stagedPath);
                });
#else
            const QString fileName = QFileDialog::getOpenFileName(
                this,
                tr("Open RospOS Binary"),
                QString(),
                tr("Binary Files (*.rosp);;All Files (*)"));
            if (fileName.isEmpty()) {
                return;
            }
            loadBinaryFile(fileName);
#endif
        });

        connect(stepButton, &QPushButton::clicked, controller, &VMControllerCore::step);
        connect(runButton, &QPushButton::clicked, controller, &VMControllerCore::run);
        connect(pauseButton, &QPushButton::clicked, controller, &VMControllerCore::pause);
        connect(resetButton, &QPushButton::clicked, controller, &VMControllerCore::reset);
        connect(speedSlider, &QSlider::valueChanged, controller, &VMControllerCore::setExecutionSpeedLevel);

        connect(controller, &VMControllerCore::stateChanged, this, [this]() {
            status->setText(QStringLiteral("Status: PC=0x%1")
                                .arg(controller->getProgramCounter(), 8, 16, QChar('0')));
            display->update();
        });
        connect(controller, &VMControllerCore::executionStarted, this, [this]() {
            status->setText(tr("Status: Running"));
        });
        connect(controller, &VMControllerCore::executionStopped, this, [this]() {
            status->setText(tr("Status: Stopped"));
        });
        connect(controller, &VMControllerCore::error, this, [this](const QString &message) {
            status->setText(tr("Status: %1").arg(message));
        });

        TTYSetWriteCallback([this](uint8_t value) {
            QMetaObject::invokeMethod(tty, [this, value]() {
                tty->appendOutputByte(value);
            }, Qt::QueuedConnection);
        });
        TTYSetReadRequestCallback([this]() {
            QMetaObject::invokeMethod(tty, [this]() {
                tty->requestInputFocusHighlight();
            }, Qt::QueuedConnection);
        });
    }

    ~HtmlWindow() override
    {
        TTYSetWriteCallback(nullptr);
        TTYSetReadRequestCallback(nullptr);
    }

    void loadBinaryFile(const QString &filePath)
    {
        if (controller->loadBinaryFile(filePath)) {
            status->setText(tr("Status: Loaded %1").arg(QFileInfo(filePath).fileName()));
        }
    }

private:
    VMControllerCore *controller;
    VMDisplay *display;
    TTYWidget *tty;
    QLabel *status;
};

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    HtmlWindow window;
    window.show();
    return app.exec();
}