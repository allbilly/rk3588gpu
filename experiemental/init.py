#!/usr/bin/env python3
"""Minimal Mali kbase CSF init without libmali.

Opens /dev/mali0 and replays the first ioctls every CSF client needs:
  VERSION_CHECK → SET_FLAGS → CS_GET_GLB_IFACE → CS_QUEUE_GROUP_CREATE

For mainline panthor experiments see experiemental/panthor/panthor_init.py.
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
    IOCTL_SET_FLAGS,
    IOCTL_VERSION_CHECK,
    KbaseCsGetGlbIface,
    KbaseCsQueueGroupCreate,
    KbaseSetFlags,
    KbaseVersionCheck,
)

MAX_GROUPS = 16
MAX_STREAMS = 64


def run(*, device: str | None, submit: bool) -> int:
    dev_path = device or find_mali_device()
    if not dev_path:
        print("no Mali kbase device (/dev/mali0)", file=sys.stderr)
        return 1

    print(f"device: {dev_path}")
    if not submit:
        print("dry-run: would issue VERSION_CHECK, SET_FLAGS, CS_GET_GLB_IFACE, CS_QUEUE_GROUP_CREATE")
        return 0

    groups = (ctypes.c_uint8 * (MAX_GROUPS * 64))()
    streams = (ctypes.c_uint8 * (MAX_STREAMS * 64))()

    with KbaseDevice(dev_path) as dev:
        vc = KbaseVersionCheck(major=1, minor=14)
        dev.ioctl(IOCTL_VERSION_CHECK, vc)
        print(f"VERSION_CHECK: major={vc.major} minor={vc.minor}")

        dev.ioctl(IOCTL_SET_FLAGS, KbaseSetFlags(create_flags=0))
        print("SET_FLAGS: ok")

        glb = KbaseCsGetGlbIface()
        glb.in_.max_group_num = MAX_GROUPS
        glb.in_.max_total_stream_num = MAX_STREAMS
        glb.in_.groups_ptr = ctypes.addressof(groups)
        glb.in_.streams_ptr = ctypes.addressof(streams)
        dev.ioctl(IOCTL_CS_GET_GLB_IFACE, glb)
        iface = decode_ioctl_out(IOCTL_CS_GET_GLB_IFACE, bytes(glb))
        print(f"CS_GET_GLB_IFACE: {repr_value(iface)}")

        grp = KbaseCsQueueGroupCreate()
        grp.in_.tiler_mask = 1
        grp.in_.fragment_mask = 1
        grp.in_.compute_mask = 1
        grp.in_.cs_min = 1
        grp.in_.priority = 0
        grp.in_.tiler_max = 1
        grp.in_.fragment_max = 1
        grp.in_.compute_max = 1
        grp.in_.csi_handlers = 1
        dev.ioctl(IOCTL_CS_QUEUE_GROUP_CREATE, grp)
        out = decode_ioctl_out(IOCTL_CS_QUEUE_GROUP_CREATE, bytes(grp))
        print(f"CS_QUEUE_GROUP_CREATE: {repr_value(out)}")

    print("PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print plan only")
    parser.add_argument("--device", help="kbase device path (default: /dev/mali0)")
    args = parser.parse_args()
    return run(device=args.device, submit=not args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
