"""Encode Mali CSF (Valhall v10) instructions for hand-built command streams."""

from __future__ import annotations

import struct

CS_OPCODE_NOP = 0
CS_OPCODE_MOVE48 = 1
CS_OPCODE_MOVE32 = 2
CS_OPCODE_WAIT = 3
CS_OPCODE_LDR = 0x14
CS_OPCODE_STR = 0x15
CS_OPCODE_STM = 21
CS_OPCODE_EVADD32 = 0x25
CS_OPCODE_FLUSH_CACHE = 36

CS_FLUSH_MODE_CLEAN_AND_INVALIDATE = 3
CS_FLUSH_MODE_INVALIDATE = 2

EVADD_FLAG_NO_IRQ = 1 << 2


def cs_mov48(dst: int, imm: int) -> int:
    imm &= (1 << 48) - 1
    return imm | (dst << 48) | (CS_OPCODE_MOVE48 << 56)


def cs_mov32(dst: int, imm: int) -> int:
    return (imm & 0xFFFFFFFF) | (dst << 48) | (CS_OPCODE_MOVE32 << 56)


def cs_wait(wait_mask: int = 1, progress_inc: bool = False) -> int:
    return wait_mask << 32 | (int(progress_inc) << 55) | (CS_OPCODE_WAIT << 56)


def cs_ldr32(addr_reg: int, dst_reg: int, offset: int = 0) -> int:
    rel = dst_reg - addr_reg
    mask = 1 << rel
    b = bytearray(8)
    b[0] = addr_reg
    struct.pack_into("<H", b, 1, mask)
    struct.pack_into("<h", b, 3, offset)
    b[7] = CS_OPCODE_LDR
    return int.from_bytes(b, "little")


def cs_str32(addr_reg: int, src_reg: int, offset: int = 0) -> int:
    rel = src_reg - addr_reg
    mask = 1 << rel
    b = bytearray(8)
    b[0] = addr_reg
    struct.pack_into("<H", b, 1, mask)
    struct.pack_into("<h", b, 3, offset)
    b[7] = CS_OPCODE_STR
    return int.from_bytes(b, "little")


def cs_stm32(address: int, src: int, offset: int = 0) -> int:
    raw = CS_OPCODE_STM << 56
    raw |= (src & 0xFF) << 48
    raw |= (address & 0xFF) << 40
    raw |= 1 << 16
    raw |= offset & 0xFFFF
    return raw


def cs_evadd32(addr_reg: int, src_reg: int, offset: int = 0, flags: int = EVADD_FLAG_NO_IRQ) -> int:
    raw = CS_OPCODE_EVADD32 << 56
    raw |= (src_reg & 0xFF) << 48
    raw |= (addr_reg & 0xFF) << 40
    raw |= (flags & 0xFF) << 32
    raw |= offset & 0xFFFF
    return raw


def cs_flush(
    l2_mode: int = CS_FLUSH_MODE_CLEAN_AND_INVALIDATE,
    lsc_mode: int = CS_FLUSH_MODE_CLEAN_AND_INVALIDATE,
    other_mode: int = CS_FLUSH_MODE_INVALIDATE,
    wait_mask: int = 0,
    flush_id: int = 0,
    signal_slot: int = 1,
) -> int:
    raw = CS_OPCODE_FLUSH_CACHE << 56
    raw |= (signal_slot & 0xF) << 48
    raw |= (flush_id & 0xFF) << 40
    raw |= (wait_mask & 0xFFFF) << 16
    raw |= (other_mode & 0xF) << 8
    raw |= (lsc_mode & 0xF) << 4
    raw |= l2_mode & 0xF
    return raw


def pack_cs(instrs: list[int]) -> bytes:
    return b"".join(x.to_bytes(8, "little") for x in instrs)


def build_int_add_cs(*, a_va: int, b_va: int, out_va: int, count: int = 4) -> bytes:
    """CSF stream: out[i] = a[i] + b[i] for count uint32 elements."""
    r_addr_a, r_addr_b, r_addr_o = 0x40, 0x42, 0x44
    r_a, r_b, r_zero = 0x46, 0x48, 0x4A

    instrs: list[int] = [cs_mov32(r_zero, 0)]
    for i in range(count):
        off = i * 4
        instrs += [
            cs_mov48(r_addr_o, out_va + off),
            cs_mov48(r_addr_a, a_va + off),
            cs_ldr32(r_addr_a, r_a, 0),
            cs_wait(1),
            cs_str32(r_addr_o, r_a, 0),
            cs_mov48(r_addr_b, b_va + off),
            cs_ldr32(r_addr_b, r_b, 0),
            cs_wait(1),
            cs_evadd32(r_addr_o, r_b, 0),
        ]
    instrs += [cs_wait(1), cs_flush(flush_id=r_zero), cs_wait(1)]
    return pack_cs(instrs)
