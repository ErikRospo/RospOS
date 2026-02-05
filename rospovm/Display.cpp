#include <cstdint>
#include "Display.h"
#include "Memory.h"
#include <SDL2/SDL.h>
#include <stdexcept>
#include <iostream>
#include <algorithm>
#include <vector>
#include <thread>
#include <atomic>
#include <chrono>
#include "TTY.h"
#include "Shutdown.h"
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
    if (framebuffer[offset] == value) return; // No change, skip update
    framebuffer[offset] = value;

    // Update pixel buffer under lock and mark dirty; rendering happens in the display thread
    uint8_t v = value;
    uint8_t r2 = (v >> 4) & 0x03;
    uint8_t g2 = (v >> 2) & 0x03;
    uint8_t b2 = v & 0x03;
    uint8_t r = r2 * 85;
    uint8_t g = g2 * 85;
    uint8_t b = b2 * 85;
    uint32_t pixel = (0xFFu << 24) | (static_cast<uint32_t>(r) << 16) | (static_cast<uint32_t>(g) << 8) | static_cast<uint32_t>(b);

    {
        std::lock_guard<std::mutex> lock(fbMutex);
        pixels[offset] = pixel;
        framebuffer[offset] = value;
        dirty.store(true);
    }
}

// Update constructor to initialize the static instance
Display::Display()
{
    if (displayInstance)
    {
        throw std::runtime_error("Display instance already exists");
    }
    displayInstance = this;

    // Initialize framebuffer and pixel buffer to black
    std::fill(std::begin(framebuffer), std::end(framebuffer), 0x00);
    pixels.assign(WIDTH * HEIGHT, 0xFF000000); // ARGB black
    dirty.store(false);

    // Start display thread which will initialize SDL, create window/renderer/texture,
    // poll events and render at ~60Hz. All SDL calls happen on this thread.
    displayThreadRunning.store(true);
    displayThread = std::thread([this]() {
        using clk = std::chrono::steady_clock;
        const std::chrono::microseconds period(16667); // ~60Hz

        if (SDL_Init(SDL_INIT_VIDEO) < 0)
        {
            std::cerr << "SDL could not initialize: " << SDL_GetError() << std::endl;
            displayThreadRunning.store(false);
            return;
        }

        window = SDL_CreateWindow("RospOS 256x256 8-bit Display", SDL_WINDOWPOS_UNDEFINED, SDL_WINDOWPOS_UNDEFINED, SCALED_WIDTH, SCALED_HEIGHT, SDL_WINDOW_SHOWN);
        if (!window)
        {
            std::cerr << "Window could not be created: " << SDL_GetError() << std::endl;
            SDL_Quit();
            displayThreadRunning.store(false);
            return;
        }

        renderer = SDL_CreateRenderer(window, -1, SDL_RENDERER_ACCELERATED);
        if (!renderer)
        {
            std::cerr << "Renderer could not be created: " << SDL_GetError() << std::endl;
            SDL_DestroyWindow(window);
            SDL_Quit();
            displayThreadRunning.store(false);
            return;
        }

        texture = SDL_CreateTexture(renderer, SDL_PIXELFORMAT_ARGB8888, SDL_TEXTUREACCESS_STREAMING, WIDTH, HEIGHT);
        if (!texture)
        {
            std::cerr << "Texture could not be created: " << SDL_GetError() << std::endl;
            SDL_DestroyRenderer(renderer);
            SDL_DestroyWindow(window);
            SDL_Quit();
            displayThreadRunning.store(false);
            return;
        }

        // Upload initial texture
        SDL_UpdateTexture(texture, NULL, pixels.data(), WIDTH * sizeof(uint32_t));

        while (displayThreadRunning.load())
        {
            auto start = clk::now();
            // Poll SDL events on this thread
            SDL_Event e;
            while (SDL_PollEvent(&e))
            {
                if (e.type == SDL_QUIT)
                {
                    requestShutdown();
                }
                else if (e.type == SDL_WINDOWEVENT)
                {
                    if (e.window.event == SDL_WINDOWEVENT_CLOSE)
                    {
                        requestShutdown();
                    }
                }
                else if (e.type == SDL_KEYDOWN)
                {
                    SDL_Keycode k = e.key.keysym.sym;
                    SDL_Keymod mods = SDL_GetModState();
                    if ((mods & KMOD_CTRL) && (k == SDLK_c))
                    {
                        requestShutdown();
                    }
                    uint8_t ch = 0;
                    if (k >= 32 && k <= 126)
                    {
                        ch = static_cast<uint8_t>(k);
                    }
                    else if (k == SDLK_RETURN)
                    {
                        ch = '\n';
                    }
                    else if (k == SDLK_BACKSPACE)
                    {
                        ch = '\b';
                    }

                    if (ch)
                    {
                        TTYPush(ch);
                    }
                }
            }

            bool needRender = false;
            {
                std::lock_guard<std::mutex> lock(fbMutex);
                if (dirty.load())
                {
                    // Push full texture update
                    SDL_UpdateTexture(texture, NULL, pixels.data(), WIDTH * sizeof(uint32_t));
                    dirty.store(false);
                    needRender = true;
                }
            }
            if (needRender)
            {
                SDL_RenderClear(renderer);
                SDL_Rect destRect = {0, 0, SCALED_WIDTH, SCALED_HEIGHT};
                SDL_RenderCopy(renderer, texture, NULL, &destRect);
                SDL_RenderPresent(renderer);
            }

            auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(clk::now() - start);
            if (elapsed < period)
            {
                std::this_thread::sleep_for(period - elapsed);
            }
        }

        // Cleanup SDL objects on this thread
        if (texture) SDL_DestroyTexture(texture);
        if (renderer) SDL_DestroyRenderer(renderer);
        if (window) SDL_DestroyWindow(window);
        SDL_Quit();
    });

    
}

// Update destructor to reset the static instance
Display::~Display()
{
    displayInstance = nullptr;
    // Stop display thread and let it clean up SDL objects
    displayThreadRunning.store(false);
    if (displayThread.joinable())
    {
        displayThread.join();
    }
}
