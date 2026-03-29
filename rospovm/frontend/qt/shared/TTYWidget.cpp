#include "TTYWidget.h"

#include "TTY.h"

#include <QKeyEvent>
#include <QScrollBar>
#include <QTextCursor>

TTYWidget::TTYWidget(QWidget *parent)
    : QPlainTextEdit(parent)
{
    setWindowTitle("TTY");
    setPlaceholderText("TTY output appears here. Type to send input to VM.");
    setLineWrapMode(QPlainTextEdit::NoWrap);
    setUndoRedoEnabled(false);
    setMaximumBlockCount(2000);

    QFont mono("Courier");
    mono.setStyleHint(QFont::Monospace);
    mono.setPointSize(9);
    setFont(mono);

    setHighlighted(false);
    highlightTimer.setSingleShot(true);
    connect(&highlightTimer, &QTimer::timeout, this, [this]() {
        setHighlighted(false);
    });
}

void TTYWidget::appendOutputByte(uint8_t value)
{
    QTextCursor cursor = textCursor();
    cursor.movePosition(QTextCursor::End);
    setTextCursor(cursor);

    if (value == '\r')
    {
        return;
    }

    if (value == '\b')
    {
        QTextCursor eraseCursor = textCursor();
        eraseCursor.movePosition(QTextCursor::Left, QTextCursor::KeepAnchor, 1);
        eraseCursor.removeSelectedText();
    }
    else
    {
        insertPlainText(QString(QChar(static_cast<char>(value))));
    }

    QScrollBar *bar = verticalScrollBar();
    if (bar)
    {
        bar->setValue(bar->maximum());
    }
}

void TTYWidget::requestInputFocusHighlight()
{
    setFocus(Qt::OtherFocusReason);
    setHighlighted(true);
    highlightTimer.start(300);
}

void TTYWidget::keyPressEvent(QKeyEvent *event)
{
    if (event->isAutoRepeat())
    {
        event->accept();
        return;
    }

    const int key = event->key();
    const QString text = event->text();

    if (!text.isEmpty())
    {
        for (QChar ch : text)
        {
            uint8_t byte = ch.toLatin1();
            if (byte != 0)
            {
                TTYPush(byte);
            }
        }
        event->accept();
        return;
    }

    if (key == Qt::Key_Return || key == Qt::Key_Enter)
    {
        TTYPush('\n');
        event->accept();
        return;
    }

    if (key == Qt::Key_Backspace)
    {
        TTYPush('\b');
        event->accept();
        return;
    }

    if (key == Qt::Key_Tab)
    {
        TTYPush('\t');
        event->accept();
        return;
    }

    QPlainTextEdit::keyPressEvent(event);
}

void TTYWidget::setHighlighted(bool highlighted)
{
    if (highlighted)
    {
        setStyleSheet("QPlainTextEdit { border: 2px solid #f4b400; }");
    }
    else
    {
        setStyleSheet(QString());
    }
}
