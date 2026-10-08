#ifndef BREAKPOINT_TEXT_EDIT_H
#define BREAKPOINT_TEXT_EDIT_H

#include <QWidget>
#include <QPlainTextEdit>
#include <QMap>
#include <QStringList>
#include <QEvent>
#include <cstdint>
#include "VMController.h"
#include "CodeView.h"

class CodeView;
class GutterWidget;

class BreakpointPlainTextEdit : public QPlainTextEdit
{
    Q_OBJECT
    friend GutterWidget;

public:
    BreakpointPlainTextEdit(QWidget *parent);
    ~BreakpointPlainTextEdit();

    void setVMController(VMController *controller){
      vmController=controller;  
    };
    void setCodeView(CodeView *codeView){
        this->codeView=codeView;
    };
    void refresh();
    int breakpointAreaWidth();
    void breakpointAreaPaintEvent(QPaintEvent *event);
    QTextBlock blockAtY(int y);
protected:
    void resizeEvent(QResizeEvent *event) override;
    
private slots:
    void updateBreakpointAreaWidth(int);
    void updateBreakpointArea(const QRect &, int);

private:
    QWidget *parent;
    VMController *vmController;
    CodeView *codeView;
    QWidget *breakpointArea;
    QSet<uint32_t> breakpointMap;
};

class GutterWidget : public QWidget
{

public:
    GutterWidget(BreakpointPlainTextEdit *editor) : QWidget(editor)
    {
        breakpointPTE = editor;
    }
    QSize sizeHint() const
    {
        return QSize(breakpointPTE->breakpointAreaWidth(), 0);
    }

protected:
    void paintEvent(QPaintEvent *event)
    {
        breakpointPTE->breakpointAreaPaintEvent(event);
    }
    void mouseDoubleClickEvent(QMouseEvent * event) override;

private:
    BreakpointPlainTextEdit *breakpointPTE;
};

#endif // BREAKPOINT_TEXT_EDIT_H