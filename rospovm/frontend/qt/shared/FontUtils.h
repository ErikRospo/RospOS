#pragma once

#include <QFont>
#include <QFontDatabase>
#include <QString>

inline QFont rospovmMonospaceFont()
{
#ifdef ROSPOSVM_WEB_BUILD
    const QString jetBrainsMonoFamily = QStringLiteral("JetBrains Mono");
    if (QFontDatabase::families().contains(jetBrainsMonoFamily)) {
        return QFont(jetBrainsMonoFamily);
    }
#endif

    QFont font = QFontDatabase::systemFont(QFontDatabase::FixedFont);
    font.setStyleHint(QFont::Monospace);
    return font;
}
