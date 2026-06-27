#!/usr/bin/env python3
"""Minimal Panthor DRM init on mainline Mali (renderD*).

Opens the Mali render node and queries GPU + CSIF info via DRM_IOCTL_PANTHOR_DEV_QUERY.
Mirrors examples/init.py on the kbase BSP path.
"""

from __future__ import annotations

import argparse
import ctypes
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from gpu_stack import find_drm_gpu
from panthor_dev import PanthorDevice
from panthor_ioctl import (
    DRM_PANTHOR_DEV_QUERY_CSIF_INFO,
    DRM_PANTHOR_DEV_QUERY_GPU_INFO,
    DrmPanthorCsifInfo,
    DrmPanthorDevQuery,
    DrmPanthorGpuInfo,
    IOCTL_PANTHOR_DEV_QUERY,
)


def _dev_query(dev: PanthorDevice, qtype: int, out: ctypes.Structure) -> None:
    q = DrmPanthorDevQuery(type=qtype, size=ctypes.sizeof(out), pointer=ctypes.addressof(out))
    dev.ioctl(IOCTL_PANTHOR_DEV_QUERY, q)


def run(*, device: str | None, submit: bool) -> int:
    dev_path = device or find_drm_gpu()
    if not dev_path:
        print("no Panthor/Panfrost render node", file=sys.stderr)
        return 1

    print(f"device: {dev_path}")
    if not submit:
        print("dry-run: would issue DEV_QUERY (GPU_INFO, CSIF_INFO)")
        return 0

    with PanthorDevice(dev_path) as dev:
        gpu = DrmPanthorGpuInfo()
        _dev_query(dev, DRM_PANTHOR_DEV_QUERY_GPU_INFO, gpu)
        print(
            f"DEV_QUERY GPU_INFO: gpu_id=0x{gpu.gpu_id:08x} "
            f"max_threads={gpu.max_threads} shader_present=0x{gpu.shader_present:x}"
        )

        csif = DrmPanthorCsifInfo()
        _dev_query(dev, DRM_PANTHOR_DEV_QUERY_CSIF_INFO, csif)
        print(
            f"DEV_QUERY CSIF_INFO: csg_slots={csif.csg_slot_count} "
            f"cs_slots={csif.cs_slot_count} cs_regs={csif.cs_reg_count}"
        )

    print("PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="print plan only")
    parser.add_argument("--device", help="DRM render node (default: Mali renderD*)")
    args = parser.parse_args()
    return run(device=args.device, submit=not args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
