class Register:
    def __init__(self, name):
        self.name = name
        self.value = 0

    def __repr__(self):
        return f"{self.name}: {self.value}"

    def set(self, value):
        self.value = value % (2**32)

    def get(self):
        return self.value

class ZRRegister(Register):
    def set(self, value):
        # you shouldn't write to the zero register, but if you do, print it for debugging
        print(f"Attempt to write {value} to ZR register ignored.")

    def get(self):
        return 0

class Registers:
    def __init__(self):
        self.regs = {f"R{i}": Register(f"R{i}") for i in range(16)}
        self.regs.update({
            "R0": ZRRegister("ZR"),
            "R14": Register("SP"),
            "R15": Register("PC"),
        })
    def __getitem__(self, key):
        return self.regs[key].get()

    def __setitem__(self, key, value):
        self.regs[key].set(value)

    def __repr__(self):
        return ", ".join(str(reg) for reg in self.regs.values())

class Memory:
    def __init__(self):
        self.size= 0x0FFFFFFF 
        self.mem = bytearray(self.size)
    def load(self, address, size):
        return int.from_bytes(self.mem[address:address+size], 'little')
    def store(self, address, value, size):
        self.mem[address:address+size] = value.to_bytes(size, 'little')
        



class VM:
    def __init__(self):
        self.registers = Registers()
        self.memory = Memory()
        
    def __repr__(self):
        return f"Registers: {self.registers}\nMemory Size: {self.memory.size} bytes"
    
    def dump_state(self):
        with open("vm_state_dump.txt", "w") as f:
            f.write(repr(self))
        with open("vm_memory_dump.bin", "wb") as f:
            f.write(self.memory.mem)  
                
if __name__ == "__main__":
    vm = VM()
    vm.registers["R1"] = 42
    vm.memory.store(0, 12345678, 4)
    print(vm)
    vm.dump_state()