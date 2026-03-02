#include <QApplication>
#include "MainWindow.h"
#include "Logger.h"

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);

    // Set up logger with default INFO level (less verbose than DEBUG)
    Logger::instance().setLogLevel(Logger::INFO);

    MainWindow window;
    window.show();

    return app.exec();
}
