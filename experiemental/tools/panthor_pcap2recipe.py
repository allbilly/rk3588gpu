#!/usr/bin/env python3
"""Emit mesa_init_recipe.py from a panthor .pcap (init phase only, before vadd)."""

from __future__ import annotations

import argparse
import sys
from dataclasses import fields, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panthor_cap_decode import QueueSubmit, decode_ioctl_out, ioctl_name, repr_value  # noqa: E402
from panthor_cap_format import PantGem, PantIoctl, PantSide, load_events  # noqa: E402

SKIP_NRS = {0x4D, 0xC0, 0xC2}
NR_GROUP_SUBMIT = 0x49


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


def prepare_ioctl_arg(nr: int, arg_in: bytes):
    from panthor_cap_decode import GroupCreateIn, GroupSubmitIn, SyncobjTimelineWaitIn, VmBindIn, decode_ioctl_in

    obj = decode_ioctl_in(nr, arg_in)
    if obj is None:
        return None
    if isinstance(obj, VmBindIn):
        return replace(obj, ops_ptr=0)
    if isinstance(obj, GroupSubmitIn):
        return replace(obj, qs_ptr=0)
    if isinstance(obj, GroupCreateIn):
        return replace(obj, qs_ptr=0)
    if isinstance(obj, SyncobjTimelineWaitIn):
        return replace(obj, handles_ptr=0, points_ptr=0)
    return obj


def prepare_side(kind: int, data: bytes):
    from panthor_cap_decode import GroupQueueCreate, QueueSubmit, SyncOp, VmBindOp

    if kind == 1:
        return replace(VmBindOp.from_bytes(data), syncs_ptr=0)
    if kind == 2:
        return replace(QueueSubmit.from_bytes(data), syncs_ptr=0)
    if kind in (4, 6):
        return SyncOp.from_bytes(data)
    if kind == 3:
        return GroupQueueCreate.from_bytes(data)
    if kind == 7:
        return tuple(int.from_bytes(data[i : i + 4], "little") for i in range(0, len(data), 4))
    if kind == 8:
        return tuple(int.from_bytes(data[i : i + 8], "little") for i in range(0, len(data), 8))
    return None


def classify_gem(ev: PantGem) -> str:
    data = bytes(ev.data)
    if not any(data):
        return f"GemZeros(cap_handle=0x{ev.handle:x}, gpu_va=0x{ev.gpu_va:x}, size={len(data)})"
    head_a = bytes((1, 0, 0, 0, 2, 0, 0, 0, 3, 0, 0, 0, 4, 0, 0, 0))
    head_b = bytes((10, 0, 0, 0, 20, 0, 0, 0, 30, 0, 0, 0, 40, 0, 0, 0))
    if data[:16] == head_a:
        return f'GemU32s(cap_handle=0x{ev.handle:x}, gpu_va=0x{ev.gpu_va:x}, values="INPUT_A")'
    if data[:16] == head_b:
        return f'GemU32s(cap_handle=0x{ev.handle:x}, gpu_va=0x{ev.gpu_va:x}, values="INPUT_B")'
    cs = {0x7FFFFFFE6000: "MESA_INIT_CS_0", 0x7FFFFFFCD000: "MESA_INIT_CS_1", 0x7FFFFFFB2000: "MESA_VADD_CS"}
    if ev.gpu_va in cs:
        return (
            f"GemConst(cap_handle=0x{ev.handle:x}, gpu_va=0x{ev.gpu_va:x}, "
            f'bo_offset={ev.bo_offset}, blob="{cs[ev.gpu_va]}")'
        )
    name = f"MESA_BO_{ev.gpu_va & 0xFFFFFFFF:08X}"
    return (
        f"GemConst(cap_handle=0x{ev.handle:x}, gpu_va=0x{ev.gpu_va:x}, "
        f"bo_offset={ev.bo_offset}, blob=\"{name}\")"
    )


def emit_side(kind: int, data: bytes) -> str:
    obj = prepare_side(kind, data)
    if obj is None:
        return f"({kind}, bytes.fromhex({data.hex()!r}))"
    if isinstance(obj, tuple):
        kname = "PANT_SIDE_SYNCOBJ_HANDLES" if kind == 7 else "PANT_SIDE_SYNCOBJ_POINTS"
        return f"({kname}, {obj!r})"
    kmap = {
        1: "PANT_SIDE_VM_BIND_OPS",
        2: "PANT_SIDE_QUEUE_SUBMITS",
        3: "PANT_SIDE_GROUP_QUEUES",
        4: "PANT_SIDE_SYNC_OPS",
        6: "PANT_SIDE_BIND_SYNC_OPS",
    }
    return f"({kmap[kind]}, {emit_dataclass_init(obj)})"


def emit_raw_bytes(data: bytes) -> str:
    """Emit small ioctl tail bytes as _pack_u64s (no bytes.fromhex)."""
    if not data:
        return "b''"
    if len(data) <= 8:
        return repr(data)
    pad = (-len(data)) % 8
    padded = data + b"\x00" * pad
    u64s = tuple(int.from_bytes(padded[i : i + 8], "little") for i in range(0, len(padded), 8))
    inner = ", ".join(f"{u:#018x}" for u in u64s)
    return f"_pack_u64s(({inner}))"


def collect_all_steps(events) -> list[str]:
    """One pass; sides may precede ioctl across GEM snapshots (capture order)."""
    lines: list[str] = []
    pending: list[tuple[int, bytes]] = []
    seen_gems: set[tuple[int, int, bytes]] = set()
    for ev in events:
        if isinstance(ev, PantSide):
            pending.append((ev.kind, bytes(ev.data)))
            continue
        if isinstance(ev, PantGem):
            key = (ev.handle, ev.gpu_va, bytes(ev.data))
            if key in seen_gems:
                continue
            seen_gems.add(key)
            lines.append(f"    {classify_gem(ev)},")
            continue
        if not isinstance(ev, PantIoctl):
            continue
        nr = ev.request & 0xFF
        if nr in SKIP_NRS:
            continue
        din = prepare_ioctl_arg(nr, ev.arg_in)
        dout = decode_ioctl_out(nr, ev.arg_out)
        parts = [f"    # {ioctl_name(nr)}"]
        parts.append(f"    IoctlStep(nr={nr!r}, request=0x{ev.request:08x},")
        if din is not None:
            parts.append(f"        arg={emit_dataclass_init(din)},")
        else:
            parts.append(f"        arg_raw={emit_raw_bytes(ev.arg_in)},")
        if dout is not None:
            parts.append(f"        cap_out={emit_dataclass_init(dout)},")
        else:
            parts.append(f"        cap_out_raw={emit_raw_bytes(ev.arg_out)},")
        if pending:
            parts.append("        sides=[")
            for sk, data in pending:
                parts.append(f"            {emit_side(sk, data)},")
            parts.append("        ],")
        parts.append("    ),")
        lines.append("\n".join(parts))
        pending.clear()
    return lines


def split_init_vadd(lines: list[str]) -> tuple[list[str], list[str]]:
    """Split at vadd prelude: reload BOs (fd000/fc000) + inputs + submit."""
    input_a = next(i for i, line in enumerate(lines) if "GemU32s" in line and 'values="INPUT_A"' in line)
    # Two GemConst reload lines immediately before INPUT_A in capture slice.
    start = input_a
    while start > 0 and "GemConst" in lines[start - 1] and "MESA_BO_FFFF" in lines[start - 1]:
        start -= 1
        if lines[start].count("MESA_BO_FFFF") == 0:
            start += 1
            break
    # Keep at most 2 reload lines (fd000/fc000) before INPUT_A.
    if input_a - start > 2:
        start = input_a - 2
    return lines[:start], lines[start:]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("experiemental/mesa_init_recipe.py"))
    ap.add_argument("--from", dest="start", type=int, default=18)
    args = ap.parse_args()

    events = load_events(args.pcap)[args.start :]
    all_lines = collect_all_steps(events)
    init_lines, vadd_lines = split_init_vadd(all_lines)

    out = f'''"""Mesa/rusticl init + vadd recipe from {args.pcap.name} (generated)."""

from __future__ import annotations

from dataclasses import dataclass, field

from panthor_cap_decode import (
    BoCreateIn,
    BoCreateOut,
    BoMmapIn,
    BoMmapOut,
    GroupQueueCreate,
    GroupSubmitIn,
    QueueSubmit,
    SyncOp,
    SyncobjCreateIn,
    SyncobjCreateOut,
    SyncobjTransferIn,
    SyncobjTimelineWaitIn,
    TilerHeapCreateIn,
    TilerHeapCreateOut,
    VmBindIn,
    VmBindOp,
    VmCreateIn,
    VmCreateOut,
)

PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8


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
class GemZeros:
    cap_handle: int
    gpu_va: int
    size: int


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


GemStep = GemZeros | GemU32s | GemConst
RecipeStep = GemStep | IoctlStep


MESA_INIT_STEPS: list[RecipeStep] = [
{chr(10).join(init_lines)}
]


VADD_STEPS: list[RecipeStep] = [
{chr(10).join(vadd_lines)}
]
'''
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out)
    print(
        f"wrote {args.output} ({len(out)} bytes, "
        f"init={len(init_lines)} vadd={len(vadd_lines)} total={len(all_lines)})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
