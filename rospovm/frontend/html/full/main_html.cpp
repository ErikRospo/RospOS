// #include "Display.h"
// #include "TTY.h"
// #include "TTYWidget.h"
// #include "VMControllerCore.h"

#include "MainWindow.h"
#include "Logger.h"
#include <QString>
#include <QSettings>


#include <QApplication>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFont>
#include <QHBoxLayout>
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


int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QFont monospaceFont(QStringLiteral("monospace"));
    monospaceFont.setStyleHint(QFont::Monospace);
    app.setFont(monospaceFont);
    MainWindow window;
    window.setBlockDeviceFile(QStringLiteral(ROSPOSVM_DEFAULT_BLOCKDEV_FILE));
    window.loadBinaryFile(QStringLiteral(ROSPOSVM_DEFAULT_BINARY_FILE));
    window.show();
    return app.exec();
}