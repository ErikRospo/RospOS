#include "Display.h"
#include "TTY.h"
#include "TTYWidget.h"
#include "VMControllerCore.h"
#include "ExecutionBackend.h"

#include <QApplication>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QLabel>
#include <QMetaObject>
#include <QPushButton>
#include <QSlider>
#include <QVBoxLayout>
#include <QWidget>

#include <iostream>
#include <string>

class MinimalWindow : public QWidget
{
public:
	explicit MinimalWindow(ExecutionBackend backend)
		: QWidget(nullptr),
		  controller(new VMControllerCore(this, backend)),
		  display(new VMDisplay(this)),
		  tty(new TTYWidget(this)),
		  status(new QLabel("Status: Ready", this))
	{
		setWindowTitle("RospOS VM Runner");
		setMinimumSize(900, 900);

		QPushButton *loadButton = new QPushButton("Load", this);
		QPushButton *stepButton = new QPushButton("Step", this);
		QPushButton *runButton = new QPushButton("Run", this);
		QPushButton *pauseButton = new QPushButton("Pause", this);
		QPushButton *resetButton = new QPushButton("Reset", this);

		QSlider *speedSlider = new QSlider(Qt::Horizontal, this);
		speedSlider->setMinimum(0);
		speedSlider->setMaximum(10);
		speedSlider->setValue(4);

		QHBoxLayout *controls = new QHBoxLayout();
		controls->addWidget(loadButton);
		controls->addWidget(stepButton);
		controls->addWidget(runButton);
		controls->addWidget(pauseButton);
		controls->addWidget(resetButton);
		controls->addWidget(new QLabel("Speed", this));
		controls->addWidget(speedSlider, 1);

		QVBoxLayout *layout = new QVBoxLayout(this);
		layout->addLayout(controls);
		layout->addWidget(status);
		layout->addWidget(display, 1, Qt::AlignCenter);
		layout->addWidget(tty, 1);
		setLayout(layout);

		connect(loadButton, &QPushButton::clicked, this, [this]() {
			const QString fileName = QFileDialog::getOpenFileName(
				this,
				"Open RospOS Binary",
				"",
				"Binary Files (*.rosp);;All Files (*)");
			if (fileName.isEmpty()) {
				return;
			}
			loadBinaryFile(fileName);
		});
		connect(stepButton, &QPushButton::clicked, controller, &VMControllerCore::step);
		connect(runButton, &QPushButton::clicked, controller, &VMControllerCore::run);
		connect(pauseButton, &QPushButton::clicked, controller, &VMControllerCore::pause);
		connect(resetButton, &QPushButton::clicked, controller, &VMControllerCore::reset);
		connect(speedSlider, &QSlider::valueChanged, controller, &VMControllerCore::setExecutionSpeedLevel);

		connect(controller, &VMControllerCore::stateChanged, this, [this]() {
			status->setText(QString("Status: PC=0x%1")
								.arg(controller->getProgramCounter(), 8, 16, QChar('0')));
			display->update();
		});
		connect(controller, &VMControllerCore::executionStarted, this, [this]() {
			status->setText("Status: Running");
		});
		connect(controller, &VMControllerCore::executionStopped, this, [this]() {
			status->setText("Status: Stopped");
		});
		connect(controller, &VMControllerCore::error, this, [this](const QString &message) {
			status->setText(QString("Status: %1").arg(message));
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

	~MinimalWindow() override
	{
		TTYSetWriteCallback(nullptr);
		TTYSetReadRequestCallback(nullptr);
	}

	void loadBinaryFile(const QString &filePath)
	{
		if (controller->loadBinaryFile(filePath)) {
			status->setText(QString("Status: Loaded %1").arg(filePath));
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
	ExecutionBackend backend = ExecutionBackend::Interpreter;
	QString binaryPath;

	for (int i = 1; i < argc; ++i) {
		const QString arg = QString::fromUtf8(argv[i]);
		if (arg == "--jit") {
			backend = ExecutionBackend::Jit;
			continue;
		}
		if (arg == "--interpreter") {
			backend = ExecutionBackend::Interpreter;
			continue;
		}
		if (arg == "--backend") {
			if (i + 1 >= argc) {
				std::cerr << "Missing value for --backend (expected interpreter|jit)\n";
				return 2;
			}

			const std::string value = QString::fromUtf8(argv[++i]).toLower().toStdString();
			if (!parseExecutionBackend(value, backend)) {
				std::cerr << "Invalid backend: " << value << " (expected interpreter|jit)\n";
				return 2;
			}
			continue;
		}

		if (arg.endsWith(".rosp", Qt::CaseInsensitive)) {
			binaryPath = arg;
		}
	}

	MinimalWindow window(backend);

	if (!binaryPath.isEmpty()) {
		window.loadBinaryFile(binaryPath);
	}

	window.show();
	return app.exec();
}
