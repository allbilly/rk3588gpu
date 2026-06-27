#!/usr/bin/env python3
"""Replay Mali kbase captures without libmali.

Mirrors experimental/replay.py for AGX:
  capture (.mcap) → patch GPU VAs → ioctl replay on /dev/mali0

Design reference:
  github.com/allbilly/rk3588 — GDB ioctl capture + ctypes replay
  experimental/            — cap_format + AddrMap pattern
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

from cap_decode import decode_ioctl_in, decode_ioctl_out, repr_value
from cap_format import (
    AddrMap,
    MaliGem,
    MaliIoctl,
    MaliMarker,
    CaptureReader,
    load_events,
)
from cs_disasm import disasm_ring
from kbase_dev import KbaseDevice, find_mali_device
from kbase_ioctl import (
    IOCTL_CS_QUEUE_REGISTER,
    IOCTL_MEM_ALLOC,
    IOCTL_MEM_ALLOC_EX,
)

ROOT = Path(__file__).resolve().parent


def format_event(idx: int, event: MaliIoctl | MaliGem | MaliMarker) -> str:
    if isinstance(event, MaliMarker):
        return f"[{idx}] MARKER {event.tag!r}"
    if isinstance(event, MaliGem):
        return (
            f"[{idx}] GEM va=0x{event.gpu_va:x} label={event.label!r} "
            f"size={len(event.data)}"
        )
    return (
        f"[{idx}] IOCTL {event.name} req=0x{event.request:08x} "
        f"in={len(event.arg_in)} out={len(event.arg_out)} ret={event.ret}"
    )


def replay_ioctl(
    dev: KbaseDevice,
    op: MaliIoctl,
    addr_map: AddrMap,
    idx: int,
    submit: bool,
) -> bool:
    arg_in = bytearray(op.arg_in)
    addr_map.patch_u64_buf(arg_in)

    decoded_in = decode_ioctl_in(op.request, bytes(arg_in))
    if decoded_in is not None:
        print(f"  in:  {repr_value(decoded_in)}")

    if not submit:
        print(format_event(idx, op) + " (dry-run)")
        return True

    try:
        ret, live_out = dev.ioctl_bytes(op.request, bytes(arg_in))
    except OSError as exc:
        print(f"[{idx}] {op.name} FAILED: {exc}", file=sys.stderr)
        return False

    print(
        f"[{idx}] {op.name} ret={ret} (captured {op.ret}) "
        f"out={len(live_out)} bytes"
    )
    decoded_out = decode_ioctl_out(op.request, live_out)
    if decoded_out is not None:
        print(f"  out: {repr_value(decoded_out)}")

    if op.request in (IOCTL_MEM_ALLOC, IOCTL_MEM_ALLOC_EX) and decoded_out is not None:
        addr_map.learn_mem_alloc(bytes(arg_in), live_out)

    if op.request == IOCTL_CS_QUEUE_REGISTER and decoded_in is not None:
        ring_va = decoded_in.buffer_gpu_addr
        print(f"  ring buffer GPU VA (patched): 0x{ring_va:x}")

    return ret == op.ret or (op.ret < 0 and ret < 0)


def dump_capture(path: Path, disasm_cs: bool) -> int:
    events = load_events(path)
    print(f"loaded {len(events)} events from {path}")
    for idx, event in enumerate(events):
        print(format_event(idx, event))
        if isinstance(event, MaliIoctl):
            din = decode_ioctl_in(event.request, event.arg_in)
            dout = decode_ioctl_out(event.request, event.arg_out)
            if din is not None:
                print(f"  in:  {repr_value(din)}")
            if dout is not None:
                print(f"  out: {repr_value(dout)}")
        if disasm_cs and isinstance(event, MaliGem) and "ring" in event.label.lower():
            print(f"  --- CS disasm ({event.label}) ---")
            for line in disasm_ring(event.data):
                print(f"  {line}")
    return 0


def replay_file(path: Path, submit: bool, device: str | None) -> int:
    events = load_events(path)
    print(f"loaded {len(events)} events from {path}")

    if not submit:
        return dump_capture(path, disasm_cs=False)

    dev_path = device or find_mali_device()
    if not dev_path:
        print("no Mali device (/dev/mali0 or renderD*)", file=sys.stderr)
        return 1

    addr_map = AddrMap()
    gems: list[MaliGem] = []
    fails = 0
    idx = 0

    print(f"replaying on {dev_path}")
    with KbaseDevice(dev_path) as dev:
        for event in events:
            if isinstance(event, MaliMarker):
                print(f"[{idx}] --- {event.tag} ---")
                idx += 1
                continue
            if isinstance(event, MaliGem):
                gems.append(event)
                print(format_event(idx, event))
                idx += 1
                continue
            fails += not replay_ioctl(dev, event, addr_map, idx, submit=True)
            idx += 1

    print(f"done: {idx} ops, {fails} failures, {len(addr_map)} addr maps, {len(gems)} gem dumps")
    if gems:
        print("note: GEM blobs were not re-uploaded — capture must include MEM_ALLOC sequence")
    return 1 if fails else 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay Mali kbase ioctl captures.")
    parser.add_argument(
        "capture",
        nargs="?",
        default=str(ROOT / "test.mcap"),
        help="capture file (.mcap)",
    )
    parser.add_argument("--dry-run", action="store_true", help="parse only, no ioctls")
    parser.add_argument("--disasm-cs", action="store_true", help="disasm ring GEM blobs when dumping")
    parser.add_argument("--device", help="kbase device path (default: /dev/mali0)")
    args = parser.parse_args()

    path = Path(args.capture)
    if not path.exists():
        print(f"{path}: not found", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        sys.exit(dump_capture(path, disasm_cs=args.disasm_cs))
    sys.exit(replay_file(path, submit=True, device=args.device))


if __name__ == "__main__":
    main()
