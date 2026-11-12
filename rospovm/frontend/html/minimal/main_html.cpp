

#include "MinimalWindow.cpp"
#include "Logger.h"
#include <QDebug>
#include <QString>
#include <QSettings>
#include <QFont>
#include <QFontDatabase>



#ifndef ROSPOSVM_DEFAULT_BINARY_FILE
#define ROSPOSVM_DEFAULT_BINARY_FILE ""
#endif

#ifndef ROSPOSVM_DEFAULT_BLOCKDEV_FILE
#define ROSPOSVM_DEFAULT_BLOCKDEV_FILE ""
#endif


int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    if (QFontDatabase::addApplicationFont(QStringLiteral("/fonts/JetBrainsMono-Regular.ttf")) < 0) {
        qWarning("Failed to load embedded JetBrains Mono font");
    }
    QFont applicationFont = QFontDatabase::systemFont(QFontDatabase::GeneralFont);
    applicationFont.setStyleHint(QFont::SansSerif);
    app.setFont(applicationFont);
    MinimalWindow window;
    window.setBlockDeviceFile(QStringLiteral(ROSPOSVM_DEFAULT_BLOCKDEV_FILE));
    window.loadBinaryFile(QStringLiteral(ROSPOSVM_DEFAULT_BINARY_FILE));
    window.show();
    return app.exec();
}