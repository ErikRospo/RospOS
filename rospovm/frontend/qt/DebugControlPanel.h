#ifndef DEBUG_CONTROL_PANEL_H
#define DEBUG_CONTROL_PANEL_H

#include <QWidget>
#include <QPushButton>
#include <QLabel>
#include <QSlider>
#include <QSpinBox>
#include <QLineEdit>

class VMController;

class DebugControlPanel : public QWidget
{
    Q_OBJECT

public:
    explicit DebugControlPanel(QWidget *parent = nullptr);
    ~DebugControlPanel();

    void setVMController(VMController *controller);
    void setStepEnabled(bool enabled);
    void setStepBackEnabled(bool enabled);
    void setRunEnabled(bool enabled);
    void setPauseEnabled(bool enabled);
    void setResetEnabled(bool enabled);
    void setStatus(const QString &status);
    void setPCLabel(uint32_t pc);

signals:
    void speedChanged(int value);
    void addressChanged(uint32_t address);

private:
    void createUI();
    void setupConnections();
    void updateConverterFromHex(const QString &text);
    void updateConverterFromDec(const QString &text);
    void updateConverterFromBin(const QString &text);
    void updateConverterFromAscii(const QString &text);

    VMController *vmController;

    QLabel *statusLabel;
    QLabel *pcLabel;
    QSlider *speedSlider;
    QLabel *speedValueLabel;
    QSpinBox *addressSpinBox;
    QLabel *breakpointLabel;
    QLineEdit *hexInput;
    QLineEdit *decInput;
    QLineEdit *binInput;
    QLineEdit *asciiInput;
    bool converterUpdating = false;

    int currentSpeed = 2;
};

#endif // DEBUG_CONTROL_PANEL_H
