#!/usr/bin/env python3
"""Experimental: hand-coded panthor vector add (mainline DRM path).

Not wired into examples/ — needs correct G610 CSF firmware and CS tuning.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cs_encode import build_int_add_cs
from gpu_stack import find_drm_gpu
from panthor_dev import PanthorDevice
from panthor_gpu import PAGE_SIZE, PanthorSession

WORKLOAD = "add"
COUNT = 4
INPUT_A = (1, 2, 3, 4)
INPUT_B = (10, 20, 30, 40)
EXPECTED = (11, 22, 33, 44)
VA_BASE = 0x1000000


def run(*, device: str | None, submit: bool, verbose: bool) -> int:
    dev_path = device or find_drm_gpu()
    if not dev_path:
        print("no Panthor render node", file=sys.stderr)
        return 1

    print(f"{WORKLOAD}: device {dev_path} (panthor)")
    if not submit:
        print("dry-run: DEV_QUERY → VM/BO → CSF int-add → GROUP_SUBMIT")
        print(f"  input A={list(INPUT_A)} B={list(INPUT_B)} expected={list(EXPECTED)}")
        return 0

    cmd_va = VA_BASE
    a_va = VA_BASE + PAGE_SIZE
    b_va = VA_BASE + 2 * PAGE_SIZE
    out_va = VA_BASE + 3 * PAGE_SIZE

    bos = []
    with PanthorDevice(dev_path) as dev, PanthorSession(dev) as sess:
        gpu = sess.init()
        if verbose:
            print(f"gpu_id=0x{gpu.gpu_id:08x} shader_present=0x{gpu.shader_present:x}")

        cmd_bo = sess.create_bo(PAGE_SIZE, cmd_va)
        a_bo = sess.create_bo(PAGE_SIZE, a_va)
        b_bo = sess.create_bo(PAGE_SIZE, b_va)
        out_bo = sess.create_bo(PAGE_SIZE, out_va)
        bos.extend((cmd_bo, a_bo, b_bo, out_bo))

        PanthorSession.write_u32_array(a_bo, INPUT_A)
        PanthorSession.write_u32_array(b_bo, INPUT_B)
        out_bo.map[:] = b"\x00" * out_bo.size

        cs = build_int_add_cs(a_va=a_va, b_va=b_va, out_va=out_va, count=COUNT)
        cmd_bo.map[: len(cs)] = cs

        try:
            sess.submit_cs(cmd_va, len(cs), cmd_bo, a_bo, b_bo, out_bo)
        except OSError as exc:
            if exc.errno != 62:
                raise
            print("GPU submit timed out — see journalctl -k | grep CS_FATAL", file=sys.stderr)
            return 1
        sess.sync_bo_for_cpu(out_bo)
        got = PanthorSession.read_u32_array(out_bo, COUNT)

    for bo in bos:
        bo.close(dev)

    print(f"expected={list(EXPECTED)} got={got}")
    return 0 if tuple(got) == EXPECTED else 1


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--device")
    p.add_argument("-v", "--verbose", action="store_true")
    a = p.parse_args()
    return run(device=a.device, submit=not a.dry_run, verbose=a.verbose)


if __name__ == "__main__":
    sys.exit(main())
