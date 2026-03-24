#include "Display.h"
#include "Memory.h"
#include <array>
#include <stdexcept>
#include <iostream>
#include <algorithm>
#include <QPainter>

namespace {
constexpr uint32_t kDisplayBase = 0x20000000;
constexpr uint32_t kDisplaySize = 256U * 256U;

std::array<uint8_t, kDisplaySize> g_framebuffer{};
std::mutex g_fbMutex;
}

// Add a static instance for the VMDisplay class
static VMDisplay *displayInstance = nullptr;

// Static MMIO handlers
uint8_t VMDisplay::displayReadHandler(uint32_t address)
{
    return read(address);
}

void VMDisplay::displayWriteHandler(uint32_t address, uint8_t value)
{
    write(address, value);
}

// Non-static methods for internal logic
uint8_t VMDisplay::read(uint32_t address)
{
    // Address range: 0x20000000 - 0x2000FFFF (FB_SIZE bytes)
    if (address < kDisplayBase)
    {
        throw std::runtime_error("DisplayReadHandler: Address out of range");
    }
    uint32_t offset = address - kDisplayBase;
    if (offset >= kDisplaySize)
    {
        throw std::runtime_error("DisplayReadHandler: Address out of range");
    }

    std::lock_guard<std::mutex> lock(g_fbMutex);
    return g_framebuffer[offset];
}

void VMDisplay::write(uint32_t address, uint8_t value)
{
    // Address range: 0x20000000 - 0x2000FFFF (FB_SIZE bytes)
    if (address < kDisplayBase)
    {
        throw std::runtime_error("DisplayWriteHandler: Address out of range");
    }
    uint32_t offset = address - kDisplayBase;
    if (offset >= kDisplaySize)
    {
        throw std::runtime_error("DisplayWriteHandler: Address out of range");
    }

    VMDisplay *instanceCopy = nullptr;
    {
        std::lock_guard<std::mutex> lock(g_fbMutex);
        if (g_framebuffer[offset] == value) {
            return;
        }
        g_framebuffer[offset] = value;
        instanceCopy = displayInstance;
    }

    // Convert 8-bit color to RGB
    // Format: 00RRGGBB where each component is 2 bits
    uint8_t v = value;
    uint8_t r2 = (v >> 4) & 0x03;
    uint8_t g2 = (v >> 2) & 0x03;
    uint8_t b2 = v & 0x03;
    uint8_t r = r2 * 85;
    uint8_t g = g2 * 85;
    uint8_t b = b2 * 85;

    if (instanceCopy != nullptr) {
        // Update the QImage when the UI widget is active.
        const int x = static_cast<int>(offset % WIDTH);
        const int y = static_cast<int>(offset / WIDTH);
        instanceCopy->displayImage.setPixelColor(x, y, QColor(r, g, b));

        // Schedule a paint update on the Qt event loop.
        instanceCopy->update();
    }
}

VMDisplay::VMDisplay(QWidget *parent)
    : QWidget(parent), displayImage(WIDTH, HEIGHT, QImage::Format_RGB32)
{
    if (displayInstance)
    {
        throw std::runtime_error("Display instance already exists");
    }
    displayInstance = this;

    displayImage.fill(Qt::black);

    // Mirror the backend framebuffer into the Qt image.
    {
        std::lock_guard<std::mutex> lock(g_fbMutex);
        for (uint32_t offset = 0; offset < kDisplaySize; ++offset) {
            const uint8_t v = g_framebuffer[offset];
            const uint8_t r = static_cast<uint8_t>(((v >> 4) & 0x03) * 85);
            const uint8_t g = static_cast<uint8_t>(((v >> 2) & 0x03) * 85);
            const uint8_t b = static_cast<uint8_t>((v & 0x03) * 85);
            const int x = static_cast<int>(offset % WIDTH);
            const int y = static_cast<int>(offset / WIDTH);
            displayImage.setPixelColor(x, y, QColor(r, g, b));
        }
    }

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
    Q_UNUSED(event);
    QPainter painter(this);
    painter.setRenderHint(QPainter::SmoothPixmapTransform, false);

    // Scale and draw the image
    QRect targetRect(0, 0, SCALED_WIDTH, SCALED_HEIGHT);
    painter.drawImage(targetRect, displayImage);
}
