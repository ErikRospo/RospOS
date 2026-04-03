#ifndef REGISTER_H
#define REGISTER_H

#include <cstdint>
#include <stdexcept>

class Register
{
private:
    uint32_t value = 0;
    bool read_only = false;

public:
    Register() = default;
    
    uint32_t get() const { return value; }
    
    void set(uint32_t val) {
        if (!read_only) {
            value = val;
        }
    }
    
    void setReadOnly(bool ro) { read_only = ro; }
    bool isReadOnly() const { return read_only; }
};

class RegisterFile
{
private:
    static constexpr int kRegisterCount = 16;
    Register registers[16];
    
    // Validate register index bounds
    static void validateIndex(int index) {
        if (index < 0 || index >= kRegisterCount) {
            throw std::out_of_range("Register index out of range");
        }
    }

public:
    RegisterFile() {
        registers[0].setReadOnly(true);  // R0 is always zero
    }

    // Fast path for hot VM decode/execute loops where indices are ISA-decoded (0..15).
    Register& unchecked(int index) noexcept {
        return registers[index];
    }

    const Register& unchecked(int index) const noexcept {
        return registers[index];
    }
    
    Register& getRegister(int index) {
        validateIndex(index);
        return registers[index];
    }
    
    const Register& getRegister(int index) const {
        validateIndex(index);
        return registers[index];
    }
    
    Register& operator[](int index) {
        return getRegister(index);
    }
    
    const Register& operator[](int index) const {
        return getRegister(index);
    }
    
    Register& fp() { return registers[13]; }
    Register& lr() { return registers[14]; }
    Register& sp() { return registers[15]; }
};

#endif // REGISTER_H