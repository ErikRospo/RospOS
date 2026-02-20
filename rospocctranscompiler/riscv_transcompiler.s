	.attribute	4, 16
	.attribute	5, "rv32i2p1_m2p0_a2p1_c2p0_zmmul1p0_zaamo1p0_zalrsc1p0_zca1p0"
	.file	"riscv_transcompiler.c"
	.text
	.globl	print_string                    # -- Begin function print_string
	.p2align	1
	.type	print_string,@function
print_string:                           # @print_string
# %bb.0:
	lbu	a1, 0(a0)
	beqz	a1, .LBB0_3
# %bb.1:
	addi	a0, a0, 1
	lui	a2, 65536
.LBB0_2:                                # =>This Inner Loop Header: Depth=1
	sb	a1, 0(a2)
	lbu	a1, 0(a0)
	addi	a0, a0, 1
	bnez	a1, .LBB0_2
.LBB0_3:
	ret
.Lfunc_end0:
	.size	print_string, .Lfunc_end0-print_string
                                        # -- End function
	.globl	print_char                      # -- Begin function print_char
	.p2align	1
	.type	print_char,@function
print_char:                             # @print_char
# %bb.0:
	lui	a1, 65536
	sb	a0, 0(a1)
	ret
.Lfunc_end1:
	.size	print_char, .Lfunc_end1-print_char
                                        # -- End function
	.globl	printi                          # -- Begin function printi
	.p2align	1
	.type	printi,@function
printi:                                 # @printi
# %bb.0:
	addi	sp, sp, -16
	beqz	a0, .LBB2_12
# %bb.1:
	bgez	a0, .LBB2_3
# %bb.2:
	lui	a1, 65536
	li	a2, 45
	sb	a2, 0(a1)
	neg	a0, a0
.LBB2_3:
	li	a3, 0
	addi	a1, sp, 3
	lui	a2, 838861
	addi	a7, a2, -819
	li	a6, 9
.LBB2_4:                                # =>This Inner Loop Header: Depth=1
	mv	t0, a3
	mv	a5, a0
	mulhu	a4, a0, a7
	addi	a3, a3, 1
	srli	a0, a4, 3
	andi	a4, a4, 248
	slli	a2, a0, 1
	sub	a4, a5, a4
	sub	a4, a4, a2
	ori	a2, a4, 48
	sb	a2, 1(a1)
	addi	a1, a1, 1
	bltu	a6, a5, .LBB2_4
# %bb.5:
	sb	zero, 1(a1)
	beqz	t0, .LBB2_8
# %bb.6:
	srli	a3, a3, 1
	seqz	a0, a3
	add	a3, a3, a0
	addi	a0, sp, 4
	add	a2, a0, t0
	sub	a2, a2, a3
.LBB2_7:                                # =>This Inner Loop Header: Depth=1
	lbu	a3, 0(a1)
	lbu	a4, 0(a0)
	sb	a3, 0(a0)
	sb	a4, 0(a1)
	addi	a1, a1, -1
	addi	a0, a0, 1
	bne	a1, a2, .LBB2_7
.LBB2_8:
	lbu	a0, 4(sp)
	beqz	a0, .LBB2_11
# %bb.9:
	addi	a1, sp, 5
	lui	a2, 65536
.LBB2_10:                               # =>This Inner Loop Header: Depth=1
	sb	a0, 0(a2)
	lbu	a0, 0(a1)
	addi	a1, a1, 1
	bnez	a0, .LBB2_10
.LBB2_11:
	addi	sp, sp, 16
	ret
.LBB2_12:
	lui	a0, 65536
	li	a1, 48
	sb	a1, 0(a0)
	addi	sp, sp, 16
	ret
.Lfunc_end2:
	.size	printi, .Lfunc_end2-printi
                                        # -- End function
	.globl	read_char                       # -- Begin function read_char
	.p2align	1
	.type	read_char,@function
read_char:                              # @read_char
# %bb.0:
	lui	a0, 65536
	lbu	a0, 0(a0)
	ret
.Lfunc_end3:
	.size	read_char, .Lfunc_end3-read_char
                                        # -- End function
	.globl	read_string                     # -- Begin function read_string
	.p2align	1
	.type	read_string,@function
read_string:                            # @read_string
# %bb.0:
	li	a5, 0
	li	a2, 2
	blt	a1, a2, .LBB4_6
# %bb.1:
	addi	a1, a1, -1
	lui	a6, 65536
	li	a4, 10
	li	a7, 13
.LBB4_2:                                # =>This Inner Loop Header: Depth=1
	lbu	a3, 0(a6)
	beq	a3, a4, .LBB4_6
# %bb.3:                                #   in Loop: Header=BB4_2 Depth=1
	beq	a3, a7, .LBB4_6
# %bb.4:                                #   in Loop: Header=BB4_2 Depth=1
	addi	a2, a5, 1
	add	a5, a5, a0
	sb	a3, 0(a5)
	mv	a5, a2
	bne	a1, a2, .LBB4_2
# %bb.5:
	mv	a5, a1
.LBB4_6:
	add	a5, a5, a0
	sb	zero, 0(a5)
	ret
.Lfunc_end4:
	.size	read_string, .Lfunc_end4-read_string
                                        # -- End function
	.globl	align4                          # -- Begin function align4
	.p2align	1
	.type	align4,@function
align4:                                 # @align4
# %bb.0:
	addi	a0, a0, 3
	andi	a0, a0, -4
	ret
.Lfunc_end5:
	.size	align4, .Lfunc_end5-align4
                                        # -- End function
	.globl	malloc                          # -- Begin function malloc
	.p2align	1
	.type	malloc,@function
malloc:                                 # @malloc
# %bb.0:
	blez	a0, .LBB6_5
# %bb.1:
	lui	a1, %hi(heap_info_head)
	lw	a4, %lo(heap_info_head)(a1)
	lui	a3, 524288
	addi	a6, a3, -4
	addi	a0, a0, 3
	and	a2, a0, a6
	bnez	a4, .LBB6_7
# %bb.2:
	li	a1, 0
.LBB6_3:
	lui	a0, %hi(.L_MergedGlobals)
	lw	a4, %lo(.L_MergedGlobals)(a0)
	addi	a0, a0, %lo(.L_MergedGlobals)
	lw	a0, 4(a0)
	add	a0, a0, a4
	blez	a0, .LBB6_5
# %bb.4:
	lui	a5, %hi(.L_MergedGlobals+8)
	lw	a3, %lo(.L_MergedGlobals+8)(a5)
	add	a5, a0, a2
	bge	a3, a5, .LBB6_12
.LBB6_5:
	li	a0, 0
	ret
.LBB6_6:                                #   in Loop: Header=BB6_7 Depth=1
	lw	a4, 12(a1)
	beqz	a4, .LBB6_3
.LBB6_7:                                # =>This Inner Loop Header: Depth=1
	mv	a1, a4
	lw	a0, 8(a4)
	beqz	a0, .LBB6_6
# %bb.8:                                #   in Loop: Header=BB6_7 Depth=1
	lw	a4, 0(a1)
	blt	a4, a2, .LBB6_6
# %bb.9:
	lui	a0, %hi(.L_MergedGlobals+4)
	lw	a3, %lo(.L_MergedGlobals+4)(a0)
	sub	a4, a4, a2
	addi	a5, a3, 4
	blt	a4, a5, .LBB6_11
# %bb.10:
	lw	a5, 4(a1)
	sub	a4, a4, a3
	li	a6, 1
	lw	a3, 12(a1)
	add	a5, a5, a2
	sw	a4, 0(a5)
	lw	a0, %lo(.L_MergedGlobals+4)(a0)
	sw	a6, 8(a5)
	add	a0, a0, a5
	sw	a0, 4(a5)
	sw	a3, 12(a5)
	sw	a2, 0(a1)
	sw	a5, 12(a1)
.LBB6_11:
	lw	a0, 4(a1)
	sw	zero, 8(a1)
	ret
.LBB6_12:
	sw	a2, 0(a4)
	sw	a0, 4(a4)
	sw	zero, 8(a4)
	sw	zero, 12(a4)
	beqz	a1, .LBB6_14
# %bb.13:
	sw	a4, 12(a1)
	j	.LBB6_15
.LBB6_14:
	lui	a1, %hi(heap_info_head)
	sw	a4, %lo(heap_info_head)(a1)
.LBB6_15:
	addi	a5, a5, 3
	and	a1, a5, a6
	lui	a2, %hi(.L_MergedGlobals)
	sw	a1, %lo(.L_MergedGlobals)(a2)
	ret
.Lfunc_end6:
	.size	malloc, .Lfunc_end6-malloc
                                        # -- End function
	.globl	free                            # -- Begin function free
	.p2align	1
	.type	free,@function
free:                                   # @free
# %bb.0:
	beqz	a0, .LBB7_13
# %bb.1:
	lui	a1, %hi(heap_info_head)
	lw	a1, %lo(heap_info_head)(a1)
	beqz	a1, .LBB7_13
# %bb.2:
	lw	a2, 4(a1)
	bne	a2, a0, .LBB7_4
# %bb.3:
	li	a2, 0
	j	.LBB7_7
.LBB7_4:
	mv	a3, a1
.LBB7_5:                                # =>This Inner Loop Header: Depth=1
	lw	a1, 12(a3)
	beqz	a1, .LBB7_13
# %bb.6:                                #   in Loop: Header=BB7_5 Depth=1
	lw	a4, 4(a1)
	mv	a2, a3
	mv	a3, a1
	bne	a4, a0, .LBB7_5
.LBB7_7:
	lw	a0, 12(a1)
	li	a3, 1
	sw	a3, 8(a1)
	beqz	a0, .LBB7_10
# %bb.8:
	lw	a3, 8(a0)
	beqz	a3, .LBB7_10
# %bb.9:
	lui	a3, %hi(.L_MergedGlobals+4)
	lw	a4, 0(a1)
	lw	a3, %lo(.L_MergedGlobals+4)(a3)
	lw	a5, 0(a0)
	lw	a0, 12(a0)
	add	a3, a3, a4
	add	a3, a3, a5
	sw	a3, 0(a1)
	sw	a0, 12(a1)
.LBB7_10:
	beqz	a2, .LBB7_13
# %bb.11:
	lw	a3, 8(a2)
	beqz	a3, .LBB7_13
# %bb.12:
	lui	a3, %hi(.L_MergedGlobals+4)
	lw	a4, 0(a2)
	lw	a3, %lo(.L_MergedGlobals+4)(a3)
	lw	a1, 0(a1)
	add	a3, a3, a4
	add	a1, a1, a3
	sw	a1, 0(a2)
	sw	a0, 12(a2)
.LBB7_13:
	ret
.Lfunc_end7:
	.size	free, .Lfunc_end7-free
                                        # -- End function
	.globl	_dump_heap_info                 # -- Begin function _dump_heap_info
	.p2align	1
	.type	_dump_heap_info,@function
_dump_heap_info:                        # @_dump_heap_info
# %bb.0:
	lui	a0, %hi(heap_info_head)
	lw	t0, %lo(heap_info_head)(a0)
	beqz	t0, .LBB8_32
# %bb.1:
	addi	sp, sp, -64
	sw	ra, 60(sp)                      # 4-byte Folded Spill
	sw	s0, 56(sp)                      # 4-byte Folded Spill
	sw	s1, 52(sp)                      # 4-byte Folded Spill
	sw	s2, 48(sp)                      # 4-byte Folded Spill
	sw	s3, 44(sp)                      # 4-byte Folded Spill
	sw	s4, 40(sp)                      # 4-byte Folded Spill
	sw	s5, 36(sp)                      # 4-byte Folded Spill
	sw	s6, 32(sp)                      # 4-byte Folded Spill
	sw	s7, 28(sp)                      # 4-byte Folded Spill
	sw	s8, 24(sp)                      # 4-byte Folded Spill
	sw	s9, 20(sp)                      # 4-byte Folded Spill
	sw	s10, 16(sp)                     # 4-byte Folded Spill
	sw	s11, 12(sp)                     # 4-byte Folded Spill
	lui	t3, 65536
	li	t5, 107
	li	a7, 32
	li	t6, 97
	li	s2, 116
	li	s9, 48
	li	s11, 45
	li	s3, 83
	li	s4, 105
	li	s5, 122
	li	ra, 101
	li	s10, 58
	li	s6, 70
	li	s7, 114
	li	s8, 10
	lui	a0, 838861
	mv	t2, sp
	addi	t4, a0, -819
	li	t1, 9
	j	.LBB8_4
.LBB8_2:                                #   in Loop: Header=BB8_4 Depth=1
	sb	s9, 0(t3)
.LBB8_3:                                #   in Loop: Header=BB8_4 Depth=1
	sb	s8, 0(t3)
	lw	t0, 12(t0)
	beqz	t0, .LBB8_31
.LBB8_4:                                # =>This Loop Header: Depth=1
                                        #     Child Loop BB8_8 Depth 2
                                        #     Child Loop BB8_11 Depth 2
                                        #     Child Loop BB8_14 Depth 2
                                        #     Child Loop BB8_20 Depth 2
                                        #     Child Loop BB8_23 Depth 2
                                        #     Child Loop BB8_26 Depth 2
                                        #     Child Loop BB8_30 Depth 2
	li	a0, 66
	sb	a0, 0(t3)
	li	a0, 108
	sb	a0, 0(t3)
	li	a0, 111
	sb	a0, 0(t3)
	li	a0, 99
	sb	a0, 0(t3)
	sb	t5, 0(t3)
	sb	a7, 0(t3)
	sb	t6, 0(t3)
	sb	s2, 0(t3)
	sb	a7, 0(t3)
	lw	s0, 4(t0)
	beqz	s0, .LBB8_15
# %bb.5:                                #   in Loop: Header=BB8_4 Depth=1
	bgez	s0, .LBB8_7
# %bb.6:                                #   in Loop: Header=BB8_4 Depth=1
	sb	s11, 0(t3)
	neg	s0, s0
.LBB8_7:                                #   in Loop: Header=BB8_4 Depth=1
	li	a0, 0
	li	s1, 1
	mv	a1, sp
.LBB8_8:                                #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	mv	a6, a0
	mv	a4, s0
	mv	a2, s1
	mv	a3, a1
	mulhu	a1, s0, t4
	addi	a0, a0, 1
	srli	s0, a1, 3
	andi	a1, a1, 248
	slli	s1, s0, 1
	sub	a1, a4, a1
	sub	a1, a1, s1
	add	s1, t2, a6
	ori	a1, a1, 48
	sb	a1, 0(s1)
	addi	s1, a2, 1
	addi	a1, a3, 1
	bltu	t1, a4, .LBB8_8
# %bb.9:                                #   in Loop: Header=BB8_4 Depth=1
	add	a0, a0, t2
	sb	zero, 0(a0)
	beqz	a6, .LBB8_12
# %bb.10:                               #   in Loop: Header=BB8_4 Depth=1
	srli	a2, a2, 1
	seqz	a0, a2
	add	a2, a2, a0
	mv	a0, sp
	add	a6, a6, a0
	sub	a2, a6, a2
.LBB8_11:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	lbu	a1, 0(a3)
	lbu	a4, 0(a0)
	sb	a1, 0(a0)
	sb	a4, 0(a3)
	addi	a3, a3, -1
	addi	a0, a0, 1
	bne	a3, a2, .LBB8_11
.LBB8_12:                               #   in Loop: Header=BB8_4 Depth=1
	lbu	a0, 0(sp)
	beqz	a0, .LBB8_16
# %bb.13:                               #   in Loop: Header=BB8_4 Depth=1
	addi	a1, sp, 1
.LBB8_14:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	sb	a0, 0(t3)
	lbu	a0, 0(a1)
	addi	a1, a1, 1
	bnez	a0, .LBB8_14
	j	.LBB8_16
.LBB8_15:                               #   in Loop: Header=BB8_4 Depth=1
	sb	s9, 0(t3)
.LBB8_16:                               #   in Loop: Header=BB8_4 Depth=1
	sb	a7, 0(t3)
	sb	s11, 0(t3)
	sb	a7, 0(t3)
	sb	s3, 0(t3)
	sb	s4, 0(t3)
	sb	s5, 0(t3)
	sb	ra, 0(t3)
	sb	s10, 0(t3)
	sb	a7, 0(t3)
	lw	a5, 0(t0)
	beqz	a5, .LBB8_27
# %bb.17:                               #   in Loop: Header=BB8_4 Depth=1
	bgez	a5, .LBB8_19
# %bb.18:                               #   in Loop: Header=BB8_4 Depth=1
	sb	s11, 0(t3)
	neg	a5, a5
.LBB8_19:                               #   in Loop: Header=BB8_4 Depth=1
	li	s1, 0
	li	a0, 1
	mv	a4, sp
.LBB8_20:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	mv	a2, s1
	mv	s0, a5
	mv	a1, a0
	mv	a3, a4
	mulhu	a0, a5, t4
	addi	s1, s1, 1
	srli	a5, a0, 3
	andi	a0, a0, 248
	slli	a4, a5, 1
	sub	a0, s0, a0
	sub	a0, a0, a4
	add	a4, t2, a2
	ori	a0, a0, 48
	sb	a0, 0(a4)
	addi	a0, a1, 1
	addi	a4, a3, 1
	bltu	t1, s0, .LBB8_20
# %bb.21:                               #   in Loop: Header=BB8_4 Depth=1
	add	s1, s1, t2
	sb	zero, 0(s1)
	beqz	a2, .LBB8_24
# %bb.22:                               #   in Loop: Header=BB8_4 Depth=1
	srli	a1, a1, 1
	seqz	a0, a1
	add	a1, a1, a0
	mv	a0, sp
	add	a2, a2, a0
	sub	a2, a2, a1
.LBB8_23:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	lbu	a1, 0(a3)
	lbu	a4, 0(a0)
	sb	a1, 0(a0)
	sb	a4, 0(a3)
	addi	a3, a3, -1
	addi	a0, a0, 1
	bne	a3, a2, .LBB8_23
.LBB8_24:                               #   in Loop: Header=BB8_4 Depth=1
	lbu	a0, 0(sp)
	beqz	a0, .LBB8_28
# %bb.25:                               #   in Loop: Header=BB8_4 Depth=1
	addi	a1, sp, 1
.LBB8_26:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	sb	a0, 0(t3)
	lbu	a0, 0(a1)
	addi	a1, a1, 1
	bnez	a0, .LBB8_26
	j	.LBB8_28
.LBB8_27:                               #   in Loop: Header=BB8_4 Depth=1
	sb	s9, 0(t3)
.LBB8_28:                               #   in Loop: Header=BB8_4 Depth=1
	sb	a7, 0(t3)
	sb	s11, 0(t3)
	sb	a7, 0(t3)
	sb	s6, 0(t3)
	sb	s7, 0(t3)
	sb	ra, 0(t3)
	sb	ra, 0(t3)
	sb	s10, 0(t3)
	sb	a7, 0(t3)
	lw	a0, 8(t0)
	beqz	a0, .LBB8_2
# %bb.29:                               #   in Loop: Header=BB8_4 Depth=1
	sb	zero, 1(sp)
	li	a1, 49
	addi	a0, sp, 1
.LBB8_30:                               #   Parent Loop BB8_4 Depth=1
                                        # =>  This Inner Loop Header: Depth=2
	sb	a1, 0(t3)
	lbu	a1, 0(a0)
	addi	a0, a0, 1
	bnez	a1, .LBB8_30
	j	.LBB8_3
.LBB8_31:
	lw	ra, 60(sp)                      # 4-byte Folded Reload
	lw	s0, 56(sp)                      # 4-byte Folded Reload
	lw	s1, 52(sp)                      # 4-byte Folded Reload
	lw	s2, 48(sp)                      # 4-byte Folded Reload
	lw	s3, 44(sp)                      # 4-byte Folded Reload
	lw	s4, 40(sp)                      # 4-byte Folded Reload
	lw	s5, 36(sp)                      # 4-byte Folded Reload
	lw	s6, 32(sp)                      # 4-byte Folded Reload
	lw	s7, 28(sp)                      # 4-byte Folded Reload
	lw	s8, 24(sp)                      # 4-byte Folded Reload
	lw	s9, 20(sp)                      # 4-byte Folded Reload
	lw	s10, 16(sp)                     # 4-byte Folded Reload
	lw	s11, 12(sp)                     # 4-byte Folded Reload
	addi	sp, sp, 64
.LBB8_32:
	ret
.Lfunc_end8:
	.size	_dump_heap_info, .Lfunc_end8-_dump_heap_info
                                        # -- End function
	.globl	add                             # -- Begin function add
	.p2align	1
	.type	add,@function
add:                                    # @add
# %bb.0:
	add	a0, a0, a1
	ret
.Lfunc_end9:
	.size	add, .Lfunc_end9-add
                                        # -- End function
	.globl	main                            # -- Begin function main
	.p2align	1
	.type	main,@function
main:                                   # @main
# %bb.0:
	addi	sp, sp, -16
	lui	a0, 65536
	li	a2, 84
	li	a3, 104
	li	a4, 101
	li	a1, 32
	li	a5, 114
	sb	a2, 0(a0)
	li	a6, 115
	sb	a3, 0(a0)
	li	a2, 117
	sb	a4, 0(a0)
	sb	a1, 0(a0)
	sb	a5, 0(a0)
	li	a3, 108
	sb	a4, 0(a0)
	li	a4, 116
	sb	a6, 0(a0)
	sb	a2, 0(a0)
	li	a5, 111
	sb	a3, 0(a0)
	li	a3, 102
	sb	a4, 0(a0)
	li	a2, 49
	sb	a1, 0(a0)
	sb	a5, 0(a0)
	li	a4, 48
	sb	a3, 0(a0)
	li	a3, 43
	sb	a1, 0(a0)
	sb	a2, 0(a0)
	sb	a4, 0(a0)
	li	a4, 53
	sb	a1, 0(a0)
	sb	a3, 0(a0)
	li	a3, 105
	sb	a1, 0(a0)
	sb	a4, 0(a0)
	sb	a1, 0(a0)
	sb	a3, 0(a0)
	li	a5, 58
	sb	a6, 0(a0)
	addi	a3, sp, 5
	sb	a5, 0(a0)
	sb	a1, 0(a0)
	sb	a2, 4(sp)
	sb	a4, 5(sp)
	sb	zero, 6(sp)
.LBB10_1:                               # =>This Inner Loop Header: Depth=1
	sb	a2, 0(a0)
	lbu	a2, 0(a3)
	addi	a3, a3, 1
	bnez	a2, .LBB10_1
# %bb.2:
	lui	a0, %hi(heap_info_head)
	lw	a2, %lo(heap_info_head)(a0)
	beqz	a2, .LBB10_10
# %bb.3:
	li	a0, 4
	j	.LBB10_5
.LBB10_4:                               #   in Loop: Header=BB10_5 Depth=1
	lw	a2, 12(a1)
	beqz	a2, .LBB10_11
.LBB10_5:                               # =>This Inner Loop Header: Depth=1
	mv	a1, a2
	lw	a2, 8(a2)
	beqz	a2, .LBB10_4
# %bb.6:                                #   in Loop: Header=BB10_5 Depth=1
	lw	a3, 0(a1)
	blt	a3, a0, .LBB10_4
# %bb.7:
	lui	a0, %hi(.L_MergedGlobals+4)
	lw	a2, %lo(.L_MergedGlobals+4)(a0)
	addi	a3, a3, -4
	addi	a4, a2, 4
	blt	a3, a4, .LBB10_9
# %bb.8:
	lw	a4, 4(a1)
	sub	a3, a3, a2
	li	a2, 1
	sw	a3, 4(a4)
	lw	a0, %lo(.L_MergedGlobals+4)(a0)
	addi	a3, a4, 4
	sw	a2, 12(a4)
	add	a0, a0, a3
	sw	a0, 8(a4)
	lw	a0, 12(a1)
	li	a2, 4
	sw	a0, 16(a4)
	sw	a2, 0(a1)
	sw	a3, 12(a1)
.LBB10_9:
	lw	a6, 4(a1)
	sw	zero, 8(a1)
	bnez	a6, .LBB10_19
	j	.LBB10_13
.LBB10_10:
	li	a1, 0
.LBB10_11:
	lui	a2, %hi(.L_MergedGlobals)
	lw	a0, %lo(.L_MergedGlobals)(a2)
	addi	a2, a2, %lo(.L_MergedGlobals)
	lw	a6, 4(a2)
	add	a6, a6, a0
	blez	a6, .LBB10_13
# %bb.12:
	lui	a2, %hi(.L_MergedGlobals+8)
	lw	a2, %lo(.L_MergedGlobals+8)(a2)
	addi	a3, a6, 4
	bge	a2, a3, .LBB10_15
.LBB10_13:
	lui	a0, 65536
	li	a1, 77
	li	a6, 101
	li	a3, 109
	li	a4, 111
	li	a5, 114
	li	a2, 121
	sb	a1, 0(a0)
	li	a1, 32
	sb	a6, 0(a0)
	sb	a3, 0(a0)
	li	a3, 97
	sb	a4, 0(a0)
	sb	a5, 0(a0)
	li	a5, 108
	sb	a2, 0(a0)
	li	a2, 99
	sb	a1, 0(a0)
	sb	a3, 0(a0)
	sb	a5, 0(a0)
	sb	a5, 0(a0)
	sb	a4, 0(a0)
	sb	a2, 0(a0)
	li	a2, 116
	sb	a3, 0(a0)
	sb	a2, 0(a0)
	li	a2, 105
	sb	a2, 0(a0)
	sb	a4, 0(a0)
	li	a4, 110
	sb	a4, 0(a0)
	li	a4, 102
	sb	a1, 0(a0)
	li	a1, 100
	sb	a4, 0(a0)
	sb	a3, 0(a0)
	sb	a2, 0(a0)
	sb	a5, 0(a0)
	sb	a6, 0(a0)
	sb	a1, 0(a0)
.LBB10_14:
	li	a0, 0
	addi	sp, sp, 16
	ret
.LBB10_15:
	li	a2, 4
	sw	a2, 0(a0)
	sw	a6, 4(a0)
	sw	zero, 8(a0)
	sw	zero, 12(a0)
	beqz	a1, .LBB10_17
# %bb.16:
	sw	a0, 12(a1)
	j	.LBB10_18
.LBB10_17:
	lui	a1, %hi(heap_info_head)
	sw	a0, %lo(heap_info_head)(a1)
.LBB10_18:
	addi	a0, a6, 7
	lui	a1, 524288
	addi	a1, a1, -4
	and	a0, a0, a1
	lui	a1, %hi(.L_MergedGlobals)
	sw	a0, %lo(.L_MergedGlobals)(a1)
.LBB10_19:
	li	a4, 42
	lui	a1, 65536
	li	a3, 68
	li	a5, 121
	li	a7, 110
	li	a2, 97
	li	t0, 109
	li	t1, 105
	li	t2, 99
	sw	a4, 0(a6)
	li	a4, 108
	sb	a3, 0(a1)
	li	a3, 32
	sb	a5, 0(a1)
	sb	a7, 0(a1)
	sb	a2, 0(a1)
	sb	t0, 0(a1)
	li	a0, 111
	sb	t1, 0(a1)
	sb	t2, 0(a1)
	sb	a2, 0(a1)
	sb	a4, 0(a1)
	sb	a4, 0(a1)
	sb	a5, 0(a1)
	li	t0, 116
	sb	a3, 0(a1)
	sb	a2, 0(a1)
	sb	a4, 0(a1)
	sb	a4, 0(a1)
	sb	a0, 0(a1)
	li	a0, 101
	sb	t2, 0(a1)
	li	a5, 100
	sb	a2, 0(a1)
	sb	t0, 0(a1)
	sb	a0, 0(a1)
	sb	a5, 0(a1)
	li	a5, 103
	sb	a3, 0(a1)
	sb	t1, 0(a1)
	li	t1, 114
	sb	a7, 0(a1)
	li	a7, 118
	sb	t0, 0(a1)
	li	t0, 117
	sb	a0, 0(a1)
	sb	a5, 0(a1)
	li	t2, 40
	sb	a0, 0(a1)
	sb	t1, 0(a1)
	li	t1, 52
	sb	a3, 0(a1)
	sb	a7, 0(a1)
	li	a5, 50
	sb	a2, 0(a1)
	li	a2, 41
	sb	a4, 0(a1)
	li	a4, 58
	sb	t0, 0(a1)
	sb	a0, 0(a1)
	sb	a3, 0(a1)
	sb	t2, 0(a1)
	sb	t1, 0(a1)
	sb	a5, 0(a1)
	sb	a2, 0(a1)
	sb	a4, 0(a1)
	sb	a3, 0(a1)
	lw	a3, 0(a6)
	beqz	a3, .LBB10_30
# %bb.20:
	bgez	a3, .LBB10_22
# %bb.21:
	lui	a0, 65536
	li	a1, 45
	sb	a1, 0(a0)
	neg	a3, a3
.LBB10_22:
	li	a4, 0
	addi	a1, sp, 3
	lui	a0, 838861
	addi	t1, a0, -819
	li	a7, 9
.LBB10_23:                              # =>This Inner Loop Header: Depth=1
	mv	t0, a4
	mv	a2, a3
	mulhu	a5, a3, t1
	addi	a4, a4, 1
	srli	a3, a5, 3
	andi	a5, a5, 248
	slli	a0, a3, 1
	sub	a5, a2, a5
	sub	a5, a5, a0
	ori	a0, a5, 48
	sb	a0, 1(a1)
	addi	a1, a1, 1
	bltu	a7, a2, .LBB10_23
# %bb.24:
	sb	zero, 1(a1)
	beqz	t0, .LBB10_27
# %bb.25:
	srli	a4, a4, 1
	seqz	a0, a4
	add	a4, a4, a0
	addi	a0, sp, 4
	add	a2, a0, t0
	sub	a2, a2, a4
.LBB10_26:                              # =>This Inner Loop Header: Depth=1
	lbu	a3, 0(a1)
	lbu	a4, 0(a0)
	sb	a3, 0(a0)
	sb	a4, 0(a1)
	addi	a1, a1, -1
	addi	a0, a0, 1
	bne	a1, a2, .LBB10_26
.LBB10_27:
	lbu	a0, 4(sp)
	beqz	a0, .LBB10_31
# %bb.28:
	addi	a1, sp, 5
	lui	a2, 65536
.LBB10_29:                              # =>This Inner Loop Header: Depth=1
	sb	a0, 0(a2)
	lbu	a0, 0(a1)
	addi	a1, a1, 1
	bnez	a0, .LBB10_29
	j	.LBB10_31
.LBB10_30:
	li	a0, 48
	sb	a0, 0(a1)
.LBB10_31:
	lui	a0, %hi(heap_info_head)
	lw	a1, %lo(heap_info_head)(a0)
	beqz	a1, .LBB10_14
# %bb.32:
	lw	a0, 4(a1)
	bne	a0, a6, .LBB10_34
# %bb.33:
	li	a2, 0
	j	.LBB10_37
.LBB10_34:
	mv	a0, a1
.LBB10_35:                              # =>This Inner Loop Header: Depth=1
	lw	a1, 12(a0)
	beqz	a1, .LBB10_14
# %bb.36:                               #   in Loop: Header=BB10_35 Depth=1
	lw	a3, 4(a1)
	mv	a2, a0
	mv	a0, a1
	bne	a3, a6, .LBB10_35
.LBB10_37:
	lw	a0, 12(a1)
	li	a3, 1
	sw	a3, 8(a1)
	beqz	a0, .LBB10_40
# %bb.38:
	lw	a3, 8(a0)
	beqz	a3, .LBB10_40
# %bb.39:
	lui	a3, %hi(.L_MergedGlobals+4)
	lw	a3, %lo(.L_MergedGlobals+4)(a3)
	lw	a4, 0(a1)
	lw	a5, 0(a0)
	add	a3, a3, a4
	add	a3, a3, a5
	sw	a3, 0(a1)
	lw	a0, 12(a0)
	sw	a0, 12(a1)
.LBB10_40:
	beqz	a2, .LBB10_14
# %bb.41:
	lw	a3, 8(a2)
	beqz	a3, .LBB10_14
# %bb.42:
	lui	a3, %hi(.L_MergedGlobals+4)
	lw	a4, 0(a2)
	lw	a3, %lo(.L_MergedGlobals+4)(a3)
	lw	a1, 0(a1)
	add	a3, a3, a4
	add	a1, a1, a3
	sw	a1, 0(a2)
	sw	a0, 12(a2)
	j	.LBB10_14
.Lfunc_end10:
	.size	main, .Lfunc_end10-main
                                        # -- End function
	.type	heap_info_head,@object          # @heap_info_head
	.bss
	.globl	heap_info_head
	.p2align	2, 0x0
heap_info_head:
	.word	0
	.size	heap_info_head, 4

	.type	.L_MergedGlobals,@object        # @_MergedGlobals
	.data
	.p2align	2, 0x0
.L_MergedGlobals:
	.word	16777216                        # 0x1000000
	.word	16                              # 0x10
	.word	268369920                       # 0xfff0000
	.size	.L_MergedGlobals, 12

	.globl	heap_top
heap_top = .L_MergedGlobals
	.size	heap_top, 4
	.globl	HEAP_HEADER_SIZE
HEAP_HEADER_SIZE = .L_MergedGlobals+4
	.size	HEAP_HEADER_SIZE, 4
	.globl	STACK_LIMIT
STACK_LIMIT = .L_MergedGlobals+8
	.size	STACK_LIMIT, 4
	.section	".note.GNU-stack","",@progbits
	.addrsig
	.addrsig_sym .L_MergedGlobals
