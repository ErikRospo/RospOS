TARGET := riscv32-unknown-unknown
CC := clang
CFLAGS := --no-standard-libraries --no-standard-includes --target=$(TARGET) -S -O2 -fno-builtin -fno-ident -ffreestanding -dA -msoft-float
SRC := riscv_transcompiler.c
OBJ := $(SRC:.c=.s)
ROS := $(OBJ:.s=.ros)

all: $(ROS) 

dummy: $(ROS) $(OBJ)

%.ros: %.s
	python3 transpiler.py $< -o $@

%.s: %.c
	$(CC) $(CFLAGS) $< -o $@

clean:
	rm -f $(OBJ)
	rm -f $(ROS)