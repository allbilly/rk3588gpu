#!/usr/bin/env python3
"""Generate self-contained examples/add.py (applegpu cap2standalone style).

Single file: u64 Mesa payloads (no hex blobs), struct codecs, init/vadd recipe, replay.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panthor_cap_format import load_events  # noqa: E402
from tools.panthor_pcap2recipe import (  # noqa: E402
    collect_all_steps,
    split_init_vadd,
)
from tools.panthor_pcap2standalone import (  # noqa: E402
    collect_ops,
    replay_engine_source,
    struct_source,
)

# GEM payloads required for PASS (others are optional Mesa init snapshots).
REQUIRED_BLOBS = frozenset(
    {
        "MESA_BO_FFFBA000",
        "MESA_BO_FFFFC000",
        "MESA_BO_FFFFD000",
        "MESA_VADD_CS",
    }
)


def trim_blob(data: bytes) -> bytes:
    last = max((i for i, b in enumerate(data) if b), default=-1)
    if last < 0:
        return b""
    n = last + 1
    pad = (-n) % 8
    return data[: n + pad]


def emit_mesa_bo_ba000_builder() -> str:
    """Sparse Mesa pipeline table for the 64KiB BO at 0x7ffffffba000 (not a u64 blob)."""
    return '''def build_mesa_bo_ba000() -> bytes:
    """Mesa compute pipeline/exec descriptors for BO @ MESA_BO_BA000_VA (handle 19).

    Capture had 576 nonzero-prefix bytes in a 64KiB BO; only 11 qwords matter.
  A/B VAs and in-BO pointers are wired for the vadd kernel."""
    buf = bytearray(576)

    def q(off: int, val: int) -> None:
        struct.pack_into("<Q", buf, off, val)

    q(0x100, 0x0000001F00000000)
    q(0x120, 0x0000000006A99901)
    q(0x180, MESA_VA_A)
    q(0x188, MESA_VA_B)
    q(0x190, 0x7FFFFFFB0000)  # scratch BO (handle 22)
    q(0x198, 4)
    q(0x1C0, 0x0000001F00000000)
    q(0x200, MESA_BO_BA000_VA + 0x140)
    q(0x208, 0x20)
    q(0x230, MESA_BO_BA000_VA + 0x120)
    q(0x238, 0x20)
    return bytes(buf)


MESA_BO_FFFBA000 = build_mesa_bo_ba000()'''


def emit_sparse_blob_builder(
    name: str,
    data: bytes,
    *,
    fn_name: str,
    doc: str,
) -> str:
    """Emit build_*() that pokes only nonzero qwords (dense Mesa pipeline tables)."""
    data = trim_blob(data)
    size = len(data)
    lines = [
        f"def {fn_name}() -> bytes:",
        f'    """{doc}"""',
        f"    buf = bytearray({size})",
        "",
        "    def q(off: int, val: int) -> None:",
        '        struct.pack_into("<Q", buf, off, val)',
        "",
    ]
    for off in range(0, size, 8):
        val = int.from_bytes(data[off : off + 8], "little")
        if val:
            lines.append(f"    q({off:#x}, {val:#018x})")
    lines.append("    return bytes(buf)")
    lines.append("")
    lines.append(f"{name} = {fn_name}()")
    return "\n".join(lines)


def emit_mesa_bo_fc000_builder(data: bytes) -> str:
    return emit_sparse_blob_builder(
        "MESA_BO_FFFFC000",
        data,
        fn_name="build_mesa_bo_fc000",
        doc="Mesa pipeline/init descriptor table @ MESA_BO_FFFFC000_VA (440B prefix).",
    )


def emit_mesa_bo_fd000_builder() -> str:
    return '''def build_mesa_bo_fd000() -> bytes:
    """Mesa pipeline binding table @ MESA_BO_FFFFD000_VA (points at fc000 BO)."""
    buf = bytearray(48)

    def q(off: int, val: int) -> None:
        struct.pack_into("<Q", buf, off, val)

    hdr = 0x0000100080020018
    q(0x00, hdr)
    q(0x08, MESA_BO_FFFFC000_VA)
    q(0x20, hdr)
    q(0x28, MESA_BO_FFFFC000_VA + 0x100)
    return bytes(buf)


MESA_BO_FFFFD000 = build_mesa_bo_fd000()'''


def emit_mesa_vadd_cs_builder() -> str:
    return '''def _cs_mov48(dst: int, imm: int) -> int:
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
        0x0400000000008001,                  # run compute
        0x0300000000FF0000,                  # wait
        0x024A000000000000,                  # mov w4a, #0 (flush_id reg)
        0x24004A0000000211,                  # flush + signal
        0x0300000000010000,                  # wait (progress)
    ])


MESA_VADD_CS = build_mesa_vadd_cs()'''


def emit_u64_blob(name: str, data: bytes) -> str:
    data = trim_blob(data)
    if not data:
        return f"{name} = b''"
    u64s = [int.from_bytes(data[i : i + 8], "little") for i in range(0, len(data), 8)]
    lines = [f"{name}_U64 = ("]
    for i in range(0, len(u64s), 2):
        chunk = u64s[i : i + 2]
        lines.append("    " + ", ".join(f"{u:#018x}" for u in chunk) + ",")
    lines.append(")")
    lines.append(f"{name} = _pack_u64s({name}_U64)")
    return "\n".join(lines)


def emit_blob(name: str, data: bytes) -> str:
    if name == "MESA_BO_FFFBA000":
        return emit_mesa_bo_ba000_builder()
    if name == "MESA_BO_FFFFC000":
        return emit_mesa_bo_fc000_builder(data)
    if name == "MESA_BO_FFFFD000":
        return emit_mesa_bo_fd000_builder()
    if name == "MESA_VADD_CS":
        return emit_mesa_vadd_cs_builder()
    return emit_u64_blob(name, data)


def slim_recipe_lines(lines: list[str]) -> list[str]:
    """Drop optional GemZeros/GemConst loads; keep INPUT_A/B and required blobs."""
    out: list[str] = []
    for line in lines:
        s = line.strip()
        if s.startswith("GemZeros("):
            continue
        if s.startswith("GemConst("):
            if not any(f'blob="{name}"' in line for name in REQUIRED_BLOBS):
                continue
        out.append(line)
    return out


def mesa_runtime_source() -> str:
    return '''
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
'''


def generate(events, capture: Path, *, start: int, end: int) -> str:
    slice_ev = events[start:end]
    all_lines = collect_all_steps(slice_ev)
    init_lines, vadd_lines = split_init_vadd(all_lines)
    init_lines = slim_recipe_lines(init_lines)
    vadd_lines = slim_recipe_lines(vadd_lines)
    _, constants = collect_ops(slice_ev)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blob_block = "\n\n".join(
        emit_blob(name, constants[name]) for name in sorted(REQUIRED_BLOBS)
    )

    return f'''#!/usr/bin/env python3
"""Vector add on Mali G610 — standalone pure Python (panthor DRM).

Self-contained: Mesa CS/BO payloads as u64 tuples, panthor_drm structs, init/vadd recipe.
Decoded from Mesa/rusticl capture ({capture.name}).

Workload: [1,2,3,4] + [10,20,30,40] -> [11,22,33,44] (uint32)

Regenerate:
  python3 experiemental/tools/panthor_pcap2add.py /tmp/add_cl2.pcap

Reference: allbilly/applegpu experimental/cap2standalone.py
"""
# generated from {capture.name} ({when}) — do not edit recipe by hand

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

INPUT_A = (1, 2, 3, 4)
INPUT_B = (10, 20, 30, 40)
EXPECTED = (11, 22, 33, 44)

MESA_VADD_CS_VA = 0x7FFFFFFB2000
MESA_VA_OUT = 0x7FFFFFFCB000
MESA_VA_A = 0x7FFFFFFCA000
MESA_VA_B = 0x7FFFFFFB1000
MESA_BO_BA000_VA = 0x7FFFFFFBA000
MESA_BO_FFFFC000_VA = 0x7FFFFFFFC000
MESA_BO_FFFFD000_VA = 0x7FFFFFFFD000

# ── Mesa BO payloads (builders, no hex blobs) ─────────────────────

def _pack_u64s(words: tuple[int, ...]) -> bytes:
    return b"".join(w.to_bytes(8, "little") for w in words)

{blob_block}

# ── panthor_drm struct codecs ─────────────────────────────────────

{struct_source()}

# ── recipe + replay ───────────────────────────────────────────────

{mesa_runtime_source()}

MESA_INIT_STEPS: list[RecipeStep] = [
{chr(10).join(init_lines)}
]

VADD_STEPS: list[RecipeStep] = [
{chr(10).join(vadd_lines)}
]

# ── replay engine ─────────────────────────────────────────────────

{replay_engine_source()}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if args.dry_run:
        print(f"init steps: {{len(MESA_INIT_STEPS)}}  vadd steps: {{len(VADD_STEPS)}}")
        print(f"A={{list(INPUT_A)}} B={{list(INPUT_B)}} expected={{list(EXPECTED)}}")
        return 0
    try:
        return mesa_vadd(INPUT_A, INPUT_B, verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("examples/add.py"))
    ap.add_argument("--from", dest="start", type=int, default=18)
    ap.add_argument("--until", dest="end", type=int, default=0)
    args = ap.parse_args()

    events = load_events(args.pcap)
    end = args.end or len(events)
    out = generate(events, args.pcap, start=args.start, end=end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out)
    print(f"wrote {args.output} ({len(out)} bytes, slice [{args.start}:{end}])")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
