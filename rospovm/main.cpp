#include <iostream>
#include <fstream>
#include <vector>
#include <cstdint>
#include <stdexcept>
#include <iomanip>
#include <map>
#include <sstream>

enum class Opcode : uint8_t {
    R_TYPE = 0x0,
    I_TYPE_ARITH = 0x1,
    I_TYPE_LS = 0x2,
    B_TYPE = 0x3,
    J_TYPE = 0x4,
    S_TYPE = 0x5,
    NOP = 0xF
};

std::string decodeInstruction(uint32_t instruction) {
    uint32_t opcode = (instruction >> 28) & 0x0F;
    std::string oss;
    switch (opcode) {
        case 0x0: { // R-type
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs1 = (instruction >> 16) & 0x0F;
            uint32_t rs2 = (instruction >> 12) & 0x0F;
            oss += "R-TYPE ";
            switch (sub_op) {
                case 0x0: oss += "ADD"; break;
                case 0x1: oss += "SUB"; break;
                case 0x2: oss += "AND"; break;
                case 0x3: oss += "OR"; break;
                case 0x4: oss += "XOR"; break;
                case 0x5: oss += "MUL"; break;
                case 0x6: oss += "MULH"; break;
                case 0x7: oss += "NEG"; break;
                case 0x8: oss += "NOT"; break;
                case 0x9: oss += "SHL"; break;
                case 0xA: oss += "SHR"; break;
                case 0xB: oss += "SAR"; break;
                case 0xC: oss += "DIV"; break;
                case 0xD: oss += "DIVU"; break;
                case 0xE: oss += "REM"; break;
                case 0xF: oss += "REMU"; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " R" + std::to_string(rd) + ", R" + std::to_string(rs1) + ", R" + std::to_string(rs2);
            break;
        }
        case 0x1: { // I-type arithmetic
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs1 = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            oss += "I-TYPE ";
            switch (sub_op) {
                case 0x0: oss += "ADDI"; break;
                case 0x1: oss += "ANDI"; break;
                case 0x2: oss += "ORI"; break;
                case 0x3: oss += "XORI"; break;
                case 0x4: oss += "SHLI"; break;
                case 0x5: oss += "SHRI"; break;
                case 0x6: oss += "SARI"; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " R" + std::to_string(rd) + ", R" + std::to_string(rs1) + ", " + std::to_string(imm);
            break;
        }
        case 0x2: { // Load/Store
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            oss += "LOAD/STORE ";
            switch (sub_op) {
                case 0x0: oss += "LB"; break;
                case 0x1: oss += "LBU"; break;
                case 0x2: oss += "LH"; break;
                case 0x3: oss += "LHU"; break;
                case 0x4: oss += "LW"; break;
                case 0x5: oss += "SB"; break;
                case 0x6: oss += "SH"; break;
                case 0x7: oss += "SW"; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " R" + std::to_string(rd) + ", " + std::to_string(imm) + "(R" + std::to_string(rs) + ")";
            break;
        }
        case 0x3: { // Branch
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rs1 = (instruction >> 20) & 0x0F;
            uint32_t rs2 = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            oss += "BRANCH ";
            switch (sub_op) {
                case 0x0: oss += "BEQ"; break;
                case 0x1: oss += "BNE"; break;
                case 0x2: oss += "BLT"; break;
                case 0x3: oss += "BGE"; break;
                case 0x4: oss += "BLTU"; break;
                case 0x5: oss += "BGEU"; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " R" + std::to_string(rs1) + ", R" + std::to_string(rs2) + ", " + std::to_string(imm);
            break;
        }
        case 0x4: { // Jump
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            uint32_t rd = (instruction >> 20) & 0x0F;
            uint32_t rs = (instruction >> 16) & 0x0F;
            int32_t imm = static_cast<int16_t>(instruction & 0xFFFF);
            oss += "JUMP ";
            switch (sub_op) {
                case 0x0: oss += "JAL"; break;
                case 0x1: oss += "JALR"; break;
                default: oss += "UNKNOWN"; break;
            }
            oss += " R" + std::to_string(rd) + ", R" + std::to_string(rs) + ", " + std::to_string(imm);
            break;
        }
        case 0x5: { // Special
            uint32_t sub_op = (instruction >> 24) & 0x0F;
            oss += "SPECIAL ";
            switch (sub_op) {
                case 0x0: oss += "ECALL"; break;
                case 0x1: oss += "BREAK"; break;
                default: oss += "UNKNOWN"; break;
            }
            break;
        }
        case 0xF: // NOP
            oss += "NOP";
            break;
        default:
            oss += "UNKNOWN OPCODE";
            break;
    }
    return oss;
}
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

class RospOSVM {
private:
    RegisterFile regFile;
    uint32_t pc; // Program Counter
    std::vector<uint8_t> memory;
    
    
    void rTypeInstruction(uint32_t instruction) {
        /*
        | 31-28 | 27-24 | 23-20 | 19-16 | 15-12 | 11-0          |
        |-------|-------|-------|-------|-------|---------------|
        | opcode| sub-op|   rd  |  rs1  |  rs2  |   unused      | */
        uint32_t sub_op=(instruction >> 24) & 0x0F;
        uint32_t rd=(instruction >> 20) & 0x0F;
        uint32_t rs1=(instruction >> 16) & 0x0F;
        uint32_t rs2=(instruction >> 12) & 0x0F;
        switch(sub_op){
            case 0x0: // ADD
                regFile[rd].set(regFile[rs1].get() + regFile[rs2].get());
                break;
            case 0x1: // SUB
                regFile[rd].set(regFile[rs1].get() - regFile[rs2].get());
                break;
            case 0x2: // AND
                regFile[rd].set(regFile[rs1].get() & regFile[rs2].get());
                break;
            case 0x3: // OR
                regFile[rd].set(regFile[rs1].get() | regFile[rs2].get());
                break;
            case 0x4: // XOR
                regFile[rd].set(regFile[rs1].get() ^ regFile[rs2].get());
                break;
            case 0x5: // MUL (lower 32 bits)
                regFile[rd].set(regFile[rs1].get() * regFile[rs2].get());
                break;
            case 0x6: //MULH
                {
                    uint64_t result = static_cast<uint64_t>(regFile[rs1].get()) * static_cast<uint64_t>(regFile[rs2].get());
                    regFile[rd].set(static_cast<uint32_t>(result >> 32));
                }
                break;
            case 0x7: //NEG
                regFile[rd].set(-regFile[rs1].get());
                break;
            case 0x8: // NOT
                regFile[rd].set(~regFile[rs1].get());
                break;
            case 0x9: //SHL
                regFile[rd].set(regFile[rs1].get() << (regFile[rs2].get() & 0x1F));
                break;
            case 0xA: //SHR
                regFile[rd].set(regFile[rs1].get() >> (regFile[rs2].get() & 0x1F));
                break;
            case 0xB: //SAR
                regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) >> (regFile[rs2].get() & 0x1F));
                break;
            case 0xC: //DIV
                if (regFile[rs2].get() == 0) {
                    std::cerr << "Division by zero error in DIV instruction." << std::endl;
                    regFile[rd].set(0xFFFFFFFF);
                } else {
                    regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) / static_cast<int32_t>(regFile[rs2].get()));
                }
                break;
            case 0xD: //DIVU
                if (regFile[rs2].get() == 0) {
                    std::cerr << "Division by zero error in DIVU instruction." << std::endl;
                    regFile[rd].set(0xFFFFFFFF);
                } else {
                    regFile[rd].set(regFile[rs1].get() / regFile[rs2].get());
                }
                break;
            case 0xE: //REM
                if (regFile[rs2].get() == 0) {
                    std::cerr << "Division by zero error in REM instruction." << std::endl;
                    regFile[rd].set(0xFFFFFFFF);
                } else {
                    regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) % static_cast<int32_t>(regFile[rs2].get()));
                }
                break;
            case 0xF: //REMU
                if (regFile[rs2].get() == 0) {
                    std::cerr << "Division by zero error in REMU instruction." << std::endl;
                    regFile[rd].set(0xFFFFFFFF);
                } else {
                    regFile[rd].set(regFile[rs1].get() % regFile[rs2].get());
                }
                break;
            default:
                std::cerr << "Unknown R-type sub-opcode: " << sub_op << std::endl;
                break;
        }
    }
    void iArithTypeInstruction(uint32_t instruction) {
        /*
        | 31-28 | 27-24 | 23-20 | 19-16 | 15-0           |
        |-------|-------|-------|-------|----------------|
        | opcode| sub-op|   rd  |  rs1  |   immediate    | */
        uint32_t sub_op=(instruction >> 24) & 0x0F;
        uint32_t rd=(instruction >> 20) & 0x0F;
        uint32_t rs1=(instruction >> 16) & 0x0F;
        int32_t r_imm=static_cast<int32_t>(instruction & 0xFFFF);
        int32_t zero_ext_imm=static_cast<uint16_t>(instruction & 0xFFFF);
        int32_t sign_ext_imm=(r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
        
        switch(sub_op){
            case 0x0: // ADDI
                regFile[rd].set(regFile[rs1].get() + sign_ext_imm);
                break;
            case 0x1: // ANDI
                regFile[rd].set(regFile[rs1].get() & zero_ext_imm);
                break;
            case 0x2: // ORI
                regFile[rd].set(regFile[rs1].get() | zero_ext_imm);
                break;
            case 0x3: // XORI
                regFile[rd].set(regFile[rs1].get() ^ zero_ext_imm);
                break;
            case 0x4: // SHLI
                regFile[rd].set(regFile[rs1].get() << (zero_ext_imm & 0x1F));
                break;
            case 0x5: // SHRI
                regFile[rd].set(regFile[rs1].get() >> (zero_ext_imm & 0x1F));
                break;
            case 0x6: // SARI
                regFile[rd].set(static_cast<int32_t>(regFile[rs1].get()) >> (zero_ext_imm & 0x1F));
                break;
            default:
                std::cerr << "Unknown I-type sub-opcode: " << sub_op << std::endl;
                break;
        }
    }
    void iTypeLSInstruction(uint32_t instruction) {
        /*
        | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
        |-------|-------|-------|-------|--------------------------|
        | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
        */
        uint32_t sub_op=(instruction >> 24) & 0x0F;
        uint32_t rd=(instruction >> 20) & 0x0F;
        uint32_t rs=(instruction >> 16) & 0x0F;
        int32_t r_imm=static_cast<int32_t>(instruction & 0xFFFF);
        int32_t sign_ext_imm=(r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
        uint32_t addr = regFile[rs].get() + sign_ext_imm;
        switch (sub_op){
            case 0x0: //LB
                regFile[rd].set(static_cast<int8_t>(memory[addr]));
                break;
            case 0x1: //LBU
                regFile[rd].set(static_cast<uint8_t>(memory[addr]));
                break;
            case 0x2: //LH
                regFile[rd].set(static_cast<int16_t>(memory[addr] | (memory[addr + 1] << 8)));
                break;
            case 0x3: //LHU
                regFile[rd].set(static_cast<uint16_t>(memory[addr] | (memory[addr + 1] << 8)));
                break;
            case 0x4: //LW
                regFile[rd].set(static_cast<uint32_t>(memory[addr] | (memory[addr + 1] << 8) | (memory[addr + 2] << 16) | (memory[addr + 3] << 24)));
                break;
            case 0x5: //SB
                memory[addr] = static_cast<uint8_t>(regFile[rd].get() & 0xFF);
                break;
            case 0x6: //SH
                {
                
                    memory[addr] = static_cast<uint8_t>(regFile[rd].get() & 0xFF);
                    memory[addr + 1] = static_cast<uint8_t>((regFile[rd].get() >> 8) & 0xFF);
                }
                break;
            case 0x7: //SW
                {
                    memory[addr] = static_cast<uint8_t>(regFile[rd].get() & 0xFF);
                    memory[addr + 1] = static_cast<uint8_t>((regFile[rd].get() >> 8) & 0xFF);
                    memory[addr + 2] = static_cast<uint8_t>((regFile[rd].get() >> 16) & 0xFF);
                    memory[addr + 3] = static_cast<uint8_t>((regFile[rd].get() >> 24) & 0xFF);
                }
                break;
            default:
                std::cerr << "Unknown Load/Store sub-opcode: " << sub_op << std::endl;
                break;
            }
        }
    void bTypeInstruction(uint32_t instruction){
        /*
        | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
        |-------|-------|-------|-------|--------------------------|
        | opcode| sub-op|  rs1  |  rs2  | immediate (16-bit offset)|
        */
        uint32_t sub_op=(instruction >> 24) & 0x0F;
        uint32_t rs1=(instruction >> 20) & 0x0F;
        uint32_t rs2=(instruction >> 16) & 0x0F;
        int32_t r_imm=static_cast<int32_t>(instruction & 0xFFFF);
        int32_t sign_ext_imm=(r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
        
        sign_ext_imm <<= 2; // Branch addresses are word-aligned
        
        std::cout << "Branch check: R" << rs1 << "=" << regFile[rs1].get() << ", R" << rs2 << "=" << regFile[rs2].get() << std::endl;
        bool takeBranch = false;
        switch(sub_op){
            case 0x0: // BEQ
                takeBranch = (regFile[rs1].get() == regFile[rs2].get());
                break;
            case 0x1: // BNE
                takeBranch = (regFile[rs1].get() != regFile[rs2].get());
                break;
            case 0x2: // BLT
                takeBranch = (static_cast<int32_t>(regFile[rs1].get()) < static_cast<int32_t>(regFile[rs2].get()));
                break;
            case 0x3: // BGE
                takeBranch = (static_cast<int32_t>(regFile[rs1].get()) >= static_cast<int32_t>(regFile[rs2].get()));
                break;
            case 0x4: // BLTU
                takeBranch = (regFile[rs1].get() < regFile[rs2].get());
                break;
            case 0x5: // BGEU
                takeBranch = (regFile[rs1].get() >= regFile[rs2].get());
                break;
            default:
                std::cerr << "Unknown B-type sub-opcode: " << sub_op << std::endl;
                break;
        }
        std::cout << "Branch " << (takeBranch ? "taken" : "not taken") << std::endl;
        if(takeBranch){
            pc += sign_ext_imm;
        }
    }
    void jTypeInstruction(uint32_t instruction){
        /*
        | 31-28 | 27-24 | 23-20 | 19-16 | 15-0                     |
        |-------|-------|-------|-------|--------------------------|
        | opcode| sub-op|   rd  |  rs   | immediate (16-bit offset)|
        */
        int32_t sub_op=(instruction >> 24) & 0x0F;
        int32_t rd=(instruction >> 20) & 0x0F;
        int32_t rs=(instruction >> 16) & 0x0F;
        int32_t r_imm=static_cast<int32_t>(instruction & 0xFFFF);
        int32_t sign_ext_imm=(r_imm & 0x8000) ? (r_imm | 0xFFFF0000) : r_imm;
        switch(sub_op){
            case 0x0: // JAL
                regFile[rd].set(pc + 4);
                pc += sign_ext_imm<<2;
                break;
            case 0x1: // JALR
                {
                    uint32_t temp = pc + 4;
                    pc = (regFile[rs].get() + (sign_ext_imm<<2)) & ~1;
                    regFile[rd].set(temp);
                }
                break;
        }
    }
    void sTypeInstruction(uint32_t instruction){
        /*
            | 31-28 | 27-24 | 23-0                             |
            |-------|-------|----------------------------------|
            | opcode| sub-op|   unused                         |
        */
        uint32_t sub_op=(instruction >> 24) & 0x0F;
        switch(sub_op){
            case 0x0: // ECALL
                std::cout << "ECALL invoked." << std::endl;
                break;
            case 0x1: // BREAK
                std::cout << "BREAK invoked. Halting execution." << std::endl;
                std::cout << "Final Register State: " << getRegisterState() << std::endl;
                std::cout << "Final PC: " << std::hex << pc << std::dec << std::endl;
                std::cout << "Top 256 bytes of Memory Dump:" << std::endl;
                for (uint32_t addr = 0; addr < 256; ++addr) {
                    if (addr % 16 == 0) {
                        std::cout << std::hex << (addr) << ": ";
                    }
                    std::cout << std::hex << static_cast<int>(memory[addr]) << " ";
                    if (addr % 16 == 15) {
                        std::cout << std::endl;
                    }
                }
                exit(0);
                break;
            default:
                std::cerr << "Unknown S-type sub-opcode: " << sub_op << std::endl;
                break;
        }
    }
    void executeInstruction(uint32_t instruction) {
        uint32_t opcode = (instruction >> 28) & 0x0F;
        switch (opcode) {
            case 0x0: // R-type arithmetic
                rTypeInstruction(instruction);
                break;
            case 0x1: // I-type arithmetic/logical (immediate)
                iArithTypeInstruction(instruction);
                break;
            case 0x2: // Load/Store (I-type)
                iTypeLSInstruction(instruction);
                break;
            case 0x3: // Branch (B-type)
                bTypeInstruction(instruction);
                break;
            case 0x4: // Jump (J-type)
                jTypeInstruction(instruction);
                break;
            case 0x5: // Special (S-type)
                sTypeInstruction(instruction);
                break;
            case 0xF: // NOP
                // Do nothing
                break;
            default:
                std::cerr << "Unknown opcode: " << opcode << std::endl;
                break;
        }
        pc += 4; // Move to next instruction    
    }
public:
    RospOSVM() {
        // Initialize VM state
        pc = 0xFFFF0000; // Start of kernel space
        memory.resize(1ULL << 32); // 4GB memory
        regFile.sp().set(0x0FFFFFFF); // Top of RAM
    }
    void loadBinary(const std::vector<char>& binary) {
        // Load binary into memory starting at address 0x00000000
        std::copy(binary.begin(), binary.end(), memory.begin());
    }
    void loadBinaryAtAddress(const std::vector<char>& binary, uint32_t address) {
        if (address + binary.size() > memory.size()) {
            throw std::out_of_range("Memory overflow while loading binary.");
        }
        std::copy(binary.begin(), binary.end(), memory.begin() + address);
    }
    void step() {
        // Fetch instruction
        uint32_t instruction = static_cast<uint32_t>(memory[pc]<<24) |
                               (static_cast<uint32_t>(memory[pc + 1]) << 16) |
                               (static_cast<uint32_t>(memory[pc + 2]) << 8) |
                               (static_cast<uint32_t>(memory[pc + 3]));
        // Execute instruction
        executeInstruction(instruction);
        std::cout << "PC: " << std::hex << pc << std::dec << " ";
        std::cout << "Instruction: 0x" << std::hex << std::setw(8) << std::setfill('0') << instruction << std::dec << " ";
        std::cout << decodeInstruction(instruction) << " ";
        std::cout << getRegisterState() << std::endl;
    }
    std::string getRegisterState() const {
        std::string state;
        for (int i = 0; i < 16; ++i) {
            state += "R" + std::to_string(i) + ": " + std::to_string(regFile[i].get()) + " ";
        }
        return state;
    }
};

std::map<uint32_t, std::string> parseMemoryMap(const std::string& mmapFile) {
    std::map<uint32_t, std::string> memoryMap;
    std::ifstream file(mmapFile);
    if (!file) {
        std::cerr << "Failed to open memory map file: " << mmapFile << std::endl;
        exit(1);
    }

    std::string line;
    while (std::getline(file, line)) {
        std::istringstream iss(line);
        uint32_t address;
        std::string filename;
        if (!(iss >> std::hex >> address) || !(iss.ignore(2)) || !(iss >> filename)) {
            std::cerr << "Invalid line in memory map file: " << line << std::endl;
            exit(1);
        }
        memoryMap[address] = filename;
    }
    return memoryMap;
}

int main(int argc, char* argv[]) {
    std::cout << "RospOS Virtual Machine starting..." << std::endl;
    if (argc < 2) {
        std::cerr << "Usage: " << argv[0] << " <mmap.txt>" << std::endl;
        return 1;
    }

    std::string mmapFile = argv[1];
    auto memoryMap = parseMemoryMap(mmapFile);

    RospOSVM vm;
    for (const auto& [address, filename] : memoryMap) {
        std::ifstream file(filename, std::ios::binary | std::ios::ate);
        if (!file) {
            std::cerr << "Failed to open binary file: " << filename << std::endl;
            continue;
        }

        std::streamsize size = file.tellg();
        file.seekg(0, std::ios::beg);

        std::vector<char> buffer(size);
        if (!file.read(buffer.data(), size)) {
            std::cerr << "Failed to read binary file: " << filename << std::endl;
            continue;
        }

        try {
            vm.loadBinaryAtAddress(buffer, address);
            std::cout << "Loaded " << filename << " at address 0x" << std::hex << address << std::endl;
        } catch (const std::exception& e) {
            std::cerr << "Error loading binary at address 0x" << std::hex << address << ": " << e.what() << std::endl;
        }
    }

    // Simple execution loop
    for (int i = 0; i < 2000; ++i) {
        vm.step();
    }

    return 0;
}