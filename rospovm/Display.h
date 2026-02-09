#ifndef DISPLAY_H
#define DISPLAY_H

#include <cstdint>
#include <SDL2/SDL.h>
#include <vector>
#include <thread>
#include <mutex>
#include <atomic>

class Display
{
    // 256x256, 8-bit color framebuffer
    // Memory-mapped at 0x20000000 - 0x2000FFFF
    // Pixel format: 8-bit value in 00RRGGBB where each component is 2 bits.
    // Components expand to 0..255 by multiplying by 85 (0->0,1->85,2->170,3->255).
private:
    SDL_Window *window;
    SDL_Renderer *renderer;
    SDL_Texture *texture;

    // FB size: 256*256 pixels * 8 bits/pixel = 65536 bytes
    static const int WIDTH = 256;
    static const int HEIGHT = 256;
    static const int FB_SIZE = WIDTH * HEIGHT; // 1 byte per pixel
    static const int SCALE = 4;                // Scaling factor for rendering;
    static const int SCALED_WIDTH = WIDTH * SCALE;
    static const int SCALED_HEIGHT = HEIGHT * SCALE;

    uint8_t framebuffer[FB_SIZE];
    // Pixel buffer used for SDL texture updates (ARGB8888)
    std::vector<uint32_t> pixels;

    // Synchronization for framebuffer/pixels access
    std::mutex fbMutex;
    std::atomic<bool> dirty;

    // Display rendering thread (updates the SDL texture at 60Hz)
    std::thread displayThread;
    std::atomic<bool> displayThreadRunning;

    // Internal methods for MMIO logic
    uint8_t read(uint32_t address);
    void write(uint32_t address, uint8_t value);

public:
    // Static MMIO handlers
    static uint8_t displayReadHandler(uint32_t address);
    static void displayWriteHandler(uint32_t address, uint8_t value);

    Display();
    ~Display();
};

#endif // DISPLAY_H