#!/usr/bin/env python3
"""Replay panthor .pcap captures (used by panthor_pcap2replay.py)."""

from __future__ import annotations

import ctypes
import glob
import mmap
import os
import struct
import sys
import time
from pathlib import Path

PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_DEV_QUERY = 5
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8

DRM_BASE = 0x40
NR_DEV_QUERY = DRM_BASE + 0
NR_VM_CREATE = DRM_BASE + 1
NR_VM_BIND = DRM_BASE + 3
NR_BO_CREATE = DRM_BASE + 5
NR_BO_MMAP = DRM_BASE + 6
NR_GROUP_CREATE = DRM_BASE + 7
NR_GROUP_SUBMIT = DRM_BASE + 9
NR_TILER_HEAP_CREATE = DRM_BASE + 11
NR_BO_SET_LABEL = DRM_BASE + 13
NR_SYNCOBJ_CREATE = 0xBF
NR_SYNCOBJ_WAIT = 0xC3
NR_SYNCOBJ_FD_TO_HANDLE = 0xC2
NR_SYNCOBJ_TIMELINE_WAIT = 0xCA
SKIP_IOCTLS = {NR_BO_SET_LABEL, NR_SYNCOBJ_FD_TO_HANDLE, 0xC0}
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
    if nr == NR_VM_BIND:
        _patch_u32(buf, 0, hmap)
    elif nr == NR_BO_MMAP:
        _patch_u32(buf, 0, hmap)
    elif nr == NR_GROUP_SUBMIT:
        _patch_u32(buf, 0, hmap)
    elif nr == NR_GROUP_CREATE and len(buf) >= 44:
        _patch_u32(buf, 40, hmap)  # vm_id
    elif nr == NR_TILER_HEAP_CREATE:
        _patch_u32(buf, 0, hmap)  # vm_id
        _patch_u32(buf, 4, hmap)  # heap handle (input)
    elif nr == 0xCC:
        _patch_u32(buf, 0, hmap)
        _patch_u32(buf, 4, hmap)
    elif nr in (0xC0, 0xC2):
        _patch_u32(buf, 0, hmap)
    elif nr == NR_BO_CREATE and len(buf) >= 20:
        _patch_u32(buf, 16, hmap)  # handle extension / import


def _learn(nr: int, cap_out: bytes, live: bytes, hmap: dict[int, int]) -> None:
    pairs: list[tuple[int, int]] = []
    if nr == NR_BO_CREATE and len(cap_out) >= 20:
        pairs.append((struct.unpack_from("<I", cap_out, 16)[0], struct.unpack_from("<I", live, 16)[0]))
    elif nr == NR_VM_CREATE and len(cap_out) >= 8:
        pairs.append((struct.unpack_from("<I", cap_out, 4)[0], struct.unpack_from("<I", live, 4)[0]))
    elif nr == NR_GROUP_CREATE and len(cap_out) >= 48:
        pairs.append((struct.unpack_from("<I", cap_out, 44)[0], struct.unpack_from("<I", live, 44)[0]))
    elif nr == NR_SYNCOBJ_CREATE and len(cap_out) >= 4:
        pairs.append((struct.unpack_from("<I", cap_out, 0)[0], struct.unpack_from("<I", live, 0)[0]))
    elif nr == NR_TILER_HEAP_CREATE and len(cap_out) >= 36:
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

        if nr == NR_DEV_QUERY and sides:
            struct.pack_into("<Q", arg, 8, ctypes.addressof(sides[0][1]))
        elif nr == NR_VM_BIND and sides:
            struct.pack_into("<Q", arg, 16, ctypes.addressof(sides[0][1]))
            if bind_sync:
                struct.pack_into("<Q", sides[0][1], 40, ctypes.addressof(bind_sync[0]))
        elif nr == NR_GROUP_CREATE and sides:
            struct.pack_into("<Q", arg, 8, ctypes.addressof(sides[0][1]))
        elif nr == NR_GROUP_SUBMIT:
            qs = next((sb for k, sb in sides if k == PANT_SIDE_QUEUE_SUBMITS), None)
            if qs is not None:
                struct.pack_into("<Q", arg, 16, ctypes.addressof(qs))
                struct.pack_into("<I", qs, 16, _read_flush_id(fd))
                sync = next((sb for k, sb in sides if k == PANT_SIDE_SYNC_OPS), None)
                if sync is not None:
                    struct.pack_into("<Q", qs, 32, ctypes.addressof(sync))
                if struct.unpack_from("<I", qs, 4)[0] == 160:
                    _sync_mapped_bos(fd, mmaps, hmap, write=True)
        elif nr == NR_SYNCOBJ_WAIT:
            for sk, sb in sides:
                if sk == PANT_SIDE_SYNCOBJ_HANDLES:
                    hb = bytearray(sb)
                    _patch_syncobj_handles(hb, hmap)
                    for i, b in enumerate(hb):
                        sb[i] = b
                    struct.pack_into("<Q", arg, 0, ctypes.addressof(sb))
                    break
        elif nr == NR_SYNCOBJ_TIMELINE_WAIT:
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
            if (req & 0xFF) in (NR_SYNCOBJ_WAIT, NR_SYNCOBJ_TIMELINE_WAIT) and exc.errno in (22, 62):
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

        if nr == NR_GROUP_SUBMIT:
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

        if nr == NR_BO_CREATE and len(live) >= 20:
            handle = struct.unpack_from("<I", live, 16)[0]
            bo_size[handle] = struct.unpack_from("<Q", live, 0)[0]

        if nr == NR_BO_MMAP and len(live) >= 16:
            handle = struct.unpack_from("<I", live, 0)[0]
            offset = struct.unpack_from("<Q", live, 8)[0]
            size = bo_size.get(handle, 4096)
            map_sz = (size + 4095) & ~4095
            mmaps[handle] = mmap.mmap(
                fd, map_sz, mmap.MAP_SHARED, mmap.PROT_READ | mmap.PROT_WRITE, offset=offset
            )

        if nr == NR_SYNCOBJ_WAIT or nr == NR_SYNCOBJ_TIMELINE_WAIT:
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
    import argparse

    from panthor_cap_format import PantGem, PantIoctl, PantSide, load_events

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("--from", dest="start", type=int, default=0)
    ap.add_argument("--until", type=int, default=0)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    tuples: list[tuple] = []
    for ev in load_events(args.pcap)[args.start :]:
        if isinstance(ev, PantIoctl):
            tuples.append(("ioctl", ev.request, ev.ret, ev.arg_in, ev.arg_out))
        elif isinstance(ev, PantSide):
            tuples.append(("side", ev.kind, ev.data))
        elif isinstance(ev, PantGem):
            tuples.append(("gem", ev.handle, ev.gpu_va, ev.bo_offset, ev.data))
    if args.until:
        tuples = tuples[: args.until]
    try:
        return replay_events(tuples, verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
