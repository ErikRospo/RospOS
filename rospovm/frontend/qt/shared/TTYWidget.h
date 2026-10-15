#ifndef TTY_WIDGET_H
#define TTY_WIDGET_H

#include <QPlainTextEdit>
#include <QTimer>
#include <QByteArray>
#include <mutex>

#include <cstdint>

class TTYWidget : public QPlainTextEdit
{
    Q_OBJECT

public:
    explicit TTYWidget(QWidget *parent = nullptr);

public slots:
    void appendOutputByte(uint8_t value);
    void requestInputFocusHighlight();

protected:
    void keyPressEvent(QKeyEvent *event) override;

private:
    void setHighlighted(bool highlighted);
    void flushOutput();

    QTimer highlightTimer;
    QTimer outputTimer;
    std::mutex outputMutex;
    QByteArray pendingOutput;
    bool outputScheduled = false;
};

#endif // TTY_WIDGET_H
