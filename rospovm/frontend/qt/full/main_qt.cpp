#include <QApplication>
#include "MainWindow.h"
#include "Logger.h"
#include "ExecutionBackend.h"
#include <QString>
#include <QSettings>
#include <iostream>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    // Set up logger with default INFO level (less verbose than DEBUG)
    Logger::instance().setLogLevel(Logger::INFO);

    QString binaryPath;
    bool clearWindowGeometry = false;
    ExecutionBackend backend = ExecutionBackend::Interpreter;
    for (int i = 1; i < argc; ++i) {
        const QString arg = QString::fromUtf8(argv[i]);
        if (arg == "--clear-window-geometry") {
            clearWindowGeometry = true;
            continue;
        }
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

    if (clearWindowGeometry) {
        QSettings settings("RospOS", "RospOSVMFullQt");
        settings.remove("window/geometry");
        settings.remove("window/state");
        settings.remove("window/splitterHorizontal");
        settings.remove("window/splitterVertical");
        settings.remove("window/splitterRightSidebar");
    }

    MainWindow window(nullptr, backend);

    // Load binary from CLI if one was provided.
    if (!binaryPath.isEmpty()) {
        window.loadBinaryFile(binaryPath);
    }

    window.show();

    return app.exec();
}
