# ABI definitions for RospOS

ARG_REGS = ["r1", "r2", "r3", "r4"]
RETURN_REG = "r1"
LINK_REG = "r14"
SP_REG = "r15"

# Caller-saved registers (must be saved by caller if needed across calls)
CALLER_SAVED = ["r1", "r2", "r3", "r4", "r5", "r6", "r7", "r13"]

# Callee-saved registers (callee must preserve)
CALLEE_SAVED = ["r8", "r9", "r10", "r11", "r12"]

# Temporaries available for register allocation (simple allocator will use these)
TEMP_REGS = [f"r{i}" for i in range(2, 13)]

# A small set of general-purpose registers reserved for special uses
SPECIAL_REGS = {
    "zero": "r0",
    "sp": SP_REG,
    "lr": LINK_REG,
    "ret": RETURN_REG,
}

__all__ = [
    "ARG_REGS",
    "RETURN_REG",
    "LINK_REG",
    "SP_REG",
    "CALLER_SAVED",
    "CALLEE_SAVED",
    "TEMP_REGS",
    "SPECIAL_REGS",
]
