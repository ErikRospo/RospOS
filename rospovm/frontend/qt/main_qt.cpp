#include <QApplication>
#include "MainWindow.h"
#include "Logger.h"
#include <QString>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    // Set up logger with default INFO level (less verbose than DEBUG)
    Logger::instance().setLogLevel(Logger::INFO);

    MainWindow window;
    
    // Check if a .rosp file was provided as a command-line argument
    if (argc > 1) {
        QString filePath = QString::fromUtf8(argv[argc - 1]);
        if (filePath.endsWith(".rosp", Qt::CaseInsensitive)) {
            window.loadBinaryFile(filePath);
        }
    }
    
    window.show();

    return app.exec();
}
