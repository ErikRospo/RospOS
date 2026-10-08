#include "CodeView.h"
#include "BreakpointTextEdit.h"
#include "VMController.h"
#include <QPlainTextEdit>
#include <QtGui>

BreakpointPlainTextEdit::BreakpointPlainTextEdit(QWidget *parent) : parent(parent), vmController(nullptr)
{
    breakpointArea = new GutterWidget(this);
    connect(this, SIGNAL(blockCountChanged(int)), this, SLOT(updateBreakpointAreaWidth(int)));
    connect(this, SIGNAL(updateRequest(QRect, int)), this, SLOT(updateBreakpointArea(QRect, int)));
    // connect(this, SIGNAL(mouseDoubleClickEvent(QMouseEvent * event)), this, SLOT(doubleClickHandler(QMouseEvent * event)));
    updateBreakpointAreaWidth(0);
}

BreakpointPlainTextEdit::~BreakpointPlainTextEdit() = default;

int BreakpointPlainTextEdit::breakpointAreaWidth()
{

    int space = 3 + fontMetrics().averageCharWidth() * 2;

    return space;
}

QTextBlock BreakpointPlainTextEdit::blockAtY(int y)
{
    QTextBlock block = firstVisibleBlock();

    int top = qRound(
        blockBoundingGeometry(block)
            .translated(contentOffset())
            .top());

    while (block.isValid())
    {
        int height = qRound(blockBoundingRect(block).height());

        if (y >= top && y < top + height)
            return block;

        top += height;
        block = block.next();
    }

    return {};
}

void BreakpointPlainTextEdit::updateBreakpointArea(const QRect &rect, int dy)
{
    if (dy)
        breakpointArea->scroll(0, dy);
    else
        breakpointArea->update(0, rect.y(), breakpointArea->width(), rect.height());

    if (rect.contains(viewport()->rect()))
        updateBreakpointAreaWidth(0);
}
void BreakpointPlainTextEdit::updateBreakpointAreaWidth(int)
{
    setViewportMargins(breakpointAreaWidth(), 0, 0, 0);
}

void BreakpointPlainTextEdit::breakpointAreaPaintEvent(QPaintEvent *event)
{
    QPainter painter(breakpointArea);
    painter.fillRect(event->rect(), Qt::blue);

    QTextBlock block = firstVisibleBlock();
    // int blockNumber = block.blockNumber();
    int top = (int)blockBoundingGeometry(block).translated(contentOffset()).top();
    int bottom = top + (int)blockBoundingRect(block).height();

    while (block.isValid() && top <= event->rect().bottom())
    {
        if (block.isVisible() && bottom >= event->rect().top())
        {
            uint32_t address=codeView->lookupAddress(block.blockNumber());
            if (breakpointMap.contains(address)){
                
                painter.fillRect(0, top, breakpointAreaWidth(), (int)blockBoundingRect(block).height(),Qt::red);
            }
        }

        block = block.next();
        top = bottom;
        bottom = top + (int)blockBoundingRect(block).height();
        // ++blockNumber
    }
}

void BreakpointPlainTextEdit::resizeEvent(QResizeEvent *e)
{
    QPlainTextEdit::resizeEvent(e);

    QRect cr = contentsRect();
    breakpointArea->setGeometry(QRect(cr.left(), cr.top(), breakpointAreaWidth(), cr.height()));
}


void GutterWidget::mouseDoubleClickEvent(QMouseEvent *event)
{

    if (event->button() != Qt::LeftButton)
        return;

    QTextBlock block = breakpointPTE->blockAtY(event->position().y());
    if (!block.isValid())
        return;

    int line = block.blockNumber();
    uint32_t address = breakpointPTE->codeView->lookupAddress(line);

    if (breakpointPTE->breakpointMap.contains(address))
    {
        breakpointPTE->breakpointMap.remove(address);
        breakpointPTE->vmController->getRegisterView()->removePCBkpt(address);
        
    }
    else
    {
        breakpointPTE->breakpointMap.insert(address);
        breakpointPTE->vmController->getRegisterView()->addPCBkpt(address);
    }
    update();
    breakpointPTE->update();
}