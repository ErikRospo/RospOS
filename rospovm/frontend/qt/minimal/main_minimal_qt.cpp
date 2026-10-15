#include <QApplication>
#include <QString>
#include "MinimalWindow.cpp"

int main(int argc, char *argv[])
{
	QApplication app(argc, argv);
	MinimalWindow window;

	if (argc > 1) {
		const QString filePath = QString::fromUtf8(argv[argc - 1]);
		if (filePath.endsWith(".rosp", Qt::CaseInsensitive)) {
			window.loadBinaryFile(filePath);
		}
	}

	window.show();
	return app.exec();
}
