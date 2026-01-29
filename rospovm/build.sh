python ../base_writer.py
g++ -std=c++17 -o main main.cpp RospOSVM.cpp InstructionDecoder.cpp MemoryMapParser.cpp Register.cpp Memory.cpp TTY.cpp -I./ -I../rospovm/ -I../rospovm/include/