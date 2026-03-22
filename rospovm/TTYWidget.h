#ifndef TTY_WIDGET_H
#define TTY_WIDGET_H

#include <QPlainTextEdit>
#include <QTimer>

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

    QTimer highlightTimer;
};

#endif // TTY_WIDGET_H
