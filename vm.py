from typing import List


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
        self.regs.update(
            {
                "R0": ZRRegister("ZR"),
                "R14": Register("SP"),
                "R15": Register("PC"),
            }
        )

    def __getitem__(self, key):
        return self.regs[key].get()

    def __setitem__(self, key, value):
        self.regs[key].set(value)

    def __repr__(self):
        return ", ".join(str(reg) for reg in self.regs.values())


class Memory:
    def __init__(self):
        self.size = 0x0FFFFFFF
        self.mem = bytearray(self.size)

    def load(self, address, size):
        return int.from_bytes(self.mem[address : address + size], "little")

    def store(self, address, value, size):
        self.mem[address : address + size] = value.to_bytes(size, "little")


class Instruction:
    def __init__(self, name: str, opcode: int) -> None:
        self.name = name
        self.opcode = opcode


__instructions = [
    ("ADD  ", 0b0000_0000),
    ("ADDI ", 0b0000_0001),
    ("SUB  ", 0b0000_0010),
    ("NEG  ", 0b0000_0011),
    ("AND  ", 0b0000_0100),
    ("OR   ", 0b0000_0101),
    ("XOR  ", 0b0000_0110),
    ("ANDI ", 0b0000_0111),
    ("ORI  ", 0b0000_1000),
    ("XORI ", 0b0000_1001),
    ("NOT  ", 0b0000_1010),
    ("SHL  ", 0b0000_1011),
    ("SHR  ", 0b0000_1100),
    ("SAR  ", 0b0000_1101),
    ("MUL  ", 0b0000_1110),
    ("MULH ", 0b0000_1111),
    ("DIV  ", 0b0001_0000),
    ("DIVU ", 0b0001_0001),
    ("REM  ", 0b0001_0010),
    ("REMU ", 0b0001_0011),
    ("LB   ", 0b0001_0100),
    ("LBU  ", 0b0001_0101),
    ("LH   ", 0b0001_0110),
    ("LHU  ", 0b0001_0111),
    ("LW   ", 0b0001_1000),
    ("SB   ", 0b0001_1001),
    ("SH   ", 0b0001_1010),
    ("SW   ", 0b0001_1011),
    ("BEQ  ", 0b0001_1100),
    ("BNE  ", 0b0001_1101),
    ("BLT  ", 0b0001_1110),
    ("BGE  ", 0b0001_1111),
    ("BLTU ", 0b0010_0000),
    ("BGEU ", 0b0010_0001),
    ("JAL  ", 0b0010_0010),
    ("JAR  ", 0b0010_0011),
    ("ECALL", 0b0010_0100),
    ("SRET ", 0b0010_0101),
    ("BREAK", 0b0010_0110),
    ("NOP  ", 0b1111_1111),
]

instructions: List[Instruction] = [Instruction("NOP", i) for i in range(256)]
for name, opcode in __instructions:
    instructions[opcode] = Instruction(name.strip(), opcode)


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