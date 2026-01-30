#ifndef DISPLAY_H
#define DISPLAY_H

#include <cstdint>
#include <SDL2/SDL.h>

class Display
{
    // 128x128, 2-bit grayscale display
    // Memory-mapped at 0x20000000 - 0x20000FFF
    // Each pixel is represented by 2 bits (00=black, 01=dark gray, 10=light gray, 11=white)
private:
    SDL_Window *window;
    SDL_Renderer *renderer;
    SDL_Texture *texture;
    
    //FB size: 128*128 pixels * 2 bits/pixel = 32768 bits = 4096 bytes
    static const int WIDTH = 128;
    static const int HEIGHT = 128;
    static const int FB_SIZE = WIDTH * HEIGHT / 4; // 4 pixels per byte
    
    uint8_t framebuffer[FB_SIZE];
    

public:
    uint8_t displayReadHandler(uint32_t address);
    void displayWriteHandler(uint32_t address, uint8_t value);
    Display();
    ~Display();
};

#endif // DISPLAY_H