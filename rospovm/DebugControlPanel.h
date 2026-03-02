#ifndef DEBUG_CONTROL_PANEL_H
#define DEBUG_CONTROL_PANEL_H

#include <QWidget>
#include <QPushButton>
#include <QLabel>
#include <QSlider>
#include <QSpinBox>

class VMController;

class DebugControlPanel : public QWidget
{
    Q_OBJECT

public:
    explicit DebugControlPanel(QWidget *parent = nullptr);
    ~DebugControlPanel();

    void setVMController(VMController *controller);
    void setStepEnabled(bool enabled);
    void setRunEnabled(bool enabled);
    void setPauseEnabled(bool enabled);
    void setResetEnabled(bool enabled);
    void setStatus(const QString &status);
    void setPCLabel(uint32_t pc);

signals:
    void stepClicked();
    void runClicked();
    void pauseClicked();
    void resetClicked();
    void speedChanged(int value);
    void addressChanged(uint32_t address);

private:
    void createUI();
    void setupConnections();

    VMController *vmController;

    QPushButton *stepButton;
    QPushButton *runButton;
    QPushButton *pauseButton;
    QPushButton *resetButton;
    QLabel *statusLabel;
    QLabel *pcLabel;
    QSlider *speedSlider;
    QSpinBox *addressSpinBox;
    QLabel *breakpointLabel;

    int currentSpeed = 50;
};

#endif // DEBUG_CONTROL_PANEL_H
