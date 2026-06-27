#!/usr/bin/env python3
"""Vector add on Mali G610 — standalone pure Python (panthor DRM).

Self-contained: Mesa CS/BO payloads as u64 tuples, panthor_drm structs, init/vadd recipe.
Decoded from Mesa/rusticl capture (add_cl2.pcap).

Workload: [1,2,3,4] + [10,20,30,40] -> [11,22,33,44] (uint32)

Regenerate:
  python3 experiemental/tools/panthor_pcap2add.py /tmp/add_cl2.pcap

Reference: allbilly/applegpu experimental/cap2standalone.py
"""
# generated from add_cl2.pcap (2026-06-27 02:44 UTC) — do not edit recipe by hand

from __future__ import annotations

import argparse
import ctypes
import glob
import mmap
import os
import struct
import sys
import time
from dataclasses import dataclass, field

# ── DRM panthor ioctl request codes (kernel ABI) ───────────────────
class NR:
    SYNCOBJ_CREATE          = 0xBF
    SYNCOBJ_DESTROY         = 0xC0
    SYNCOBJ_FD_TO_HANDLE    = 0xC2
    SYNCOBJ_WAIT            = 0xC3
    SYNCOBJ_TIMELINE_WAIT   = 0xCA
    SYNCOBJ_TRANSFER        = 0xCC
    DEV_QUERY               = 0x40
    VM_CREATE               = 0x41
    VM_BIND                 = 0x43
    VM_DESTROY              = 0x44
    BO_CREATE               = 0x45
    BO_MMAP                 = 0x46
    GROUP_CREATE            = 0x47
    GROUP_DESTROY           = 0x48
    GROUP_SUBMIT            = 0x49
    TILER_HEAP_CREATE       = 0x4B
    BO_SET_LABEL            = 0x4D
# ── Mesa-driver magic constants (descriptor format v1) ───────────
class MesaConst:
    """Mesa/rusticl descriptor-format magic values (named for clarity)."""
    PIPELINE_FLAGS    = 0x0000001F00000000   # pipeline A/B control word
    PIPELINE_CAPS     = 0x0000000006A99901   # pipeline capability bitmask
    SCRATCH_VA        = 0x7FFFFFFB0000       # scratch BO VA (MESA_VA_B - 0x1000)
    BIND_TABLE_HDR    = 0x0000100080020018   # binding table entry header


# ── Syncobj / flag masks ───────────────────────────────────────────
class FlagVal:
    """Bit flags used in syncobj descriptors and queue submit args."""
    SYNC_OBJ_HANDLE    = 0x80000000          # timeline-sync point (vs binary)
    SYNC_OBJ_FOREVER   = 0x7FFFFFFFFFFFFFFF  # infinite-wait sentinel


# ── Runtime syncobj values ────────────────────────────────────────
class SyncVal:
    """Syncobj wait-target values from the Mesa/rusticl runtime."""
    INIT_POINT  = 0x0000000000000001  # initial sync point (slot 1)
    NONE        = 0x0000000000000000  # zero padding in syncobj structs


INPUT_A = (1, 2, 3, 4)
INPUT_B = (10, 20, 30, 40)

MESA_VADD_CS_VA = 0x7FFFFFFB2000
MESA_VA_A = 0x7FFFFFFCA000
MESA_VA_B = 0x7FFFFFFB1000
MESA_BO_BA000_VA = 0x7FFFFFFBA000
MESA_BO_FFFFC000_VA = 0x7FFFFFFFC000
MESA_BO_FFFFD000_VA = 0x7FFFFFFFD000

# ── Mesa BO payloads (builders, no hex blobs) ─────────────────────

def _pack_u64s(words: tuple[int, ...]) -> bytes:
    return b"".join(w.to_bytes(8, "little") for w in words)

def exec_ptr(base: int, offset: int, flags: int = 0) -> int:
    """Compute a Mesa exec descriptor pointer (base + offset) with optional flags."""
    return base + offset + flags


class Op:
    """Valhall ALU.u32 op encoding (byte6, opcode2)."""
    IADD = (0xA8, 0x0)   # signed 32-bit integer add
    IMUL = (0xA0, 0xA)   # signed 32-bit integer multiply


def alu32(op: tuple, *, dest: int, src0: int, src1: int) -> int:
    """Pack `dest = src0 OP src1` for a Valhall ALU.u32 instruction."""
    byte6, opcode2 = op
    return (
        (dest       & 0xff)        |
        ((src0      & 0xff) <<  8) |
        ((opcode2   & 0xf ) << 16) |
        ((src1      & 0xff) << 40) |
        (byte6 << 48)
    )


class ExecFlags:
    """High-bit flags OR'd into Mesa BO descriptor pointers."""
    DEFAULT  = 0
    MUL_FLAG = 1 << 56   # set for vmul kernels; absent for vadd


# ── Captured Valhall compute shader binary ────────────────────────
class Insn:
    """Captured Valhall shader qwords — Mesa-compiled add kernel binary."""
    SHADER_A_HDR       = 0x00a0c000000a8081
    SHADER_A_S0        = 0x00a8c0000000407c
    SHADER_A_S1        = 0x00a8c00000008940
    SHADER_A_S2        = 0x00f0c10480c08800
    BRANCH_A_VAL       = 0x501fc03000001641
    SHADER_A_LDVAR0    = 0x00b4c10119c0c800
    SHADER_A_LDVAR1    = 0x00b4c00019c0cf40
    SHADER_A_S3        = 0x00a8c20000000182
    SHADER_A_S4        = 0x00a8c30000000083
    SHADER_A_BR0       = 0x00f0c40400c08202
    SHADER_A_S5        = 0x00a8c30000004344
    STORE_A_PREFIX     = 0x0060828218000042
    SHADER_A_S6        = 0x00a8c30000000184
    SHADER_A_S7        = 0x00a8c40000000085
    SHADER_A_BR1       = 0x00f0c50400c08403
    SHADER_A_S8        = 0x00a8c40000004445
    CNOP_A0            = 0x0091c60000000043
    CNOP_A1            = 0x0891c70000000044
    STORE_A_SUFFIX     = 0x1060838258000046
    SHADER_A_S9        = 0x00a8c10000004186
    SHADER_A_S10       = 0x00a8c00000004087
    SHADER_A_BR2       = 0x00f0c30400c08601
    SHADER_A_S11       = 0x00a8c00000004043
    CNOP_A2            = 0x0091c40000000041
    CNOP_A3            = 0x0091c50000000040
    BRANCH_END_A_VAL   = 0x5061420298000044
    NOP_A_VAL          = 0x7800c00000000000
    SHADER_B_HDR       = 0x00f0c00480c0863c
    SHADER_B_S16       = 0x501fc03000001440
    SHADER_B_S17       = 0x00b4c00119c0c83c
    SHADER_B_S18       = 0x00b4c10019c0cf7c
    SHADER_B_S19       = 0x00a8c20000000080
    SHADER_B_S20       = 0x00a8c30000000181
    SHADER_B_BR0       = 0x00f0c40400c08002
    SHADER_B_S21       = 0x00a8c30000004344
    STORE_B_PREFIX     = 0x0060828218000042
    SHADER_B_S22       = 0x00a8c30000000082
    SHADER_B_S23       = 0x00a8c40000000183
    SHADER_B_BR1       = 0x00f0c50400c08203
    SHADER_B_S24       = 0x00a8c40000004445
    CNOP_B0            = 0x0091c60000000043
    CNOP_B1            = 0x0891c70000000044
    STORE_B_SUFFIX     = 0x1060838258000046
    SHADER_B_S25       = 0x00a8c00000004084
    SHADER_B_S26       = 0x00a8c10000004185
    SHADER_B_S27       = 0x00f0c30400c08400
    SHADER_B_S28       = 0x00a8c10000004143
    BRANCH_END_B_VAL   = 0x5061420298000040
    NOP_B_VAL          = 0x7800c00000000000


class Reg:
    # ── Mesa compute pipeline descriptor (MESA_BO_FFFBA000) ──
    PIPELINE_FLAGS_A = 0x100
    PIPELINE_FLAGS_B = 0x1C0
    PIPELINE_CAPS    = 0x120
    VA_A_PTR         = 0x180
    VA_B_PTR         = 0x188
    SCRATCH_VA       = 0x190
    WORK_DIM         = 0x198
    EXEC_PTR_HI      = 0x200
    EXEC_SIZE        = 0x208
    EXEC_PTR_LO      = 0x230
    EXEC_SIZE_LO     = 0x238

    # ── Valhall compute shader program (MESA_BO_FFFFC000) ──
    ARITH_WARP_A     = 0x098
    ARITH_WARP_B     = 0x180

    # Scaffolding slots — listed by offset so builder reads top-to-bottom
    HDR0, S0, S1, S2      = 0x000, 0x008, 0x010, 0x018
    BRANCH_A              = 0x020
    LDVAR_A0, LDVAR_A1    = 0x028, 0x030
    S3, S4                = 0x038, 0x040
    BR_A0                 = 0x048
    S5                    = 0x050
    STORE_A0              = 0x058
    S6, S7                = 0x060, 0x068
    BR_A1                 = 0x070
    S8                    = 0x078
    CNOP0, CNOP1          = 0x080, 0x088
    STORE_A1              = 0x090
    S9, S10               = 0x0A0, 0x0A8
    BR_A2                 = 0x0B0
    S11                   = 0x0B8
    CNOP2, CNOP3          = 0x0C0, 0x0C8
    BRANCH_END_A          = 0x0D0
    NOP_A                 = 0x0D8

    HDR1, S16, S17, S18   = 0x100, 0x108, 0x110, 0x118
    S19, S20              = 0x120, 0x128
    BR_B0                 = 0x130
    S21                   = 0x138
    STORE_B0              = 0x140
    S22, S23              = 0x148, 0x150
    BR_B1                 = 0x158
    S24                   = 0x160
    CNOP4, CNOP5          = 0x168, 0x170
    STORE_B1              = 0x178
    S25, S26, S27         = 0x188, 0x190, 0x198
    S28                   = 0x1A0
    BRANCH_END_B          = 0x1A8
    NOP_B                 = 0x1B0

    # ── Mesa binding table (MESA_BO_FFFFD000) ──
    BIND_HDR0   = 0x00
    BIND_VA0    = 0x08
    BIND_HDR1   = 0x20
    BIND_VA1    = 0x28


def build_mesa_bo_ba000() -> bytes:
    """Mesa compute pipeline/exec descriptors for BO @ MESA_BO_BA000_VA (handle 19).

    Capture had 576 nonzero-prefix bytes in a 64KiB BO; only 11 qwords matter.
  A/B VAs and in-BO pointers are wired for the vadd kernel."""
    buf = bytearray(576)

    def q(off: int, val: int) -> None:
        struct.pack_into("<Q", buf, off, val)

    q(Reg.PIPELINE_FLAGS_A, MesaConst.PIPELINE_FLAGS)
    q(Reg.PIPELINE_CAPS,    MesaConst.PIPELINE_CAPS)
    q(Reg.VA_A_PTR,         MESA_VA_A)
    q(Reg.VA_B_PTR,         MESA_VA_B)
    q(Reg.SCRATCH_VA,       MesaConst.SCRATCH_VA)  # scratch BO (handle 22)
    q(Reg.WORK_DIM,         4)
    q(Reg.PIPELINE_FLAGS_B, MesaConst.PIPELINE_FLAGS)
    q(Reg.EXEC_PTR_HI,      exec_ptr(MESA_BO_BA000_VA, 0x140, ExecFlags.DEFAULT))
    q(Reg.EXEC_SIZE,        0x20)
    q(Reg.EXEC_PTR_LO,      exec_ptr(MESA_BO_BA000_VA, 0x120, ExecFlags.DEFAULT))
    q(Reg.EXEC_SIZE_LO,     0x20)
    return bytes(buf)


MESA_BO_FFFBA000 = build_mesa_bo_ba000()

def build_mesa_bo_fc000() -> bytes:
    """Mesa pipeline/init descriptor table @ MESA_BO_FFFFC000_VA (440B prefix).

    Two parallel warps execute the same Valhall kernel:
      - warp A spans offsets 0x00..0xD8
      - warp B spans offsets 0x100..0x1B8
    Each warp does: load kernel args, load A[i] and B[i], ALU, store OUT[i].
    """
    buf = bytearray(440)

    def q(off: int, val: int) -> None:
        struct.pack_into("<Q", buf, off, val)

    # ── Warp A program ──────────────────────────────────────────────
    q(Reg.HDR0,       Insn.SHADER_A_HDR)
    q(Reg.S0,         Insn.SHADER_A_S0)
    q(Reg.S1,         Insn.SHADER_A_S1)
    q(Reg.S2,         Insn.SHADER_A_S2)
    q(Reg.BRANCH_A,   Insn.BRANCH_A_VAL)
    q(Reg.LDVAR_A0,   Insn.SHADER_A_LDVAR0)
    q(Reg.LDVAR_A1,   Insn.SHADER_A_LDVAR1)
    q(Reg.S3,         Insn.SHADER_A_S3)
    q(Reg.S4,         Insn.SHADER_A_S4)
    q(Reg.BR_A0,      Insn.SHADER_A_BR0)
    q(Reg.S5,         Insn.SHADER_B_S21)
    q(Reg.STORE_A0,   Insn.STORE_A_PREFIX)
    q(Reg.S6,         Insn.SHADER_A_S6)
    q(Reg.S7,         Insn.SHADER_A_S7)
    q(Reg.BR_A1,      Insn.SHADER_A_BR1)
    q(Reg.S8,         Insn.SHADER_B_S24)
    q(Reg.CNOP0,      Insn.CNOP_B0)
    q(Reg.CNOP1,      Insn.CNOP_B1)
    q(Reg.STORE_A1,   Insn.STORE_A_SUFFIX)
    q(Reg.ARITH_WARP_A, alu32(Op.IADD, dest=0x42, src0=0x43, src1=0xC2))   # vadd: W42 = W43 + Wc2
    q(Reg.S9,         Insn.SHADER_A_S9)
    q(Reg.S10,        Insn.SHADER_A_S10)
    q(Reg.BR_A2,      Insn.SHADER_A_BR2)
    q(Reg.S11,        Insn.SHADER_A_S11)
    q(Reg.CNOP2,      Insn.CNOP_A2)
    q(Reg.CNOP3,      Insn.CNOP_A3)
    q(Reg.BRANCH_END_A, Insn.BRANCH_END_A_VAL)
    q(Reg.NOP_A,      Insn.NOP_A_VAL)

    # ── Warp B program (same shape as warp A, different register IDs) ──
    q(Reg.HDR1,       Insn.SHADER_B_HDR)
    q(Reg.S16,        Insn.SHADER_B_S16)
    q(Reg.S17,        Insn.SHADER_B_S17)
    q(Reg.S18,        Insn.SHADER_B_S18)
    q(Reg.S19,        Insn.SHADER_B_S19)
    q(Reg.S20,        Insn.SHADER_B_S20)
    q(Reg.BR_B0,      Insn.SHADER_B_BR0)
    q(Reg.S21,        Insn.SHADER_B_S21)
    q(Reg.STORE_B0,   Insn.STORE_A_PREFIX)
    q(Reg.S22,        Insn.SHADER_B_S22)
    q(Reg.S23,        Insn.SHADER_B_S23)
    q(Reg.BR_B1,      Insn.SHADER_B_BR1)
    q(Reg.S24,        Insn.SHADER_B_S24)
    q(Reg.CNOP4,      Insn.CNOP_B0)
    q(Reg.CNOP5,      Insn.CNOP_B1)
    q(Reg.STORE_B1,   Insn.STORE_A_SUFFIX)
    q(Reg.ARITH_WARP_B, alu32(Op.IADD, dest=0x42, src0=0x43, src1=0xC2))   # vadd: W42 = W43 + Wc2
    q(Reg.S25,        Insn.SHADER_B_S25)
    q(Reg.S26,        Insn.SHADER_B_S26)
    q(Reg.S27,        Insn.SHADER_B_S27)
    q(Reg.S28,        Insn.SHADER_B_S28)
    q(Reg.BRANCH_END_B, Insn.BRANCH_END_B_VAL)
    q(Reg.NOP_B,      Insn.NOP_A_VAL)
    return bytes(buf)

MESA_BO_FFFFC000 = build_mesa_bo_fc000()

def build_mesa_bo_fd000() -> bytes:
    """Mesa pipeline binding table @ MESA_BO_FFFFD000_VA (points at fc000 BO)."""
    buf = bytearray(48)

    def q(off: int, val: int) -> None:
        struct.pack_into("<Q", buf, off, val)

    hdr = MesaConst.BIND_TABLE_HDR

    q(Reg.BIND_HDR0, hdr)
    q(Reg.BIND_VA0,  MESA_BO_FFFFC000_VA)
    q(Reg.BIND_HDR1, hdr)
    q(Reg.BIND_VA1,  MESA_BO_FFFFC000_VA + 0x100)
    return bytes(buf)


MESA_BO_FFFFD000 = build_mesa_bo_fd000()

def _cs_mov48(dst: int, imm: int) -> int:
    b = bytearray(8)
    b[0] = dst & 0xFF
    b[1:7] = (imm & ((1 << 48) - 1)).to_bytes(6, "little")
    b[7] = 0x01
    return int.from_bytes(b, "little")


def _cs_mov32_word(dst: int, imm: int, tag: int) -> int:
    """Mesa CSF mov32: dst@b[0], imm@b[1:5], tag@b[6] (capture layout)."""
    b = bytearray(8)
    b[0] = dst & 0xFF
    struct.pack_into("<I", b, 1, imm & 0xFFFFFFFF)
    b[6] = tag & 0xFF
    b[7] = 0x02
    return int.from_bytes(b, "little")


def _cs_endpt(mask: int) -> int:
    b = bytearray(8)
    b[0] = mask & 0xFF
    b[7] = 0x22
    return int.from_bytes(b, "little")


def _cs_slot(slot: int) -> int:
    b = bytearray(8)
    b[0] = slot & 0xFF
    b[7] = 0x17
    return int.from_bytes(b, "little")

def _cs_run_compute() -> int:
    """CSF RUN_COMPUTE instruction (dispatch the compute program)."""
    return 0x01 | (0x04 << 56)


def _cs_wait(slot_mask: int) -> int:
    """CSF WAIT instruction (block until all slots in mask are done)."""
    return (slot_mask << 32) | (0x03 << 56)


def _cs_mov_flush_id() -> int:
    """CSF instruction that writes 0 to the W4A (flush_id) register."""
    return 0x4A | (0x4A << 40) | (0x02 << 56)


def _cs_flush_signal() -> int:
    """CSF FLUSH_CACHES + SIGNAL_AND_WAIT instruction."""
    return 0x11 | (0x02 << 8) | (0x24 << 56)


def build_mesa_vadd_cs() -> bytes:
    """Mesa compute dispatch CSF stream (160B) for GROUP_SUBMIT @ MESA_VADD_CS_VA."""
    def q(words: list[int]) -> bytes:
        return b"".join(w.to_bytes(8, "little") for w in words)

    return q([
        _cs_endpt(0x0F),
        _cs_slot(2),
        _cs_mov48(0x08, 0x7FFFFFFBA2),       # pipeline/exec ptr (BO ba000)
        _cs_mov32_word(0x80, 0xFFFBA1, 0x08),
        _cs_mov32_word(0xFF, 0x4007F, 0x09),
        _cs_mov48(0x20, 0x107FFFFFFFD0),     # binding table @ fd000
        _cs_mov48(0xC0, 0x187FFFFFFBA1),     # in-BO descriptor
        _cs_mov32_word(0x00, 0, 0x20),
        _cs_mov32_word(0x03, 0x800000, 0x21),
        _cs_mov32_word(0x00, 0, 0x22),
        _cs_mov32_word(0x00, 0, 0x23),
        _cs_mov32_word(0x00, 0, 0x24),
        _cs_mov32_word(0x01, 0, 0x25),
        _cs_mov32_word(0x01, 0, 0x26),
        _cs_mov32_word(0x01, 0, 0x27),
        _cs_run_compute(),                   # dispatch the compute program
        _cs_wait(slot_mask=0xFF),            # wait for all 8 scoreboard slots
        _cs_mov_flush_id(),                  # zero the flush_id reg
        _cs_flush_signal(),                  # flush + signal completion
        _cs_wait(slot_mask=0x01),            # wait for progress signal
    ])


MESA_VADD_CS = build_mesa_vadd_cs()

# ── panthor_drm struct codecs ─────────────────────────────────────

@dataclass
class VmCreateIn:
    flags: int = 0
    user_va_range: int = 0

    def pack(self) -> bytes:
        buf = bytearray(16)
        struct.pack_into("<I", buf, 0, self.flags)
        struct.pack_into("<Q", buf, 8, self.user_va_range)
        return bytes(buf)


@dataclass
class VmCreateOut:
    id: int = 0
    user_va_range: int = 0

    def pack(self) -> bytes:
        buf = bytearray(16)
        struct.pack_into("<I", buf, 4, self.id)
        struct.pack_into("<Q", buf, 8, self.user_va_range)
        return bytes(buf)


@dataclass
class VmBindOp:
    """drm_panthor_vm_bind_op (48 bytes)."""

    flags: int = 0
    bo_handle: int = 0
    bo_offset: int = 0
    va: int = 0
    size: int = 0
    syncs_stride: int = 0
    syncs_count: int = 0
    syncs_ptr: int = 0

    def pack(self) -> bytes:
        buf = bytearray(48)
        struct.pack_into("<I", buf, 0, self.flags)
        struct.pack_into("<I", buf, 4, self.bo_handle)
        struct.pack_into("<Q", buf, 8, self.bo_offset)
        struct.pack_into("<Q", buf, 16, self.va)
        struct.pack_into("<Q", buf, 24, self.size)
        struct.pack_into("<I", buf, 32, self.syncs_stride)
        struct.pack_into("<I", buf, 36, self.syncs_count)
        struct.pack_into("<Q", buf, 40, self.syncs_ptr)
        return bytes(buf)


@dataclass
class VmBindIn:
    vm_id: int = 0
    flags: int = 0
    ops_stride: int = 0
    ops_count: int = 0
    ops_ptr: int = 0

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<I", buf, 0, self.vm_id)
        struct.pack_into("<I", buf, 4, self.flags)
        struct.pack_into("<I", buf, 8, self.ops_stride)
        struct.pack_into("<I", buf, 12, self.ops_count)
        struct.pack_into("<Q", buf, 16, self.ops_ptr)
        return bytes(buf)


@dataclass
class BoCreateIn:
    size: int = 0
    flags: int = 0
    exclusive_vm_id: int = 0

    def pack(self) -> bytes:
        return struct.pack(
            "<QIIII", self.size, self.flags, self.exclusive_vm_id, 0, 0
        )


@dataclass
class BoCreateOut:
    size: int = 0
    flags: int = 0
    exclusive_vm_id: int = 0
    handle: int = 0

    def pack(self) -> bytes:
        return struct.pack("<QIII", self.size, self.flags, self.exclusive_vm_id, self.handle)


@dataclass
class BoMmapIn:
    handle: int = 0

    def pack(self) -> bytes:
        return struct.pack("<IIQ", self.handle, 0, 0)


@dataclass
class BoMmapOut:
    handle: int = 0
    offset: int = 0

    def pack(self) -> bytes:
        return struct.pack("<IQ", self.handle, self.offset)


@dataclass
class QueueSubmit:
    """drm_panthor_queue_submit sidecar (40 bytes)."""

    queue_index: int = 0
    stream_size: int = 0
    stream_addr: int = 0
    latest_flush: int = 0
    syncs_stride: int = 0
    syncs_count: int = 0
    syncs_ptr: int = 0

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into("<I", buf, 0, self.queue_index)
        struct.pack_into("<I", buf, 4, self.stream_size)
        struct.pack_into("<Q", buf, 8, self.stream_addr)
        struct.pack_into("<I", buf, 16, self.latest_flush)
        struct.pack_into("<I", buf, 24, self.syncs_stride)
        struct.pack_into("<I", buf, 28, self.syncs_count)
        struct.pack_into("<Q", buf, 32, self.syncs_ptr)
        return bytes(buf)


@dataclass
class SyncOp:
    """drm_panthor_sync_op (16 bytes)."""

    flags: int = 0
    handle: int = 0
    timeline_value: int = 0

    def pack(self) -> bytes:
        return struct.pack("<IIQ", self.flags, self.handle, self.timeline_value)


@dataclass
class VmBindOut:
    vm_id: int = 0
    flags: int = 0
    ops_stride: int = 0
    ops_count: int = 0

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<IIII", buf, 0, self.vm_id, self.flags, self.ops_stride, self.ops_count)
        return bytes(buf)


@dataclass
class GroupCreateIn:
    qs_stride: int = 8
    qs_count: int = 1
    qs_ptr: int = 0
    max_compute_cores: int = 0
    max_fragment_cores: int = 0
    max_tiler_cores: int = 0
    priority: int = 0
    compute_core_mask: int = 0
    fragment_core_mask: int = 0
    tiler_core_mask: int = 0
    vm_id: int = 0

    def pack(self) -> bytes:
        buf = bytearray(56)
        struct.pack_into("<II", buf, 0, self.qs_stride, self.qs_count)
        struct.pack_into("<Q", buf, 8, self.qs_ptr)
        buf[16] = self.max_compute_cores
        buf[17] = self.max_fragment_cores
        buf[18] = self.max_tiler_cores
        buf[19] = self.priority
        struct.pack_into("<Q", buf, 24, self.compute_core_mask)
        struct.pack_into("<Q", buf, 32, self.fragment_core_mask)
        struct.pack_into("<Q", buf, 40, self.tiler_core_mask)
        struct.pack_into("<I", buf, 48, self.vm_id)
        return bytes(buf)


@dataclass
class GroupCreateOut(GroupCreateIn):
    group_handle: int = 0

    def pack(self) -> bytes:
        buf = bytearray(GroupCreateIn.pack(self))
        struct.pack_into("<I", buf, 52, self.group_handle)
        return bytes(buf)


@dataclass
class GroupSubmitIn:
    group_handle: int = 0
    qs_stride: int = 0
    qs_count: int = 0
    qs_ptr: int = 0

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<I", buf, 0, self.group_handle)
        struct.pack_into("<I", buf, 8, self.qs_stride)
        struct.pack_into("<I", buf, 12, self.qs_count)
        struct.pack_into("<Q", buf, 16, self.qs_ptr)
        return bytes(buf)


@dataclass
class TilerHeapCreateIn:
    vm_id: int = 0
    initial_chunk_count: int = 0
    chunk_size: int = 0
    max_chunks: int = 0
    target_in_flight: int = 0

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into(
            "<IIIII",
            buf,
            0,
            self.vm_id,
            self.initial_chunk_count,
            self.chunk_size,
            self.max_chunks,
            self.target_in_flight,
        )
        struct.pack_into("<I", buf, 20, 0)
        struct.pack_into("<Q", buf, 24, 0)
        struct.pack_into("<Q", buf, 32, 0)
        return bytes(buf)


@dataclass
class TilerHeapCreateOut(TilerHeapCreateIn):
    handle: int = 0
    tiler_heap_ctx_gpu_va: int = 0
    first_heap_chunk_gpu_va: int = 0

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into(
            "<IIIII",
            buf,
            0,
            self.vm_id,
            self.initial_chunk_count,
            self.chunk_size,
            self.max_chunks,
            self.target_in_flight,
        )
        struct.pack_into("<I", buf, 20, self.handle)
        struct.pack_into("<Q", buf, 24, self.tiler_heap_ctx_gpu_va)
        struct.pack_into("<Q", buf, 32, self.first_heap_chunk_gpu_va)
        return bytes(buf)


@dataclass
class SyncobjCreateIn:
    handle: int = 0
    flags: int = 0

    def pack(self) -> bytes:
        return struct.pack("<II", self.handle, self.flags)


@dataclass
class SyncobjCreateOut(SyncobjCreateIn):
    pass


@dataclass
class SyncobjTransferIn:
    src_handle: int = 0
    dst_handle: int = 0
    src_point: int = 0
    dst_point: int = 0
    flags: int = 0

    def pack(self) -> bytes:
        return struct.pack("<IIQQI", self.src_handle, self.dst_handle,
                           self.src_point, self.dst_point, self.flags) + b"\x00" * 4


@dataclass
class SyncobjTimelineWaitIn:
    handles_ptr: int = 0
    points_ptr: int = 0
    timeout_nsec: int = -1
    count_handles: int = 0
    flags: int = 0

    def pack(self) -> bytes:
        buf = bytearray(48)
        struct.pack_into("<Q", buf, 0, self.handles_ptr)
        struct.pack_into("<Q", buf, 8, self.points_ptr)
        struct.pack_into("<q", buf, 16, self.timeout_nsec)
        struct.pack_into("<I", buf, 24, self.count_handles)
        struct.pack_into("<I", buf, 28, self.flags)
        return bytes(buf)


@dataclass
class GroupQueueCreate:
    """drm_panthor_queue_create sidecar (8 bytes)."""

    priority: int = 0
    ringbuf_size: int = 0

    def pack(self) -> bytes:
        buf = bytearray(8)
        buf[0] = self.priority & 0xFF
        struct.pack_into("<I", buf, 4, self.ringbuf_size)
        return bytes(buf)


# ── recipe + replay ───────────────────────────────────────────────


PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8

IOCTL_NAMES = {
    65: "VM_CREATE", 67: "VM_BIND", 69: "BO_CREATE", 70: "BO_MMAP",
    71: "GROUP_CREATE", 73: "GROUP_SUBMIT", 75: "TILER_HEAP_CREATE",
    191: "SYNCOBJ_CREATE", 195: "SYNCOBJ_WAIT", 202: "SYNCOBJ_TIMELINE_WAIT",
    204: "SYNCOBJ_TRANSFER",
}


def _ioctl_name(nr: int) -> str:
    return IOCTL_NAMES.get(nr, f"0x{nr:02x}")


@dataclass
class IoctlStep:
    nr: int
    request: int
    arg: object | None = None
    arg_raw: bytes | None = None
    cap_out: object | None = None
    cap_out_raw: bytes | None = None
    sides: list[tuple[int, object]] = field(default_factory=list)


@dataclass
class GemU32s:
    cap_handle: int
    gpu_va: int
    values: str


@dataclass
class GemConst:
    cap_handle: int
    gpu_va: int
    bo_offset: int
    blob: str


RecipeStep = GemU32s | GemConst | IoctlStep


def _pack_side(kind: int, obj: object) -> bytes:
    if isinstance(obj, tuple):
        if kind == PANT_SIDE_SYNCOBJ_HANDLES:
            return b"".join(struct.pack("<I", h) for h in obj)
        if kind == PANT_SIDE_SYNCOBJ_POINTS:
            return b"".join(struct.pack("<Q", p) for p in obj)
        raise ValueError(f"unexpected tuple side kind {kind}")
    return obj.pack()


def _ioctl_arg_bytes(step: IoctlStep) -> bytes:
    if step.arg_raw is not None:
        return step.arg_raw
    if step.arg is not None and hasattr(step.arg, "pack"):
        return step.arg.pack()
    raise ValueError(f"{_ioctl_name(step.nr)} missing arg")


def _ioctl_cap_out_bytes(step: IoctlStep) -> bytes:
    if step.cap_out_raw is not None:
        return step.cap_out_raw
    if step.cap_out is not None and hasattr(step.cap_out, "pack"):
        return step.cap_out.pack()
    return b""


def steps_to_tuples(steps: list[RecipeStep], *, inputs: dict[str, tuple[int, ...]]) -> list[tuple]:
    g = globals()
    tuples: list[tuple] = []
    for step in steps:
        if isinstance(step, GemU32s):
            vals = inputs[step.values]
            tuples.append(
                ("gem", step.cap_handle, step.gpu_va, 0, struct.pack(f"<{len(vals)}I", *vals))
            )
        elif isinstance(step, GemConst):
            tuples.append(("gem", step.cap_handle, step.gpu_va, step.bo_offset, g[step.blob]))
        elif isinstance(step, IoctlStep):
            for sk, obj in step.sides:
                tuples.append(("side", sk, _pack_side(sk, obj)))
            tuples.append(
                ("ioctl", step.request, 0, _ioctl_arg_bytes(step), _ioctl_cap_out_bytes(step))
            )
    return tuples


def mesa_vadd(
    input_a: tuple[int, ...],
    input_b: tuple[int, ...],
    *,
    verbose: bool = False,
) -> int:
    steps = [*MESA_INIT_STEPS, *VADD_STEPS]
    inputs = {"INPUT_A": input_a, "INPUT_B": input_b}
    return replay_events(steps_to_tuples(steps, inputs=inputs), verbose=verbose)


MESA_INIT_STEPS: list[RecipeStep] = [
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=1, flags=1),
    ),
    # VM_CREATE
    IoctlStep(nr=NR.VM_CREATE, request=0xc0106441,
        arg=VmCreateIn(user_va_range=0x800000000000),
        cap_out=VmCreateOut(id=1, user_va_range=0x800000000000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=1),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=1, va=0x7FFFFFFFF000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=1),
        cap_out=BoMmapOut(handle=1, offset=0x1000B0000),
    ),
    # 0x0c
    IoctlStep(nr=NR.DEV_QUERY, request=0xc010640c,
        arg_raw=_pack_u64s((0x0000000000000005, 0x0000000000000000)),
        cap_out_raw=_pack_u64s((0x0000000000000005, 0x0000000000000003)),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=2),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=2, va=0x7FFFFFFFE000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=2),
        cap_out=BoMmapOut(handle=2, offset=0x1000B1000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=2, flags=1),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=3),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=3, va=0x7FFFFFFFD000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=3),
        cap_out=BoMmapOut(handle=3, offset=0x1000B2000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=4),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=4, va=0x7FFFFFFFC000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=4),
        cap_out=BoMmapOut(handle=4, offset=0x1000B3000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=3),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=16384, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=16384, exclusive_vm_id=1, handle=5),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=5, va=0x7FFFFFFF8000, size=16384, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=5),
        cap_out=BoMmapOut(handle=5, offset=0x1000B4000),
    ),
    # GROUP_CREATE
    IoctlStep(nr=NR.GROUP_CREATE, request=0xc0386447,
        arg=GroupCreateIn(qs_stride=8, qs_count=1, max_compute_cores=4, max_fragment_cores=4, max_tiler_cores=1, priority=1, compute_core_mask=0x50005, fragment_core_mask=0x50005, tiler_core_mask=1, vm_id=1),
        cap_out=GroupCreateOut(qs_stride=8, qs_count=1, max_compute_cores=4, max_fragment_cores=4, max_tiler_cores=1, priority=1, compute_core_mask=0x50005, fragment_core_mask=0x50005, tiler_core_mask=1, vm_id=1, group_handle=1),
        sides=[
            (PANT_SIDE_GROUP_QUEUES, GroupQueueCreate(priority=1, ringbuf_size=0x10000)),
        ],
    ),
    # TILER_HEAP_CREATE
    IoctlStep(nr=NR.TILER_HEAP_CREATE, request=0xc028644b,
        arg=TilerHeapCreateIn(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535),
        cap_out=TilerHeapCreateOut(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535, handle=0xA00000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=6),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=6, va=0x7FFFFFFF7000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=6),
        cap_out=BoMmapOut(handle=6, offset=0x100ADF000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, flags=1, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, flags=1, exclusive_vm_id=1, handle=7),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=7, va=0x7FFFFFFE7000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=8),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=8, va=0x7FFFFFFE6000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=8),
        cap_out=BoMmapOut(handle=8, offset=0x100AF0000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=9),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=9, va=0x7FFFFFFE5000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=9),
        cap_out=BoMmapOut(handle=9, offset=0x100AF1000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=10),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=10, va=0x7FFFFFFE4000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=10),
        cap_out=BoMmapOut(handle=10, offset=0x100AF2000),
    ),
    # GROUP_SUBMIT
    IoctlStep(nr=NR.GROUP_SUBMIT, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=1, qs_stride=40, qs_count=1),
        cap_out_raw=_pack_u64s((SyncVal.INIT_POINT, 0x0000000100000028, 0x0000fffffe049c68)),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=40, stream_addr=0x7FFFFFFE6000, latest_flush=0xFFFFE0, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=FlagVal.SYNC_OBJ_HANDLE, handle=2)),
        ],
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x00000000290f26c0, FlagVal.SYNC_OBJ_FOREVER, 0x0000000000000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x00000000290f26c0, FlagVal.SYNC_OBJ_FOREVER, 0x0000000000000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (2,)),
        ],
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=4, flags=1),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=8),
        cap_out=BoMmapOut(handle=8, offset=0x100AF0000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=11),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=11, va=0x7FFFFFFE3000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=11),
        cap_out=BoMmapOut(handle=11, offset=0x100AF3000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=5),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=16384, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=16384, exclusive_vm_id=1, handle=12),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=12, va=0x7FFFFFFDF000, size=16384, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=12),
        cap_out=BoMmapOut(handle=12, offset=0x100AF4000),
    ),
    # GROUP_CREATE
    IoctlStep(nr=NR.GROUP_CREATE, request=0xc0386447,
        arg=GroupCreateIn(qs_stride=8, qs_count=1, max_compute_cores=4, max_fragment_cores=4, max_tiler_cores=1, priority=1, compute_core_mask=0x50005, fragment_core_mask=0x50005, tiler_core_mask=1, vm_id=1),
        cap_out=GroupCreateOut(qs_stride=8, qs_count=1, max_compute_cores=4, max_fragment_cores=4, max_tiler_cores=1, priority=1, compute_core_mask=0x50005, fragment_core_mask=0x50005, tiler_core_mask=1, vm_id=1, group_handle=2),
        sides=[
            (PANT_SIDE_GROUP_QUEUES, GroupQueueCreate(priority=1, ringbuf_size=0x10000)),
        ],
    ),
    # TILER_HEAP_CREATE
    IoctlStep(nr=NR.TILER_HEAP_CREATE, request=0xc028644b,
        arg=TilerHeapCreateIn(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535),
        cap_out=TilerHeapCreateOut(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535, handle=0x1400000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=13),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=13, va=0x7FFFFFFDE000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=13),
        cap_out=BoMmapOut(handle=13, offset=0x10151D000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, flags=1, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, flags=1, exclusive_vm_id=1, handle=14),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=14, va=0x7FFFFFFCE000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=15),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=15, va=0x7FFFFFFCD000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=15),
        cap_out=BoMmapOut(handle=15, offset=0x10152E000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=16),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=16, va=0x7FFFFFFCC000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=16),
        cap_out=BoMmapOut(handle=16, offset=0x10152F000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=17),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=17, va=0x7FFFFFFCB000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=17),
        cap_out=BoMmapOut(handle=17, offset=0x101530000),
    ),
    # GROUP_SUBMIT
    IoctlStep(nr=NR.GROUP_SUBMIT, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=2, qs_stride=40, qs_count=1),
        cap_out_raw=_pack_u64s((0x0000000000000002, 0x0000000100000028, 0x0000fffffe04c338)),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=40, stream_addr=0x7FFFFFFCD000, latest_flush=1, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=FlagVal.SYNC_OBJ_HANDLE, handle=4)),
        ],
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x000000002c7662c0, FlagVal.SYNC_OBJ_FOREVER, 0x0000000000000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x000000002c7662c0, FlagVal.SYNC_OBJ_FOREVER, 0x0000000000000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (4,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=18),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=18, va=0x7FFFFFFCA000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=18),
        cap_out=BoMmapOut(handle=18, offset=0x101531000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, exclusive_vm_id=1, handle=19),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=19, va=0x7FFFFFFBA000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=32768, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=32768, exclusive_vm_id=1, handle=20),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=20, va=0x7FFFFFFB2000, size=32768, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=NR.SYNCOBJ_FD_TO_HANDLE, request=0xc01864c1,
        arg_raw=_pack_u64s((0x0000000100000002, 0x00000000ffffffff, 0x0000000000000000)),
        cap_out_raw=_pack_u64s((0x0000000100000002, 0x0000000000000006, 0x0000000000000000)),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x0000000028eb51f4, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x0000000028eb51f4, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=21),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=21, va=0x7FFFFFFB1000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=21),
        cap_out=BoMmapOut(handle=21, offset=0x10154A000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=NR.SYNCOBJ_FD_TO_HANDLE, request=0xc01864c1,
        arg_raw=_pack_u64s((0x0000000100000002, 0x00000000ffffffff, 0x0000000000000000)),
        cap_out_raw=_pack_u64s((0x0000000100000002, 0x0000000000000006, 0x0000000000000000)),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x0000000028eb51f4, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x0000000028eb51f4, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=22),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=22, va=0x7FFFFFFB0000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
]

VADD_STEPS: list[RecipeStep] = [
    GemConst(cap_handle=0x3, gpu_va=0x7fffffffd000, bo_offset=0, blob="MESA_BO_FFFFD000"),
    GemConst(cap_handle=0x4, gpu_va=0x7fffffffc000, bo_offset=0, blob="MESA_BO_FFFFC000"),
    GemU32s(cap_handle=0x12, gpu_va=0x7ffffffca000, values="INPUT_A"),
    GemConst(cap_handle=0x13, gpu_va=0x7ffffffba000, bo_offset=0, blob="MESA_BO_FFFBA000"),
    GemConst(cap_handle=0x14, gpu_va=0x7ffffffb2000, bo_offset=0, blob="MESA_VADD_CS"),
    GemU32s(cap_handle=0x15, gpu_va=0x7ffffffb1000, values="INPUT_B"),
    # GROUP_SUBMIT
    IoctlStep(nr=NR.GROUP_SUBMIT, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=2, qs_stride=40, qs_count=1),
        cap_out_raw=_pack_u64s((0x0000000000000002, 0x0000000100000028, 0x0000ffffa85dbed0)),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=160, stream_addr=0x7FFFFFFB2000, latest_flush=0xFFFFE0, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=FlagVal.SYNC_OBJ_HANDLE | 0x01, handle=1, timeline_value=1)),
        ],
    ),
    # SYNCOBJ_TRANSFER
    IoctlStep(nr=NR.SYNCOBJ_TRANSFER, request=0xc02064cc,
        arg=SyncobjTransferIn(src_handle=1, dst_handle=4, src_point=1),
        cap_out_raw=_pack_u64s((0x0000000400000001, 0x0000000000000001, SyncVal.NONE, SyncVal.NONE)),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=NR.SYNCOBJ_TIMELINE_WAIT, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD139F9B, count_handles=1, flags=1),
        cap_out_raw=_pack_u64s((0x000000002900e728, 0x0000ffffa85dc968, 0x000acd2dbd139f9b, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=NR.BO_CREATE, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, exclusive_vm_id=1, handle=23),
    ),
    # VM_BIND
    IoctlStep(nr=NR.VM_BIND, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out=VmBindOut(vm_id=1, ops_stride=48, ops_count=1),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=23, va=0x7FFFFFFA0000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=23),
        cap_out=BoMmapOut(handle=23, offset=0x10154C000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=NR.SYNCOBJ_TIMELINE_WAIT, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD17104A, count_handles=1, flags=1),
        cap_out_raw=_pack_u64s((0x000000002900e7d8, 0x0000ffffa85dc858, 0x000acd2dbd17104a, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=NR.SYNCOBJ_TIMELINE_WAIT, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD186CEB, count_handles=1, flags=1),
        cap_out_raw=_pack_u64s((0x000000002900e728, 0x0000ffffa85ddcb8, 0x000acd2dbd186ceb, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=NR.SYNCOBJ_FD_TO_HANDLE, request=0xc01864c1,
        arg_raw=_pack_u64s((0x0000000100000004, 0x00000000ffffffff, 0x0000000000000000)),
        cap_out_raw=_pack_u64s((0x0000000100000004, 0x0000000000000006, 0x0000000000000000)),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x00000000290d4114, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x00000000290d4114, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=22),
        cap_out=BoMmapOut(handle=22, offset=0x10154B000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=NR.SYNCOBJ_TIMELINE_WAIT, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=FlagVal.SYNC_OBJ_FOREVER, count_handles=1, flags=1),
        cap_out_raw=_pack_u64s((0x000000002900f6a8, 0x0000ffffa85dd7c8, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=23),
        cap_out=BoMmapOut(handle=23, offset=0x10154C000),
    ),
    # BO_MMAP
    IoctlStep(nr=NR.BO_MMAP, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=NR.SYNCOBJ_FD_TO_HANDLE, request=0xc01864c1,
        arg_raw=_pack_u64s((0x0000000100000004, 0x00000000ffffffff, 0x0000000000000000)),
        cap_out_raw=_pack_u64s((0x0000000100000004, 0x0000000000000006, 0x0000000000000000)),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=NR.SYNCOBJ_CREATE, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=NR.SYNCOBJ_WAIT, request=0xc02864c3,
        arg_raw=_pack_u64s((0x00000000290b0b04, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        cap_out_raw=_pack_u64s((0x00000000290b0b04, FlagVal.SYNC_OBJ_FOREVER, 0x0000000100000001, SyncVal.NONE, SyncVal.NONE)),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
]

# ── replay engine ─────────────────────────────────────────────────

from pathlib import Path

DRM_BASE = 0x40
Req_DEV_QUERY = DRM_BASE + 0
Req_VM_CREATE = DRM_BASE + 1
Req_VM_BIND = DRM_BASE + 3
Req_BO_CREATE = DRM_BASE + 5
Req_BO_MMAP = DRM_BASE + 6
Req_GROUP_CREATE = DRM_BASE + 7
Req_GROUP_SUBMIT = DRM_BASE + 9
Req_TILER_HEAP_CREATE = DRM_BASE + 11
Req_BO_SET_LABEL = DRM_BASE + 13
Req_SYNCOBJ_CREATE = 0xBF
Req_SYNCOBJ_WAIT = 0xC3
Req_SYNCOBJ_FD_TO_HANDLE = 0xC2
Req_SYNCOBJ_TIMELINE_WAIT = 0xCA
SKIP_IOCTLS = {Req_BO_SET_LABEL, Req_SYNCOBJ_FD_TO_HANDLE, NR.SYNCOBJ_DESTROY}
_PAGE = 4096
_FLUSH_MMIO_OFF = (1 << 56) if ctypes.sizeof(ctypes.c_void_p) >= 8 else (1 << 43)
EXPECTED = (11, 22, 33, 44)


def _read_flush_id(fd: int) -> int:
    mm = mmap.mmap(fd, _PAGE, mmap.MAP_SHARED, mmap.PROT_READ, offset=_FLUSH_MMIO_OFF)
    try:
        return int.from_bytes(mm[:4], "little")
    finally:
        mm.close()


def find_render() -> str:
    for path in sorted(glob.glob("/dev/dri/renderD*")):
        try:
            fd = os.open(path, os.O_RDWR)
            os.close(fd)
            return path
        except OSError:
            continue
    raise RuntimeError("no render node")


def _ioctl(fd: int, req: int, buf: ctypes.Array | ctypes.Structure) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
    libc.ioctl.restype = ctypes.c_int
    arg = ctypes.byref(buf) if isinstance(buf, ctypes.Structure) else buf
    rc = libc.ioctl(fd, req, arg)
    if rc < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), hex(req))
    return rc


_VM_BIND_OP_STRIDE = 48
_SYNC_OP_STRIDE = 16


def _map_handle(hmap: dict[int, int], handle: int) -> int:
    return hmap.get(handle, handle)


def _patch_u32(buf: bytearray, off: int, hmap: dict[int, int]) -> None:
    if off + 4 > len(buf):
        return
    val = struct.unpack_from("<I", buf, off)[0]
    if val in hmap:
        struct.pack_into("<I", buf, off, hmap[val])


def _patch_vm_bind_ops(buf: bytearray, hmap: dict[int, int]) -> None:
    for off in range(0, len(buf) - _VM_BIND_OP_STRIDE + 1, _VM_BIND_OP_STRIDE):
        _patch_u32(buf, off + 4, hmap)


def _patch_sync_ops(buf: bytearray, hmap: dict[int, int]) -> None:
    for off in range(0, len(buf) - _SYNC_OP_STRIDE + 1, _SYNC_OP_STRIDE):
        _patch_u32(buf, off + 4, hmap)


def _patch_syncobj_handles(buf: bytearray, hmap: dict[int, int]) -> None:
    for off in range(0, len(buf) - 3, 4):
        _patch_u32(buf, off, hmap)


def _patch_ioctl_arg(nr: int, buf: bytearray, hmap: dict[int, int]) -> None:
    if nr == Req_VM_BIND:
        _patch_u32(buf, 0, hmap)
    elif nr == Req_BO_MMAP:
        _patch_u32(buf, 0, hmap)
    elif nr == Req_GROUP_SUBMIT:
        _patch_u32(buf, 0, hmap)
    elif nr == Req_GROUP_CREATE and len(buf) >= 44:
        _patch_u32(buf, 40, hmap)  # vm_id
    elif nr == Req_TILER_HEAP_CREATE:
        _patch_u32(buf, 0, hmap)  # vm_id
        _patch_u32(buf, 4, hmap)  # heap handle (input)
    elif nr == NR.SYNCOBJ_TRANSFER:
        _patch_u32(buf, 0, hmap)
        _patch_u32(buf, 4, hmap)
    elif nr in (NR.SYNCOBJ_DESTROY, NR.SYNCOBJ_FD_TO_HANDLE):
        _patch_u32(buf, 0, hmap)
    elif nr == Req_BO_CREATE and len(buf) >= 20:
        _patch_u32(buf, 16, hmap)  # handle extension / import


def _learn(nr: int, cap_out: bytes, live: bytes, hmap: dict[int, int]) -> None:
    pairs: list[tuple[int, int]] = []
    if nr == Req_BO_CREATE and len(cap_out) >= 20:
        pairs.append((struct.unpack_from("<I", cap_out, 16)[0], struct.unpack_from("<I", live, 16)[0]))
    elif nr == Req_VM_CREATE and len(cap_out) >= 8:
        pairs.append((struct.unpack_from("<I", cap_out, 4)[0], struct.unpack_from("<I", live, 4)[0]))
    elif nr == Req_GROUP_CREATE and len(cap_out) >= 48:
        pairs.append((struct.unpack_from("<I", cap_out, 44)[0], struct.unpack_from("<I", live, 44)[0]))
    elif nr == Req_SYNCOBJ_CREATE and len(cap_out) >= 4:
        pairs.append((struct.unpack_from("<I", cap_out, 0)[0], struct.unpack_from("<I", live, 0)[0]))
    elif nr == Req_TILER_HEAP_CREATE and len(cap_out) >= 36:
        pairs.append((struct.unpack_from("<I", cap_out, 32)[0], struct.unpack_from("<I", live, 32)[0]))
    for old, new in pairs:
        if old and new:
            hmap[old] = new


def _dma_sync(dmabuf_fd: int, flags: int) -> None:
    _DMA_BUF_IOCTL_SYNC = (1 << 30) | (8 << 16) | (ord("b") << 8) | 0

    class DmaBufSync(ctypes.Structure):
        _fields_ = [("flags", ctypes.c_uint64)]

    libc = ctypes.CDLL(None, use_errno=True)
    libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
    libc.ioctl.restype = ctypes.c_int
    if libc.ioctl(dmabuf_fd, _DMA_BUF_IOCTL_SYNC, ctypes.byref(DmaBufSync(flags=flags))) < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()), "DMA_BUF_IOCTL_SYNC")


def _prime_dma_sync(render_fd: int, handle: int, *, write: bool = False) -> None:
    _IO_PRIME = (3 << 30) | (16 << 16) | (ord("d") << 8) | 0x2D
    _DMA_START = 1 << 0
    _DMA_END = 1 << 1
    _DMA_WRITE = 1 << 2

    class PrimeHandle(ctypes.Structure):
        _fields_ = [
            ("handle", ctypes.c_uint32),
            ("flags", ctypes.c_uint32),
            ("fd", ctypes.c_int32),
            ("pad", ctypes.c_uint32),
        ]

    prime = PrimeHandle(handle=handle, flags=0)
    _ioctl(render_fd, _IO_PRIME, prime)
    try:
        flags = _DMA_START | _DMA_END
        if write:
            flags |= _DMA_WRITE
        _dma_sync(prime.fd, flags)
    finally:
        os.close(prime.fd)


def _sync_mapped_bos(render_fd: int, mmaps: dict[int, mmap.mmap], hmap: dict[int, int], *, write: bool) -> None:
    for cap in (0x11, 0x12, 0x14, 0x15):
        live = _map_handle(hmap, cap)
        if live in mmaps:
            try:
                _prime_dma_sync(render_fd, live, write=write)
            except OSError:
                pass


def _bo_sync(fd: int, handle: int, size: int) -> None:
    """CPU cache invalidate after GPU write."""
    _IO_BO_SYNC = (3 << 30) | (16 << 16) | (ord("d") << 8) | (DRM_BASE + 15)

    class ObjArray(ctypes.Structure):
        _fields_ = [("stride", ctypes.c_uint32), ("count", ctypes.c_uint32), ("array", ctypes.c_uint64)]

    class BoSyncOp(ctypes.Structure):
        _fields_ = [
            ("handle", ctypes.c_uint32),
            ("type", ctypes.c_uint32),
            ("offset", ctypes.c_uint64),
            ("size", ctypes.c_uint64),
        ]

    class BoSync(ctypes.Structure):
        _fields_ = [("ops", ObjArray)]

    op = BoSyncOp(handle=handle, type=0, offset=0, size=size)
    sync = BoSync(ops=ObjArray(stride=ctypes.sizeof(BoSyncOp), count=1, array=ctypes.addressof(op)))
    _ioctl(fd, _IO_BO_SYNC, sync)


def _wait_syncobj(fd: int, handle: int, *, timeout: int = -1, flags: int = 0) -> None:
    _IO_C3 = 0xC02864C3

    class SyncobjWait(ctypes.Structure):
        _fields_ = [
            ("handles", ctypes.c_uint64),
            ("timeout_nsec", ctypes.c_int64),
            ("count_handles", ctypes.c_uint32),
            ("flags", ctypes.c_uint32),
            ("first_signaled", ctypes.c_uint32),
            ("pad", ctypes.c_uint32),
            ("deadline_nsec", ctypes.c_uint64),
        ]

    arr = (ctypes.c_uint32 * 1)(handle)
    w = SyncobjWait(
        handles=ctypes.addressof(arr),
        timeout_nsec=timeout,
        count_handles=1,
        flags=flags,
    )
    _ioctl(fd, _IO_C3, w)


def _wait_timeline_syncobj(
    fd: int, handle: int, point: int, *, timeout: int = -1, flags: int = 0
) -> None:
    _IO_CA = 0xC03064CA

    class TimelineWait(ctypes.Structure):
        _fields_ = [
            ("handles", ctypes.c_uint64),
            ("points", ctypes.c_uint64),
            ("timeout_nsec", ctypes.c_int64),
            ("count_handles", ctypes.c_uint32),
            ("flags", ctypes.c_uint32),
            ("first_signaled", ctypes.c_uint32),
            ("pad", ctypes.c_uint32),
            ("deadline_nsec", ctypes.c_uint64),
        ]

    handles = (ctypes.c_uint32 * 1)(handle)
    points = (ctypes.c_uint64 * 1)(point)
    w = TimelineWait(
        handles=ctypes.addressof(handles),
        points=ctypes.addressof(points),
        timeout_nsec=timeout,
        count_handles=1,
        flags=flags,
    )
    _ioctl(fd, _IO_CA, w)


def _drain_output(fd: int, mmaps: dict[int, mmap.mmap], hmap: dict[int, int]) -> int | None:
    out_h = _map_handle(hmap, 0x11)
    if out_h in mmaps:
        try:
            _bo_sync(fd, out_h, len(mmaps[out_h]))
            _prime_dma_sync(fd, out_h, write=False)
        except OSError:
            pass
    got = _scan_expected(mmaps)
    if got is not None:
        print(f"out={list(got)}")
        print(f"expected={list(EXPECTED)}")
        if got == EXPECTED:
            print("PASS")
            return 0
    return None


def _scan_expected(mmaps: dict[int, mmap.mmap]) -> tuple[int, ...] | None:
    pat = struct.pack("<4i", *EXPECTED)
    for mm in mmaps.values():
        off = mm.find(pat)
        if off >= 0:
            return tuple(struct.unpack_from("<4i", mm, off))
    return None


def replay_events(events: list[tuple], *, verbose: bool = False) -> int:
    path = find_render()
    fd = os.open(path, os.O_RDWR)
    if verbose:
        print(f"render: {path}")

    hmap: dict[int, int] = {}
    bo_size: dict[int, int] = {}
    mmaps: dict[int, mmap.mmap] = {}
    pending: list[tuple[int, bytes]] = []
    keep: list[ctypes.Array] = []
    idx = 0

    for item in events:
        kind = item[0]
        if kind == "side":
            pending.append((item[1], item[2]))
            continue

        if kind == "gem":
            _, handle, _gpu_va, bo_off, data = item
            handle = hmap.get(handle, handle)
            mm = mmaps.get(handle)
            if mm is not None:
                n = min(len(data), len(mm) - bo_off)
                if n > 0:
                    mm[bo_off : bo_off + n] = data[:n]
            idx += 1
            continue

        _, req, cap_ret, arg_in, cap_out = item
        if (req & 0xFF) in SKIP_IOCTLS:
            idx += 1
            continue

        arg = bytearray(arg_in)
        nr = req & 0xFF
        _patch_ioctl_arg(nr, arg, hmap)

        sides: list[tuple[int, ctypes.Array]] = []
        bind_sync: list[ctypes.Array] = []
        while pending:
            sk, data = pending.pop(0)
            sb = (ctypes.c_uint8 * len(data)).from_buffer_copy(data)
            sb_view = bytearray(sb)
            if sk == PANT_SIDE_VM_BIND_OPS:
                _patch_vm_bind_ops(sb_view, hmap)
            elif sk in (PANT_SIDE_SYNC_OPS, PANT_SIDE_BIND_SYNC_OPS):
                _patch_sync_ops(sb_view, hmap)
            elif sk == PANT_SIDE_SYNCOBJ_HANDLES:
                _patch_syncobj_handles(sb_view, hmap)
            for i, b in enumerate(sb_view):
                sb[i] = b
            if sk == PANT_SIDE_BIND_SYNC_OPS:
                bind_sync.append(sb)
            else:
                sides.append((sk, sb))
            keep.append(sb)

        if nr == Req_DEV_QUERY and sides:
            struct.pack_into("<Q", arg, 8, ctypes.addressof(sides[0][1]))
        elif nr == Req_VM_BIND and sides:
            struct.pack_into("<Q", arg, 16, ctypes.addressof(sides[0][1]))
            if bind_sync:
                struct.pack_into("<Q", sides[0][1], 40, ctypes.addressof(bind_sync[0]))
        elif nr == Req_GROUP_CREATE and sides:
            struct.pack_into("<Q", arg, 8, ctypes.addressof(sides[0][1]))
        elif nr == Req_GROUP_SUBMIT:
            qs = next((sb for k, sb in sides if k == PANT_SIDE_QUEUE_SUBMITS), None)
            if qs is not None:
                struct.pack_into("<Q", arg, 16, ctypes.addressof(qs))
                struct.pack_into("<I", qs, 16, _read_flush_id(fd))
                sync = next((sb for k, sb in sides if k == PANT_SIDE_SYNC_OPS), None)
                if sync is not None:
                    struct.pack_into("<Q", qs, 32, ctypes.addressof(sync))
                if struct.unpack_from("<I", qs, 4)[0] == 160:
                    _sync_mapped_bos(fd, mmaps, hmap, write=True)
        elif nr == Req_SYNCOBJ_WAIT:
            for sk, sb in sides:
                if sk == PANT_SIDE_SYNCOBJ_HANDLES:
                    hb = bytearray(sb)
                    _patch_syncobj_handles(hb, hmap)
                    for i, b in enumerate(hb):
                        sb[i] = b
                    struct.pack_into("<Q", arg, 0, ctypes.addressof(sb))
                    break
        elif nr == Req_SYNCOBJ_TIMELINE_WAIT:
            handles_sb = next((sb for k, sb in sides if k == PANT_SIDE_SYNCOBJ_HANDLES), None)
            points_sb = next((sb for k, sb in sides if k == PANT_SIDE_SYNCOBJ_POINTS), None)
            if handles_sb is None:
                if verbose:
                    print(f"[{idx}] ioctl 0x{req:08x} skipped (no timeline sidecar)")
                idx += 1
                continue
            hb = bytearray(handles_sb)
            _patch_syncobj_handles(hb, hmap)
            for i, b in enumerate(hb):
                handles_sb[i] = b
            struct.pack_into("<Q", arg, 0, ctypes.addressof(handles_sb))
            if points_sb is not None:
                struct.pack_into("<Q", arg, 8, ctypes.addressof(points_sb))

        buf = (ctypes.c_uint8 * len(arg)).from_buffer_copy(bytes(arg))
        try:
            ret = _ioctl(fd, req, buf)
        except OSError as exc:
            if (req & 0xFF) in (Req_SYNCOBJ_WAIT, Req_SYNCOBJ_TIMELINE_WAIT) and exc.errno in (22, 62):
                if verbose:
                    print(f"[{idx}] ioctl 0x{req:08x} wait skipped ({exc})")
                idx += 1
                continue
            raise
        live = bytes(buf)
        _learn(nr, cap_out, live, hmap)

        if nr == 0xCC and len(arg_in) >= 24:
            _src = hmap.get(struct.unpack_from("<I", arg_in, 0)[0], struct.unpack_from("<I", arg_in, 0)[0])
            _dst = hmap.get(struct.unpack_from("<I", arg_in, 4)[0], struct.unpack_from("<I", arg_in, 4)[0])
            _dst_point = struct.unpack_from("<Q", arg_in, 16)[0]
            try:
                _wait_timeline_syncobj(fd, _dst, _dst_point)
            except OSError:
                try:
                    _wait_syncobj(fd, _dst)
                except OSError:
                    pass
            for _ in range(200):
                rc = _drain_output(fd, mmaps, hmap)
                if rc == 0:
                    return 0
                time.sleep(0.01)

        if nr == Req_GROUP_SUBMIT:
            sync = next((sb for k, sb in sides if k == PANT_SIDE_SYNC_OPS), None)
            if sync is not None and len(sync) >= 16:
                flags, sig_handle = struct.unpack_from("<II", sync, 0)
                sig_handle = hmap.get(sig_handle, sig_handle)
                if flags & 0x80000000:
                    point = struct.unpack_from("<Q", sync, 8)[0]
                    try:
                        _wait_timeline_syncobj(fd, sig_handle, point)
                    except OSError:
                        pass
                elif flags & 1:
                    try:
                        _wait_syncobj(fd, sig_handle, flags=flags & 1)
                    except OSError:
                        pass
            rc = _drain_output(fd, mmaps, hmap)
            if rc == 0:
                return 0

        if nr == Req_BO_CREATE and len(live) >= 20:
            handle = struct.unpack_from("<I", live, 16)[0]
            bo_size[handle] = struct.unpack_from("<Q", live, 0)[0]

        if nr == Req_BO_MMAP and len(live) >= 16:
            handle = struct.unpack_from("<I", live, 0)[0]
            offset = struct.unpack_from("<Q", live, 8)[0]
            size = bo_size.get(handle, 4096)
            map_sz = (size + 4095) & ~4095
            mmaps[handle] = mmap.mmap(
                fd, map_sz, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset
            )

        if nr == Req_SYNCOBJ_WAIT or nr == Req_SYNCOBJ_TIMELINE_WAIT:
            rc = _drain_output(fd, mmaps, hmap)
            if rc == 0:
                return 0
            out_h = hmap.get(0x11, 0x11)
            if out_h in mmaps and verbose:
                print(f"out_bo handle={out_h} {struct.unpack('<4i', mmaps[out_h][:16])}")

        if verbose:
            print(f"[{idx}] ioctl 0x{req:08x} ret={ret} cap={cap_ret}")
        idx += 1

    print("FAIL: expected output not found in mapped BOs", file=sys.stderr)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.dry_run:
        print(f"init steps: {len(MESA_INIT_STEPS)}  vadd steps: {len(VADD_STEPS)}")
        print(f"A={list(INPUT_A)} B={list(INPUT_B)} expected={list(EXPECTED)}")
        return 0
    try:
        return mesa_vadd(INPUT_A, INPUT_B, verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
