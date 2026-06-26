#!/usr/bin/env python3
"""Vector add on Mali G610 via /dev/mali0 — pure Python, no libmali.

Same role as applegpu examples/add.py: open device, alloc buffers, submit GPU
work, verify results. This board uses the Rockchip BSP kbase stack (not Mesa
Panfrost on renderD128); see gpt-deepresearch.md for the two-stack distinction.

Steps implemented:

  1. open /dev/mali0
  2. VERSION_CHECK + SET_FLAGS          (context)
  3. CS_GET_GLB_IFACE                   (query GPU)
  4. CS_QUEUE_GROUP_CREATE              (scheduler group)
  5. MEM_ALLOC × 3                      (input A, input B, output) — attempted
  6. CS_QUEUE_REGISTER + KICK           (needs real CSF ring — use capture/replay)

Full vector add still requires a captured CSF ring or hand-built shader bytes.
Use ``make capture APP=...`` then ``replay.py`` for end-to-end replay.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cap_decode import decode_ioctl_out, repr_value
from kbase_dev import KbaseDevice, find_mali_device
from kbase_ioctl import (
    IOCTL_CS_GET_GLB_IFACE,
    IOCTL_CS_QUEUE_GROUP_CREATE,
    IOCTL_MEM_ALLOC,
    IOCTL_SET_FLAGS,
    IOCTL_VERSION_CHECK,
    KbaseCsGetGlbIface,
    KbaseCsQueueGroupCreate,
    KbaseMemAlloc,
    KbaseSetFlags,
    KbaseVersionCheck,
)

WORKLOAD = "add"
EXPECTED = (11.0, 22.0, 33.0, 44.0)  # metal_add reference from applegpu
MAX_GROUPS = 16
MAX_STREAMS = 64

# BASE_MEM_PROT_CPU_{RD,WR} | BASE_MEM_PROT_GPU_{RD,WR} | BASE_MEM_SAME_VA
BASE_MEM_RW = (1 << 3) | (1 << 4) | (1 << 9) | (1 << 10) | (1 << 22)


def try_mem_alloc(dev: KbaseDevice, pages: int = 1) -> int | None:
    """Return GPU VA on success."""
    alloc = KbaseMemAlloc()
    alloc.in_.va_pages = pages
    alloc.in_.commit_pages = pages
    alloc.in_.extension = 0
    alloc.in_.flags = BASE_MEM_RW
    try:
        dev.ioctl(IOCTL_MEM_ALLOC, alloc)
    except OSError as exc:
        print(f"  MEM_ALLOC failed: {exc}")
        return None
    out = decode_ioctl_out(IOCTL_MEM_ALLOC, bytes(alloc))
    if out is None:
        return None
    print(f"  MEM_ALLOC gpu_va=0x{out.gpu_va:x}")
    return out.gpu_va


def run_workload(*, device: str | None, submit: bool, verbose: bool) -> int:
    dev_path = device or find_mali_device()
    if not dev_path:
        print("no Mali device (/dev/mali0)", file=sys.stderr)
        return 1

    print(f"{WORKLOAD}: device {dev_path}")
    if not submit:
        print("dry-run steps:")
        print("  1. VERSION_CHECK + SET_FLAGS")
        print("  2. CS_GET_GLB_IFACE")
        print("  3. CS_QUEUE_GROUP_CREATE")
        print("  4. MEM_ALLOC (A, B, out)")
        print("  5. CS_QUEUE_REGISTER + KICK (needs captured CSF ring)")
        print(f"  expected={list(EXPECTED)}")
        return 0

    fails = 0
    with KbaseDevice(dev_path) as dev:
        vc = KbaseVersionCheck(major=1, minor=14)
        dev.ioctl(IOCTL_VERSION_CHECK, vc)
        if verbose:
            print(f"[0] VERSION_CHECK major={vc.major} minor={vc.minor}")

        dev.ioctl(IOCTL_SET_FLAGS, KbaseSetFlags(create_flags=0))
        if verbose:
            print("[1] SET_FLAGS ok")

        groups = (ctypes.c_uint8 * (MAX_GROUPS * 64))()
        streams = (ctypes.c_uint8 * (MAX_STREAMS * 64))()
        glb = KbaseCsGetGlbIface()
        glb.in_.max_group_num = MAX_GROUPS
        glb.in_.max_total_stream_num = MAX_STREAMS
        glb.in_.groups_ptr = ctypes.addressof(groups)
        glb.in_.streams_ptr = ctypes.addressof(streams)
        dev.ioctl(IOCTL_CS_GET_GLB_IFACE, glb)
        if verbose:
            print(f"[2] CS_GET_GLB_IFACE {repr_value(decode_ioctl_out(IOCTL_CS_GET_GLB_IFACE, bytes(glb)))}")

        grp = KbaseCsQueueGroupCreate()
        grp.in_.tiler_mask = grp.in_.fragment_mask = grp.in_.compute_mask = 1
        grp.in_.cs_min = grp.in_.tiler_max = grp.in_.fragment_max = grp.in_.compute_max = 1
        grp.in_.csi_handlers = 1
        dev.ioctl(IOCTL_CS_QUEUE_GROUP_CREATE, grp)
        if verbose:
            print(f"[3] CS_QUEUE_GROUP_CREATE {repr_value(decode_ioctl_out(IOCTL_CS_QUEUE_GROUP_CREATE, bytes(grp)))}")

        print("[4] MEM_ALLOC buffers:")
        vas = []
        for label in ("A", "B", "out"):
            print(f"  buffer {label}:")
            va = try_mem_alloc(dev)
            if va is None:
                fails += 1
            else:
                vas.append(va)

        if len(vas) < 3:
            print("note: MEM_ALLOC needs driver-specific flags or a captured sequence")
            print("      record a working app: make capture APP=./app CAP=add.mcap")
            print("      then: python3 replay.py add.mcap")

    if fails:
        print(f"FAIL ({fails} steps; init ioctls OK, alloc/submit incomplete)")
        return 1
    print(f"expected={list(EXPECTED)}")
    print("PASS (buffers allocated; CSF submit not yet wired)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--device", help="kbase device (default /dev/mali0)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()
    return run_workload(device=args.device, submit=not args.dry_run, verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
