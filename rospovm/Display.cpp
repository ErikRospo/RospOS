#include <cstdint>
#include "Display.h"
#include "Memory.h"
#include <SDL2/SDL.h>
#include <stdexcept>
#include <iostream>
#include <algorithm>
#include <vector>
// Add a static instance for the Display class
static Display* displayInstance = nullptr;

// Static MMIO handlers
uint8_t Display::displayReadHandler(uint32_t address)
{
    if (!displayInstance)
    {
        throw std::runtime_error("Display instance not initialized");
    }
    return displayInstance->read(address);
}

void Display::displayWriteHandler(uint32_t address, uint8_t value)
{
    if (!displayInstance)
    {
        throw std::runtime_error("Display instance not initialized");
    }
    displayInstance->write(address, value);
}

// Non-static methods for internal logic
uint8_t Display::read(uint32_t address)
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

void Display::write(uint32_t address, uint8_t value)
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
    framebuffer[offset] = value;

    // Update the SDL texture with the new framebuffer data
    std::vector<uint32_t> pixels(WIDTH * HEIGHT);
    for (int i = 0; i < WIDTH * HEIGHT; ++i)
    {
        uint8_t v = framebuffer[i];
        uint8_t r2 = (v >> 4) & 0x03;
        uint8_t g2 = (v >> 2) & 0x03;
        uint8_t b2 = v & 0x03;
        uint8_t r = r2 * 85; // expand 2-bit to 0-255
        uint8_t g = g2 * 85;
        uint8_t b = b2 * 85;
        pixels[i] = (0xFFu << 24) | (static_cast<uint32_t>(r) << 16) | (static_cast<uint32_t>(g) << 8) | static_cast<uint32_t>(b);
    }

    SDL_UpdateTexture(texture, NULL, pixels.data(), WIDTH * sizeof(uint32_t));
    SDL_RenderClear(renderer);

    SDL_Rect destRect = {0, 0, SCALED_WIDTH, SCALED_HEIGHT};
    SDL_RenderCopy(renderer, texture, NULL, &destRect);

    SDL_RenderPresent(renderer);
}

// Update constructor to initialize the static instance
Display::Display()
{
    if (displayInstance)
    {
        throw std::runtime_error("Display instance already exists");
    }
    displayInstance = this;

    if (SDL_Init(SDL_INIT_VIDEO) < 0)
    {
        throw std::runtime_error("SDL could not initialize!");
    }

    window = SDL_CreateWindow("RospOS 256x256 8-bit Display", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, SCALED_WIDTH, SCALED_HEIGHT, SDL_WINDOW_SHOWN);
    if (!window)
    {
        throw std::runtime_error("Window could not be created!");
    }

    renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
    if (!renderer)
    {
        throw std::runtime_error("Renderer could not be created!");
    }

    texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, WIDTH, HEIGHT);
    if (!texture)
    {
        throw std::runtime_error("Texture could not be created!");
    }

    // Initialize framebuffer to black
    std::fill(std::begin(framebuffer), std::end(framebuffer), 0x00);
}

// Update destructor to reset the static instance
Display::~Display()
{
    displayInstance = nullptr;
    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
}


