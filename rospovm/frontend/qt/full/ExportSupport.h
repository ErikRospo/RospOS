#ifndef EXPORT_SUPPORT_H
#define EXPORT_SUPPORT_H

#include <QMessageBox>

#ifdef Q_OS_WASM
#include <QFile>
#include <QFileDialog>
#include <QTemporaryFile>
#endif

namespace ExportSupport {

inline void warning(QWidget *parent, const QString &title, const QString &message)
{
#ifdef Q_OS_WASM
    auto *dialog = new QMessageBox(QMessageBox::Warning, title, message,
                                   QMessageBox::Ok, parent);
    dialog->setAttribute(Qt::WA_DeleteOnClose);
    dialog->open();
#else
    QMessageBox::warning(parent, title, message);
#endif
}

#ifdef Q_OS_WASM
// Keep path-based exporters unchanged; only the browser delivery differs.
template<typename Writer>
bool download(const QString &fileName, Writer writeFile, QString *errorMessage)
{
    QTemporaryFile temporaryFile;
    if (!temporaryFile.open()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("Failed to create temporary export file: %1")
                                .arg(temporaryFile.errorString());
        }
        return false;
    }

    const QString temporaryPath = temporaryFile.fileName();
    temporaryFile.close();
    if (!writeFile(temporaryPath, errorMessage)) {
        return false;
    }

    QFile file(temporaryPath);
    if (!file.open(QIODevice::ReadOnly)) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("Failed to open exported file: %1")
                                .arg(file.errorString());
        }
        return false;
    }

    const QByteArray content = file.readAll();
    if (file.error() != QFileDevice::NoError || content.size() != file.size()) {
        if (errorMessage) {
            *errorMessage = QStringLiteral("Failed to read exported file: %1")
                                .arg(file.errorString());
        }
        return false;
    }

    // This starts a download; Qt does not report completion or cancellation.
    QFileDialog::saveFileContent(content, fileName);
    return true;
}
#endif

} // namespace ExportSupport

#endif // EXPORT_SUPPORT_H
