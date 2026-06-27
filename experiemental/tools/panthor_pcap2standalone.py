#!/usr/bin/env python3
"""Generate structured examples/add.py from panthor .pcap (applegpu cap2standalone analogue).

GEM payloads → GemZeros / GemU32s / GemConst(name); ioctl blobs → dataclass fields.
Raw hex only for uncaptured Mesa init BO blobs (module-level named constants).
"""

from __future__ import annotations

import argparse
import re
import sys
import textwrap
from dataclasses import fields, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panthor_cap_decode import (  # noqa: E402
    NR_BO_SET_LABEL,
    NR_GROUP_SUBMIT,
    NR_SYNCOBJ_DESTROY,
    NR_VM_BIND,
    GroupQueueCreate,
    GroupSubmitIn,
    QueueSubmit,
    SyncOp,
    VmBindIn,
    VmBindOp,
    decode_ioctl_in,
    decode_ioctl_out,
    ioctl_name,
    repr_value,
)
from panthor_cap_format import (  # noqa: E402
    PANT_SIDE_BIND_SYNC_OPS,
    PANT_SIDE_GROUP_QUEUES,
    PANT_SIDE_QUEUE_SUBMITS,
    PANT_SIDE_SYNC_OPS,
    PANT_SIDE_SYNCOBJ_HANDLES,
    PANT_SIDE_SYNCOBJ_POINTS,
    PANT_SIDE_VM_BIND_OPS,
    PantEvent,
    PantGem,
    PantIoctl,
    PantSide,
    load_events,
)

SKIP_NRS = {NR_BO_SET_LABEL, NR_SYNCOBJ_DESTROY, 0xC2}

SECTION = {
    NR_VM_BIND: "# ── VM bind ─────────────────────────────────────────────────────",
    NR_GROUP_SUBMIT: "# ── group submit ────────────────────────────────────────────────",
    0xCC: "# ── syncobj transfer / timeline wait ────────────────────────────",
}

INPUT_A_HEAD = bytes((1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 4, 0, 0, 0))
INPUT_B_HEAD = bytes((10, 0, 0, 0, 20, 0, 0, 0, 30, 0, 0, 0, 40, 0, 0, 0))

CS_VA_NAMES = {
    0x7FFFFFFE6000: "MESA_INIT_CS_0",
    0x7FFFFFFCD000: "MESA_INIT_CS_1",
    0x7FFFFFFB2000: "MESA_VADD_CS",
}

CS_SLICE = {
    0x7FFFFFFE6000: 40,
    0x7FFFFFFCD000: 40,
    0x7FFFFFFB2000: 160,
}


def emit_dataclass_init(obj, *, omit_defaults: bool = True) -> str:
    parts = []
    for f in fields(obj):
        val = getattr(obj, f.name)
        if omit_defaults and val in (0, -1, b""):
            continue
        parts.append(f"{f.name}={repr_value(val)}")
    if not parts:
        return f"{type(obj).__name__}()"
    return f"{type(obj).__name__}({', '.join(parts)})"


def _hex_const(name: str, data: bytes) -> str:
    if len(data) <= 64:
        return f"{name} = bytes.fromhex({data.hex()!r})"
    w = 64
    chunks = ",\n    ".join(f'"{data[off : off + w].hex()}"' for off in range(0, len(data), w))
    return f"{name} = bytes.fromhex(\n    ''.join([\n    {chunks},\n    ]),\n)"


def _blob_const_name(gpu_va: int) -> str:
    return f"MESA_BO_{gpu_va & 0xFFFFFFFF:08X}"


def _prepare_ioctl_in(nr: int, arg_in: bytes):
    obj = decode_ioctl_in(nr, arg_in)
    if obj is None:
        return None
    if isinstance(obj, VmBindIn):
        return replace(obj, ops_ptr=0)
    if isinstance(obj, GroupSubmitIn):
        return replace(obj, qs_ptr=0)
    if hasattr(obj, "handles_ptr"):
        return replace(obj, handles_ptr=0, points_ptr=0)
    return obj


def decode_side(kind: int, data: bytes):
    if kind == PANT_SIDE_VM_BIND_OPS:
        op = VmBindOp.from_bytes(data)
        return replace(op, syncs_ptr=0)
    if kind == PANT_SIDE_QUEUE_SUBMITS:
        qs = QueueSubmit.from_bytes(data)
        return replace(qs, syncs_ptr=0)
    if kind == PANT_SIDE_SYNC_OPS or kind == PANT_SIDE_BIND_SYNC_OPS:
        return SyncOp.from_bytes(data)
    if kind == PANT_SIDE_GROUP_QUEUES:
        return GroupQueueCreate.from_bytes(data)
    if kind == PANT_SIDE_SYNCOBJ_HANDLES:
        n = len(data) // 4
        return tuple(int.from_bytes(data[i : i + 4], "little") for i in range(0, n * 4, 4))
    if kind == PANT_SIDE_SYNCOBJ_POINTS:
        n = len(data) // 8
        return tuple(int.from_bytes(data[i : i + 8], "little") for i in range(0, n * 8, 8))
    return None


def emit_side(kind: int, data: bytes) -> str:
    obj = decode_side(kind, data)
    if obj is None:
        return f"({kind}, bytes.fromhex({data.hex()!r}))"
    if isinstance(obj, tuple):
        return f"({kind}, {obj!r})"
    return f"({kind}, {emit_dataclass_init(obj)})"


class OpCollector:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.constants: dict[str, bytes] = {}
        self.seen_gems: set[tuple[int, int, bytes]] = set()
        self.current_section = ""
        self.idx = 0

    def _maybe_section(self, section: str) -> None:
        if section and section != self.current_section:
            self.lines.append(section)
            self.lines.append("")
            self.current_section = section

    def _register_const(self, name: str, data: bytes) -> str:
        self.constants.setdefault(name, data)
        return name

    def _classify_gem(self, ev: PantGem) -> str:
        data = bytes(ev.data)
        if not any(data):
            return (
                f"GemZeros(  # {self.idx}\n"
                f"    handle=0x{ev.handle:x},\n"
                f"    gpu_va=0x{ev.gpu_va:x},\n"
                f"    size={len(data)},\n"
                f"),"
            )
        if data[:16] == INPUT_A_HEAD:
            return (
                f"GemU32s(  # {self.idx}  input A\n"
                f"    handle=0x{ev.handle:x},\n"
                f"    gpu_va=0x{ev.gpu_va:x},\n"
                f"    values=\"INPUT_A\",\n"
                f"),"
            )
        if data[:16] == INPUT_B_HEAD:
            return (
                f"GemU32s(  # {self.idx}  input B\n"
                f"    handle=0x{ev.handle:x},\n"
                f"    gpu_va=0x{ev.gpu_va:x},\n"
                f"    values=\"INPUT_B\",\n"
                f"),"
            )
        if ev.gpu_va in CS_VA_NAMES:
            name = self._register_const(CS_VA_NAMES[ev.gpu_va], data[: CS_SLICE[ev.gpu_va]])
            return (
                f"GemConst(  # {self.idx}  {name}\n"
                f"    handle=0x{ev.handle:x},\n"
                f"    gpu_va=0x{ev.gpu_va:x},\n"
                f"    bo_offset={ev.bo_offset},\n"
                f"    blob=\"{name}\",\n"
                f"),"
            )
        name = self._register_const(_blob_const_name(ev.gpu_va), data)
        return (
            f"GemConst(  # {self.idx}  Mesa init BO\n"
            f"    handle=0x{ev.handle:x},\n"
            f"    gpu_va=0x{ev.gpu_va:x},\n"
            f"    bo_offset={ev.bo_offset},\n"
            f"    blob=\"{name}\",\n"
            f"),"
        )

    def add_gem(self, ev: PantGem) -> None:
        data = bytes(ev.data)
        key = (ev.handle, ev.gpu_va, data)
        if key in self.seen_gems:
            return
        self.seen_gems.add(key)
        self._maybe_section("# ── GEM load ────────────────────────────────────────────────────")
        body = self._classify_gem(ev)
        self.lines.append(textwrap.indent(body, "    "))
        self.idx += 1

    def add_ioctl(
        self,
        nr: int,
        req: int,
        arg_in: bytes,
        arg_out: bytes,
        sides: list[tuple[int, bytes]],
    ) -> None:
        self._maybe_section(SECTION.get(nr, ""))
        name = ioctl_name(nr)
        din = _prepare_ioctl_in(nr, arg_in)
        dout = decode_ioctl_out(nr, arg_out)

        lines = [f"IoctlOp(  # {self.idx}: {name}"]
        lines.append(f"    nr={nr!r}, request=0x{req:08x},")
        if din is not None:
            lines.append(f"    arg={emit_dataclass_init(din)},")
        else:
            lines.append(f"    arg_raw=bytes.fromhex({arg_in.hex()!r}),")
        if dout is not None:
            lines.append(f"    cap_out={emit_dataclass_init(dout)},")
        else:
            lines.append(f"    cap_out_raw=bytes.fromhex({arg_out.hex()!r}),")
        if sides:
            lines.append("    sides=[")
            for sk, data in sides:
                lines.append(f"        {emit_side(sk, data)},")
            lines.append("    ],")
        lines.append("),")
        self.lines.append(textwrap.indent("\n".join(lines), "    "))
        self.idx += 1


def collect_ops(events: list[PantEvent]) -> tuple[list[str], dict[str, bytes]]:
    col = OpCollector()
    pending: list[tuple[int, bytes]] = []
    for ev in events:
        if isinstance(ev, PantSide):
            pending.append((ev.kind, ev.data))
            continue
        if isinstance(ev, PantGem):
            col.add_gem(ev)
            continue
        if not isinstance(ev, PantIoctl):
            continue
        nr = ev.request & 0xFF
        if nr in SKIP_NRS:
            continue
        sides = list(pending)
        pending.clear()
        col.add_ioctl(nr, ev.request, ev.arg_in, ev.arg_out, sides)
    return col.lines, col.constants


def struct_source() -> str:
    src = (ROOT / "panthor_cap_decode.py").read_text()
    start = src.find("@dataclass\nclass VmCreateIn")
    end = src.find("\nIOCTL_IN_DECODERS")
    block = src[start:end]
    while True:
        m = re.search(
            r"\n    @classmethod\n    def from_bytes\([\s\S]*?"
            r"(?=\n    def |\n\n@dataclass|\nclass [A-Z]|\Z)",
            block,
        )
        if not m:
            break
        block = block[: m.start()] + block[m.end() :]
    return block.rstrip()


def replay_engine_source() -> str:
    src = (ROOT / "panthor_replay.py").read_text()
    src = re.sub(r"^#!/usr/bin/env python3\n", "", src)
    src = re.sub(r'"""Replay panthor.*?"""\n\n', "", src, flags=re.S)
    src = re.sub(r"from __future__ import annotations\n\n", "", src)
    src = re.sub(r"^import (ctypes|glob|mmap|os|struct|sys|time)\n", "", src, flags=re.M)
    src = re.sub(
        r"def main\(\) -> int:.*?if __name__ == \"__main__\":.*",
        "",
        src,
        flags=re.S,
    )
    return src.strip()


def ops_runtime_source() -> str:
    return '''
PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8


def _pack_side(kind: int, obj) -> bytes:
    if isinstance(obj, tuple):
        if kind == PANT_SIDE_SYNCOBJ_HANDLES:
            return b"".join(struct.pack("<I", h) for h in obj)
        if kind == PANT_SIDE_SYNCOBJ_POINTS:
            return b"".join(struct.pack("<Q", p) for p in obj)
        raise ValueError(f"unexpected tuple side kind {kind}")
    return obj.pack()


@dataclass
class GemZeros:
    handle: int
    gpu_va: int
    size: int


@dataclass
class GemU32s:
    handle: int
    gpu_va: int
    values: str


@dataclass
class GemConst:
    handle: int
    gpu_va: int
    bo_offset: int
    blob: str


@dataclass
class IoctlOp:
    nr: int
    request: int
    arg: object | None = None
    arg_raw: bytes | None = None
    cap_out: object | None = None
    cap_out_raw: bytes | None = None
    sides: list[tuple[int, object]] = field(default_factory=list)


def _ioctl_arg_bytes(op: IoctlOp) -> bytes:
    if op.arg_raw is not None:
        return op.arg_raw
    if op.arg is not None and hasattr(op.arg, "pack"):
        return op.arg.pack()
    raise ValueError(f"IoctlOp {ioctl_name(op.nr)} missing arg")


def _ioctl_cap_out_bytes(op: IoctlOp) -> bytes:
    if op.cap_out_raw is not None:
        return op.cap_out_raw
    if op.cap_out is not None and hasattr(op.cap_out, "pack"):
        return op.cap_out.pack()
    return b""


def ops_to_tuples(ops: list) -> list[tuple]:
    """Convert decoded OPS back to panthor_replay event tuples."""
    tuples: list[tuple] = []
    g = globals()
    for op in ops:
        if isinstance(op, GemZeros):
            tuples.append(("gem", op.handle, op.gpu_va, 0, b"\\x00" * op.size))
        elif isinstance(op, GemU32s):
            vals = g[op.values]
            data = struct.pack(f"<{len(vals)}I", *vals)
            tuples.append(("gem", op.handle, op.gpu_va, 0, data))
        elif isinstance(op, GemConst):
            tuples.append(("gem", op.handle, op.gpu_va, op.bo_offset, g[op.blob]))
        elif isinstance(op, IoctlOp):
            for sk, obj in op.sides:
                tuples.append(("side", sk, _pack_side(sk, obj)))
            tuples.append(
                (
                    "ioctl",
                    op.request,
                    0,
                    _ioctl_arg_bytes(op),
                    _ioctl_cap_out_bytes(op),
                )
            )
    return tuples
'''


def generate(events: list[PantEvent], capture: Path, *, start: int, end: int, output: Path) -> tuple[str, str | None]:
    slice_ev = events[start:end]
    ops_body, constants = collect_ops(slice_ev)
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    blob_import = ""
    blob_block = ""
    blobs_py: str | None = None
    if constants:
        blob_import = f"from {output.stem}_blobs import *  # noqa: F403"
        const_lines = [
            f'"""Mesa BO payloads for {output.name} (generated)."""',
            f"# generated from {capture.name} ({when})",
            "",
        ]
        for name in sorted(constants):
            const_lines.append(_hex_const(name, constants[name]))
            const_lines.append("")
        blobs_py = "\n".join(const_lines).rstrip() + "\n"
    else:
        blob_block = "# (no Mesa init blobs in this slice)"
    main_py = f'''#!/usr/bin/env python3
"""Vector add on Mali G610 — standalone pure Python (panthor DRM).

Structured decode of Mesa/rusticl capture ({capture.name}).
Ioctl blobs are panthor_drm dataclasses; GEM loads use GemZeros/GemU32s/GemConst.

Workload: [1,2,3,4] + [10,20,30,40] -> [11,22,33,44] (uint32)

Regenerate:
  make -C experiemental capture-panthor CAP=/tmp/add_cl2.pcap
  python3 experiemental/tools/panthor_pcap2standalone.py /tmp/add_cl2.pcap

Reference: allbilly/applegpu experimental/cap2standalone.py
"""
# generated from {capture.name} — do not edit OPS by hand ({when})

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

{blob_import}

{blob_block}

# ── panthor_drm struct codecs ─────────────────────────────────────

{struct_source()}

{ops_runtime_source()}

# ── replay engine ─────────────────────────────────────────────────

{replay_engine_source()}

# ── decoded capture ops ───────────────────────────────────────────

OPS = [
{chr(10).join(ops_body)}
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--dry-run", action="store_true", help="list op count only")
    args = p.parse_args()
    if args.dry_run:
        n_ioctl = sum(1 for o in OPS if isinstance(o, IoctlOp))
        n_gem = len(OPS) - n_ioctl
        print(f"{{len(OPS)}} ops ({{n_ioctl}} ioctls, {{n_gem}} gem loads)")
        return 0
    try:
        return replay_events(ops_to_tuples(OPS), verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''
    return main_py, blobs_py


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("examples/add.py"))
    ap.add_argument("--from", dest="start", type=int, default=18)
    ap.add_argument("--until", dest="end", type=int, default=0)
    args = ap.parse_args()

    events = load_events(args.pcap)
    end = args.end or len(events)
    main_py, blobs_py = generate(events, args.pcap, start=args.start, end=end, output=args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(main_py)
    print(f"wrote {args.output} ({len(main_py)} bytes, ops slice [{args.start}:{end}])")
    if blobs_py is not None:
        blobs_path = args.output.with_name(args.output.stem + "_blobs.py")
        blobs_path.write_text(blobs_py)
        print(f"wrote {blobs_path} ({len(blobs_py)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
