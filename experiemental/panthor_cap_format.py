"""Panthor DRI capture (.pcap) reader."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

PANT_MAGIC = 0x504E4154
PANT_VERSION = 1

PANT_IOCTL = 1
PANT_SIDE = 2
PANT_GEM = 3
PANT_MARKER = 4

PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_DEV_QUERY = 5
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8

HDR_FMT = "<4I"
IOCTL_HDR_FMT = "<B3xIIIi"  # 20 bytes (C struct padding)
SIDE_HDR_FMT = "<BBHI"      # 8 bytes
GEM_HDR_FMT = "<B3xII4xQQII"  # matches struct pant_gem_hdr (40 bytes with tail padding)
GEM_HDR_SIZE = struct.calcsize(GEM_HDR_FMT)

SIDE_KINDS = {
    PANT_SIDE_VM_BIND_OPS: "vm_bind_ops",
    PANT_SIDE_QUEUE_SUBMITS: "queue_submits",
    PANT_SIDE_GROUP_QUEUES: "group_queues",
    PANT_SIDE_SYNC_OPS: "sync_ops",
    PANT_SIDE_DEV_QUERY: "dev_query",
    PANT_SIDE_BIND_SYNC_OPS: "bind_sync_ops",
    PANT_SIDE_SYNCOBJ_HANDLES: "syncobj_handles",
    PANT_SIDE_SYNCOBJ_POINTS: "syncobj_points",
}


@dataclass
class PantIoctl:
    request: int
    arg_in: bytes
    arg_out: bytes
    ret: int

    @property
    def nr(self) -> int:
        return self.request & 0xFF


@dataclass
class PantSide:
    kind: int
    data: bytes

    @property
    def kind_name(self) -> str:
        return SIDE_KINDS.get(self.kind, f"side_{self.kind}")


@dataclass
class PantGem:
    handle: int
    gpu_va: int
    bo_offset: int
    data: bytes


@dataclass
class PantMarker:
    tag: str


PantEvent = PantIoctl | PantSide | PantGem | PantMarker


def load_events(path: Path) -> list[PantEvent]:
    data = path.read_bytes()
    magic, version, count, _ = struct.unpack_from(HDR_FMT, data, 0)
    if magic != PANT_MAGIC:
        raise ValueError(f"bad magic 0x{magic:08x}")
    if version != PANT_VERSION:
        raise ValueError(f"unsupported version {version}")

    events: list[PantEvent] = []
    off = struct.calcsize(HDR_FMT)
    while off < len(data):
        typ = data[off]
        if typ == PANT_IOCTL:
            _, request, in_sz, out_sz, ret = struct.unpack_from(IOCTL_HDR_FMT, data, off)
            off += struct.calcsize(IOCTL_HDR_FMT)
            arg_in = data[off : off + in_sz]
            off += in_sz
            arg_out = data[off : off + out_sz]
            off += out_sz
            events.append(PantIoctl(request, arg_in, arg_out, ret))
        elif typ == PANT_SIDE:
            _t, kind, _pad, data_sz = struct.unpack_from(SIDE_HDR_FMT, data, off)
            off += struct.calcsize(SIDE_HDR_FMT)
            events.append(PantSide(kind, data[off : off + data_sz]))
            off += data_sz
        elif typ == PANT_GEM:
            _t, handle, _pad2, gpu_va, bo_offset, data_sz, _pad3 = struct.unpack_from(
                GEM_HDR_FMT, data, off
            )
            off += GEM_HDR_SIZE
            events.append(PantGem(handle, gpu_va, bo_offset, data[off : off + data_sz]))
            off += data_sz
        elif typ == PANT_MARKER:
            tag_sz, = struct.unpack_from("<I", data, off + 4)
            off += 8
            tag = data[off : off + tag_sz].decode()
            off += tag_sz
            events.append(PantMarker(tag))
        else:
            raise ValueError(f"unknown event type {typ} at offset {off}")
    if len(events) != count:
        raise ValueError(f"count mismatch: header {count} vs parsed {len(events)}")
    return events
