# Makefile for RospOSVM project

CXX := g++
CXXFLAGS := -std=c++17
LDFLAGS := -lSDL2
SRC := main.cpp RospOSVM.cpp InstructionDecoder.cpp Register.cpp Memory.cpp TTY.cpp Binary.cpp
OBJ := $(SRC:.cpp=.o)
TARGET := main

all: $(TARGET)

$(TARGET): $(OBJ)
	$(CXX) $(CXXFLAGS) -o $@ $^ $(LDFLAGS)

%.o: %.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJ) $(TARGET)

.PHONY: all clean