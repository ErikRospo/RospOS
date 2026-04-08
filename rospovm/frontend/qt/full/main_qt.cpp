#include <QApplication>
#include "MainWindow.h"
#include "Logger.h"
#include <QString>
#include <QSettings>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    // Set up logger with default INFO level (less verbose than DEBUG)
    Logger::instance().setLogLevel(Logger::INFO);

    QString binaryPath;
    bool clearWindowGeometry = false;
    for (int i = 1; i < argc; ++i) {
        const QString arg = QString::fromUtf8(argv[i]);
        if (arg == "--clear-window-geometry") {
            clearWindowGeometry = true;
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

    MainWindow window;

    // Load binary from CLI if one was provided.
    if (!binaryPath.isEmpty()) {
        window.loadBinaryFile(binaryPath);
    }

    window.show();

    return app.exec();
}
