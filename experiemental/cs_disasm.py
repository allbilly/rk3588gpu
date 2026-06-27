"""Disassemble Mali CSF (Valhall v10) command stream instructions.

Opcode reference: icecream95.gitlab.io/the-mali-csf-command-stream-instruction-set
Cycles noted for G610 @ 330 MHz on RK3588.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterator

COND_NAMES = {
    0x00: ".LE",
    0x10: ".GT",
    0x20: ".EQ",
    0x30: ".NE",
    0x40: ".LT",
    0x50: ".GE",
    0x60: ".AL",
}


def reg32(n: int) -> str:
    return f"w{n:02x}"


def reg64(n: int) -> str:
    return f"x{n:02x}"


@dataclass
class Insn:
    off: int
    raw: int
    text: str


def _read_u64(data: bytes, off: int) -> int:
    return struct.unpack_from("<Q", data, off)[0]


def disasm_one(data: bytes, off: int) -> Insn:
    if off + 8 > len(data):
        return Insn(off, 0, "<truncated>")
    raw = _read_u64(data, off)
    b = raw.to_bytes(8, "little")
    opc = b[7]

    if raw == 0:
        return Insn(off, raw, "nop")

    if opc == 0x01:
        dst = b[0]
        imm = int.from_bytes(b[1:7], "little")
        return Insn(off, raw, f"mov {reg64(dst)}, #{imm:#x}")

    if opc == 0x02:
        dst = b[0]
        imm, = struct.unpack_from("<I", b, 1)
        return Insn(off, raw, f"mov {reg32(dst)}, #{imm:#x}")

    if opc == 0x03:
        sb = b[0]
        return Insn(off, raw, f"wait {sb}")

    if opc in (0x10, 0x11):
        width = "w" if opc == 0x10 else "x"
        dst = b[0]
        src = b[1]
        simm, = struct.unpack_from("<i", b, 2)
        if simm == 0 and width == "w":
            return Insn(off, raw, f"mov {reg32(dst)}, {reg32(src)}")
        if simm == 0:
            return Insn(off, raw, f"mov {reg64(dst)}, {reg64(src)}")
        rn = reg32 if width == "w" else reg64
        return Insn(off, raw, f"add {rn(dst)}, {rn(src)}, #{simm}")

    if opc in (0x14, 0x15):
        op = "ldr" if opc == 0x14 else "str"
        base = b[0]
        mask, = struct.unpack_from("<H", b, 1)
        simm, = struct.unpack_from("<h", b, 3)
        simm &= ~3
        regs = []
        for i in range(16):
            if mask & (1 << i):
                r = base + i
                regs.append(reg64(r) if r & 1 and opc == 0x14 else reg32(r))
        reglist = "{" + ", ".join(regs) + "}"
        return Insn(off, raw, f"{op} {reglist}, [{reg64(base)}, #{simm}]")

    if opc == 0x16:
        cond = b[1] & 0xF0
        wn = b[1] & 0x0F
        offset, = struct.unpack_from("<h", b, 2)
        off_insn = off + 8 + (struct.unpack("<h", struct.pack("<H", offset))[0] + 1) * 8
        cond_s = COND_NAMES.get(cond, f".unk{cond:#x}")
        if cond == 0x60:
            return Insn(off, raw, f"b {off_insn:#x}")
        dir_s = "skip" if offset >= 0 else "back"
        return Insn(off, raw, f"b{cond_s.lower()} {reg32(wn)}, {dir_s} {abs(offset)}")

    if opc == 0x17:
        slot = b[0]
        return Insn(off, raw, f"slot #{slot}")

    if opc in (0x20, 0x21):
        op = "call" if opc == 0x20 else "tailcall"
        dst = b[0]
        len_reg = b[1]
        return Insn(off, raw, f"{op} {reg32(len_reg)}, {reg64(dst)}")

    if opc == 0x22:
        mask = b[0]
        return Insn(off, raw, f"endpt #{mask:#x}")

    if opc == 0x28:
        typ = "timestamp" if b[0] == 0 else "cycles"
        base = b[1]
        simm, = struct.unpack_from("<h", b, 2)
        simm &= ~7
        return Insn(off, raw, f"str {typ}, [{reg64(base)}, #{simm}]")

    return Insn(off, raw, f"unk {raw:#018x}")


def disasm(data: bytes, start: int = 0, limit: int | None = None) -> list[Insn]:
    out: list[Insn] = []
    off = start
    end = len(data) if limit is None else min(len(data), start + limit)
    while off < end:
        ins = disasm_one(data, off)
        out.append(ins)
        off += 8
    return out


def disasm_ring(data: bytes, max_insns: int = 256) -> Iterator[str]:
    for ins in disasm(data, limit=max_insns * 8):
        yield f"{ins.off:04x}: {ins.text}"
