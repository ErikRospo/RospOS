#include "TTYWidget.h"

#include "TTY.h"

#include <QKeyEvent>
#include <QScrollBar>
#include <QTextCursor>
#include <QMetaObject>

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
    outputTimer.setSingleShot(true);
    outputTimer.setInterval(16);
    connect(&outputTimer, &QTimer::timeout, this, &TTYWidget::flushOutput);
}

void TTYWidget::appendOutputByte(uint8_t value)
{
    {
        std::lock_guard<std::mutex> lock(outputMutex);
        pendingOutput.append(static_cast<char>(value));
        if (outputScheduled) return;
        outputScheduled = true;
    }
    // One queued callback and one document update per batch, even when the VM
    // produces thousands of bytes before returning to the event loop.
    QMetaObject::invokeMethod(this, [this]() { outputTimer.start(); }, Qt::QueuedConnection);
}

void TTYWidget::flushOutput()
{
    QByteArray output;
    {
        std::lock_guard<std::mutex> lock(outputMutex);
        output.swap(pendingOutput);
        outputScheduled = false;
    }
    QTextCursor cursor = textCursor();
    cursor.movePosition(QTextCursor::End);
    cursor.beginEditBlock();
    QString text;
    for (char value : output) {
        if (value == '\r') continue;
        if (value == '\b') {
            cursor.insertText(text);
            text.clear();
            cursor.deletePreviousChar();
        } else {
            text.append(QChar::fromLatin1(value));
        }
    }
    cursor.insertText(text);
    cursor.endEditBlock();
    setTextCursor(cursor);

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
