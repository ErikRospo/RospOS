#include "Display.h"
#include "Memory.h"
#include <stdexcept>
#include <iostream>
#include <algorithm>
#include <QPainter>
#include <QKeyEvent>
#include "TTY.h"
#include "Shutdown.h"

// Add a static instance for the VMDisplay class
static VMDisplay *displayInstance = nullptr;

// Static MMIO handlers
uint8_t VMDisplay::displayReadHandler(uint32_t address)
{
    if (!displayInstance)
    {
        throw std::runtime_error("Display instance not initialized");
    }
    return displayInstance->read(address);
}

void VMDisplay::displayWriteHandler(uint32_t address, uint8_t value)
{
    if (!displayInstance)
    {
        throw std::runtime_error("Display instance not initialized");
    }
    displayInstance->write(address, value);
}

// Non-static methods for internal logic
uint8_t VMDisplay::read(uint32_t address)
{
    // Address range: 0x20000000 - 0x2000FFFF (FB_SIZE bytes)
    if (address < 0x20000000)
    {
        throw std::runtime_error("DisplayReadHandler: Address out of range");
    }
    uint32_t offset = address - 0x20000000;
    if (offset >= FB_SIZE)
    {
        throw std::runtime_error("DisplayReadHandler: Address out of range");
    }
    return framebuffer[offset];
}

void VMDisplay::write(uint32_t address, uint8_t value)
{
    // Address range: 0x20000000 - 0x2000FFFF (FB_SIZE bytes)
    if (address < 0x20000000)
    {
        throw std::runtime_error("DisplayWriteHandler: Address out of range");
    }
    uint32_t offset = address - 0x20000000;
    if (offset >= FB_SIZE)
    {
        throw std::runtime_error("DisplayWriteHandler: Address out of range");
    }
    if (framebuffer[offset] == value)
        return; // No change, skip update

    framebuffer[offset] = value;

    // Convert 8-bit color to RGB
    // Format: 00RRGGBB where each component is 2 bits
    uint8_t v = value;
    uint8_t r2 = (v >> 4) & 0x03;
    uint8_t g2 = (v >> 2) & 0x03;
    uint8_t b2 = v & 0x03;
    uint8_t r = r2 * 85;
    uint8_t g = g2 * 85;
    uint8_t b = b2 * 85;

    {
        std::lock_guard<std::mutex> lock(fbMutex);
        // Update the QImage
        int x = offset % WIDTH;
        int y = offset / WIDTH;
        displayImage.setPixelColor(x, y, QColor(r, g, b));
        dirty.store(true);
    }

    // Schedule a paint update on the Qt event loop
    update();
}

VMDisplay::VMDisplay(QWidget *parent)
    : QWidget(parent), displayImage(WIDTH, HEIGHT, QImage::Format_RGB32)
{
    if (displayInstance)
    {
        throw std::runtime_error("Display instance already exists");
    }
    displayInstance = this;

    // Initialize framebuffer to black
    std::fill(std::begin(framebuffer), std::end(framebuffer), 0x00);
    displayImage.fill(Qt::black);
    dirty.store(false);

    // Set widget properties
    setWindowTitle("RospOS Display");
    setMinimumSize(SCALED_WIDTH, SCALED_HEIGHT);
    resize(SCALED_WIDTH, SCALED_HEIGHT);
    setSizePolicy(QSizePolicy::Fixed, QSizePolicy::Fixed);
    setFocusPolicy(Qt::StrongFocus);
}

VMDisplay::~VMDisplay()
{
    displayInstance = nullptr;
}

void VMDisplay::paintEvent(QPaintEvent *event)
{
    std::lock_guard<std::mutex> lock(fbMutex);

    QPainter painter(this);
    painter.setRenderHint(QPainter::SmoothPixmapTransform, false);

    // Scale and draw the image
    QRect targetRect(0, 0, SCALED_WIDTH, SCALED_HEIGHT);
    painter.drawImage(targetRect, displayImage);

    dirty.store(false);
}

void VMDisplay::keyPressEvent(QKeyEvent *event)
{
    if (event->isAutoRepeat())
    {
        event->ignore();
        return;
    }

    int key = event->key();
    QString text = event->text();

    // Handle Ctrl+C
    if (event->modifiers() & Qt::ControlModifier && key == Qt::Key_C)
    {
        requestShutdown();
        event->accept();
        return;
    }

    // Handle printable characters
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
    }
    // Handle special keys
    else if (key == Qt::Key_Return || key == Qt::Key_Enter)
    {
        TTYPush('\n');
    }
    else if (key == Qt::Key_Backspace)
    {
        TTYPush('\b');
    }
    else if (key == Qt::Key_Tab)
    {
        TTYPush('\t');
    }

    event->accept();
}
