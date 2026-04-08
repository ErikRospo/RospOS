#include "Logger.h"
#include <iostream>
#include <ctime>
#include <iomanip>
#include <sstream>

void Logger::log(LogLevel level, const QString &message)
{
    if (level < minLogLevel)
        return;

    // Get current time
    auto now = std::time(nullptr);
    auto tm = *std::localtime(&now);

    // Format timestamp
    std::ostringstream oss;
    oss << std::put_time(&tm, "%H:%M:%S");
    QString timestamp = QString::fromStdString(oss.str());

    // Format log level
    const char *levelStr[] = {"DEBUG", "INFO", "WARN", "ERROR", "FATAL"};
    QString levelName = levelStr[level];

    // Format full message
    QString fullMessage = QString("[%1] %2: %3").arg(timestamp, levelName, message);

    // Store in vector
    logs.push_back(fullMessage);

    // Emit signal
    emit logAdded(fullMessage, level);

    if (level >= ERROR)
    {
        std::cerr << fullMessage.toStdString() << std::endl;
    }
    else
    {
        std::cout << fullMessage.toStdString() << std::endl;
    }
}

void Logger::errorWithLocation(const QString &source_location, const QString &original_text,
                               const QString &message)
{
    QString fullMessage = QString("Error at %1:\n  %2\n  %3")
        .arg(source_location, original_text, message);
    error(fullMessage);
}
