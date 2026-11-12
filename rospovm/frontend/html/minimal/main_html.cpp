

#include "MinimalWindow.cpp"
#include "Logger.h"
#include <QString>
#include <QSettings>
#include <QFont>



#ifndef ROSPOSVM_DEFAULT_BINARY_FILE
#define ROSPOSVM_DEFAULT_BINARY_FILE ""
#endif

#ifndef ROSPOSVM_DEFAULT_BLOCKDEV_FILE
#define ROSPOSVM_DEFAULT_BLOCKDEV_FILE ""
#endif


int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QFont monospaceFont(QStringLiteral("monospace"));
    monospaceFont.setStyleHint(QFont::Monospace);
    app.setFont(monospaceFont);
    MinimalWindow window;
    window.setBlockDeviceFile(QStringLiteral(ROSPOSVM_DEFAULT_BLOCKDEV_FILE));
    window.loadBinaryFile(QStringLiteral(ROSPOSVM_DEFAULT_BINARY_FILE));
    window.show();
    return app.exec();
}