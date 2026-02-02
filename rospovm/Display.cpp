#include <cstdint>
#include "Display.h"
#include "Memory.h"
#include <SDL2/SDL.h>
#include <stdexcept>

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
    // Address range: 0x20000000 - 0x20000FFF
    if (address < 0x20000000 || address > 0x20000FFF)
    {
        throw std::runtime_error("DisplayReadHandler: Address out of range");
    }
    uint32_t offset = address - 0x20000000;
    return framebuffer[offset];
}

void Display::write(uint32_t address, uint8_t value)
{
    // Address range: 0x20000000 - 0x20000FFF
    if (address < 0x20000000 || address > 0x20000FFF)
    {
        throw std::runtime_error("DisplayWriteHandler: Address out of range");
    }
    uint32_t offset = address - 0x20000000;
    framebuffer[offset] = value;

    // Update the SDL texture with the new framebuffer data
    uint32_t pixels[WIDTH * HEIGHT];
    for (int i = 0; i < WIDTH * HEIGHT; ++i)
    {
        int byteIndex = i / 4;
        int bitOffset = (3 - (i % 4)) * 2;
        uint8_t pixelValue = (framebuffer[byteIndex] >> bitOffset) & 0x03;

        // Map 2-bit grayscale to 32-bit ARGB
        uint8_t gray;
        switch (pixelValue)
        {
            case 0: gray = 0x00; break;       // Black
            case 1: gray = 0x55; break;       // Dark gray
            case 2: gray = 0xAA; break;       // Light gray
            case 3: gray = 0xFF; break;       // White
        }
        pixels[i] = (0xFF << 24) | (gray << 16) | (gray << 8) | gray; // ARGB
    }

    SDL_UpdateTexture(texture, NULL, pixels, WIDTH * sizeof(uint32_t));
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

    window = SDL_CreateWindow("RospOS 2-bit Grayscale Display", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, SCALED_WIDTH, SCALED_HEIGHT, SDL_WINDOW_SHOWN);
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


