#ifndef LOGVIEW_H
#define LOGVIEW_H

#include <QWidget>
#include <QListWidget>
#include <QLabel>

class Logger;

class LogView : public QWidget
{
    Q_OBJECT

public:
    explicit LogView(QWidget *parent = nullptr);
    ~LogView();

    void refresh();

private slots:
    void onLogAdded(const QString &message, int level);
    void onClearLogs();

private:
    void createUI();

    Logger *logger;
    QListWidget *logList;
    QLabel *titleLabel;
};

#endif // LOGVIEW_H
