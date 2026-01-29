#ifndef REGISTER_H
#define REGISTER_H

#include <cstdint>
#include <stdexcept>

class Register {
private:
    uint32_t value;
public:
    Register() : value(0) {}
    uint32_t get() const { return value; }
    void set(uint32_t val) { value = val; }
};

class RegisterFile {
private:
    Register registers[16];
public:
    RegisterFile() {}
    Register& getRegister(int index) {
        if (index < 0 || index >= 16) {
            throw std::out_of_range("Register index out of range");
        }
        return registers[index];
    }
    Register& operator[](int index) {
        return getRegister(index);
    }
    const Register& operator[](int index) const {
        if (index < 0 || index >= 16) {
            throw std::out_of_range("Register index out of range");
        }
        return registers[index];
    }
    Register& fp() {
        return registers[13];
    }
    Register& lr() {
        return registers[14];
    }        
    Register& sp() {
        return registers[15];
    }
};

#endif // REGISTER_H