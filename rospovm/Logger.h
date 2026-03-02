#ifndef LOGGER_H
#define LOGGER_H

#include <QString>
#include <QObject>
#include <sstream>
#include <vector>

class Logger : public QObject
{
    Q_OBJECT

public:
    enum LogLevel
    {
        DEBUG = 0,
        INFO = 1,
        WARNING = 2,
        ERROR = 3,
        FATAL = 4
    };

    static Logger &instance()
    {
        static Logger inst;
        return inst;
    }

    void log(LogLevel level, const QString &message);
    void debug(const QString &message) { log(DEBUG, message); }
    void info(const QString &message) { log(INFO, message); }
    void warning(const QString &message) { log(WARNING, message); }
    void error(const QString &message) { log(ERROR, message); }
    void fatal(const QString &message) { log(FATAL, message); }

    void setLogLevel(LogLevel level) { minLogLevel = level; }
    const std::vector<QString> &getLogs() const { return logs; }
    void clearLogs() { logs.clear(); }

signals:
    void logAdded(const QString &message, int level);

private:
    Logger() : minLogLevel(DEBUG) {}

    std::vector<QString> logs;
    LogLevel minLogLevel;
};

#endif // LOGGER_H
