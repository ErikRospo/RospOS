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

#ifndef ROSPOSVM_DEFAULT_BINARY_FILE
#define ROSPOSVM_DEFAULT_BINARY_FILE ""
#endif

#ifndef ROSPOSVM_DEFAULT_BLOCKDEV_FILE
#define ROSPOSVM_DEFAULT_BLOCKDEV_FILE ""
#endif

namespace {

QString defaultBinaryFilePath()
{
    return QStringLiteral(ROSPOSVM_DEFAULT_BINARY_FILE);
}

QString defaultBlockDeviceFilePath()
{
    return QStringLiteral(ROSPOSVM_DEFAULT_BLOCKDEV_FILE);
}

QString stageUploadedFile(const QByteArray &fileContent, const QString &suffix, QString *errorMessage)
{
    QTemporaryFile tempFile(QDir::tempPath() + QStringLiteral("/rospovm-web-XXXXXX.") + suffix);
    tempFile.setAutoRemove(false);
    if (!tempFile.open()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("Failed to prepare browser upload");
        }
        return QString();
    }

    if (tempFile.write(fileContent) != fileContent.size()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("Failed to stage uploaded file");
        }
        return QString();
    }

    const QString stagedPath = tempFile.fileName();
    tempFile.close();
    return stagedPath;
}

} // namespace

class HtmlWindow : public QWidget
{
public:
    explicit HtmlWindow(QWidget *parent = nullptr)
        : QWidget(parent),
          controller(new VMControllerCore(this, defaultBlockDeviceFilePath())),
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
        speedSlider->setValue(13);
        
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
                QStringLiteral("RospOS Files (*.rosp *.blockdev);;All Files (*)"),
                [this](const QString &fileName, const QByteArray &fileContent) {
                    if (fileName.isEmpty() || fileContent.isEmpty()) {
                        status->setText(tr("Status: No file selected"));
                        return;
                    }

                    const QString suffix = QFileInfo(fileName).suffix().toLower();
                    QString stageError;
                    const QString stagedPath = stageUploadedFile(fileContent, suffix, &stageError);
                    if (stagedPath.isEmpty()) {
                        status->setText(tr("Status: %1").arg(stageError));
                        return;
                    }

                    if (suffix == QStringLiteral("blockdev")) {
                        if (controller->setBlockDeviceFile(stagedPath)) {
                            status->setText(tr("Status: Loaded %1").arg(QFileInfo(fileName).fileName()));
                        }
                        return;
                    }

                    if (suffix == QStringLiteral("rosp")) {
                        loadBinaryFile(stagedPath);
                        return;
                    }

                    status->setText(tr("Status: Unsupported file type"));
                });
#else
            const QString fileName = QFileDialog::getOpenFileName(
                this,
                tr("Open RospOS File"),
                QString(),
                tr("RospOS Files (*.rosp *.blockdev);;All Files (*)"));
            if (fileName.isEmpty()) {
                return;
            }
            const QString suffix = QFileInfo(fileName).suffix().toLower();
            if (suffix == QStringLiteral("blockdev")) {
                if (controller->setBlockDeviceFile(fileName)) {
                    status->setText(tr("Status: Loaded %1").arg(QFileInfo(fileName).fileName()));
                }
                return;
            }

            if (suffix == QStringLiteral("rosp")) {
                loadBinaryFile(fileName);
                return;
            }

            status->setText(tr("Status: Unsupported file type"));
#endif
        });

        connect(stepButton, &QPushButton::clicked, controller, &VMControllerCore::step);
        connect(runButton, &QPushButton::clicked, controller, &VMControllerCore::run);
        connect(pauseButton, &QPushButton::clicked, controller, &VMControllerCore::pause);
        connect(resetButton, &QPushButton::clicked, controller, &VMControllerCore::reset);
        connect(speedSlider, &QSlider::valueChanged, controller, &VMControllerCore::setExecutionSpeedLevel);
        controller->setExecutionSpeedLevel(speedSlider->value());

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

        const QString defaultBinary = defaultBinaryFilePath();
        if (!defaultBinary.isEmpty()) {
            loadBinaryFile(defaultBinary);
        }
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