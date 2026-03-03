#include "LogView.h"
#include "Logger.h"

#include <QVBoxLayout>
#include <QHBoxLayout>
#include <QPushButton>
#include <QFont>
#include <QListWidgetItem>

LogView::LogView(QWidget *parent)
    : QWidget(parent), logger(&Logger::instance())
{
    createUI();

    // Connect to logger signals
    connect(logger, &Logger::logAdded, this, &LogView::onLogAdded);
}

LogView::~LogView() = default;

void LogView::createUI()
{
    QVBoxLayout *layout = new QVBoxLayout(this);
    layout->setSpacing(0);
    layout->setContentsMargins(0, 0, 0, 0);

    // Title
    titleLabel = new QLabel("VM Execution Log");
    QFont titleFont = titleLabel->font();
    titleFont.setBold(true);
    titleFont.setPointSize(titleFont.pointSize() + 1);
    titleLabel->setFont(titleFont);
    layout->addWidget(titleLabel);

    // Log list
    logList = new QListWidget();
    logList->setEditTriggers(QAbstractItemView::NoEditTriggers);

    // Monospace font
    QFont monoFont("Courier");
    monoFont.setPointSize(8);
    logList->setFont(monoFont);
    logList->setSizePolicy(QSizePolicy::Expanding, QSizePolicy::Expanding);

    layout->addWidget(logList);

    // Clear button
    QHBoxLayout *buttonLayout = new QHBoxLayout();
    buttonLayout->addStretch();

    QPushButton *clearButton = new QPushButton("Clear Logs");
    connect(clearButton, &QPushButton::clicked, this, &LogView::onClearLogs);
    buttonLayout->addWidget(clearButton);

    layout->addLayout(buttonLayout);
    setLayout(layout);
}

void LogView::onLogAdded(const QString &message, int level)
{
    QListWidgetItem *item = new QListWidgetItem(message);

    // Color code based on level
    switch (level)
    {
    case Logger::DEBUG:
        item->setForeground(Qt::gray);
        break;
    case Logger::INFO:
        item->setForeground(Qt::black);
        break;
    case Logger::WARNING:
        item->setForeground(Qt::darkYellow);
        break;
    case Logger::ERROR:
        item->setForeground(Qt::red);
        break;
    case Logger::FATAL:
        item->setForeground(Qt::darkRed);
        item->setBackground(QColor(255, 200, 200));
        break;
    }

    logList->addItem(item);
    logList->scrollToBottom();
}

void LogView::onClearLogs()
{
    logList->clear();
    logger->clearLogs();
}

void LogView::refresh()
{
    logList->clear();
    for (const auto &log : logger->getLogs())
    {
        logList->addItem(log);
    }
    logList->scrollToBottom();
}
