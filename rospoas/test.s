_MAIN:
    ADDI r1, r0, 10
    ADDI r2, r0, 0
    ADDI r3, r0, 1
    ADDI r4, r0, 1

LOOP:
    ADD r5, r2, r3
    ADD r2, r3, r0
    ADD r3, r5, r0
    ADDI r4, r4, 1
    BLT r4, r1, LOOP

SW r5, 0(r0)

ADDI r6, r0, 10

ADDI r2, r0, 1
SHLI r2, r2, 28

DIV_LOOP:

    REM r1, r5, r6
    ADDI r1, r1, 48
    DIV r5, r5, r6
    SW r1, 0(r2)
    BNE r5, r0, DIV_LOOP

BREAK