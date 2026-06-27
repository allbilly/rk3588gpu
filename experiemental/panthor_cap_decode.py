"""Decode panthor DRM capture blobs into named structures.

Field layouts follow <drm/panthor_drm.h> and <drm/drm.h> syncobj structs.
Used by tools/panthor_pcap2standalone.py (applegpu cap_decode.py analogue).
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from typing import Any

DRM_COMMAND_BASE = 0x40

NR_DEV_QUERY = DRM_COMMAND_BASE + 0
NR_VM_CREATE = DRM_COMMAND_BASE + 1
NR_VM_BIND = DRM_COMMAND_BASE + 3
NR_BO_CREATE = DRM_COMMAND_BASE + 5
NR_BO_MMAP = DRM_COMMAND_BASE + 6
NR_GROUP_CREATE = DRM_COMMAND_BASE + 7
NR_GROUP_CREATE = DRM_COMMAND_BASE + 7
NR_GROUP_SUBMIT = DRM_COMMAND_BASE + 9
NR_TILER_HEAP_CREATE = DRM_COMMAND_BASE + 11
NR_BO_SET_LABEL = DRM_COMMAND_BASE + 13
NR_SYNCOBJ_CREATE = 0xBF
NR_SYNCOBJ_DESTROY = 0xC0
NR_SYNCOBJ_WAIT = 0xC3
NR_SYNCOBJ_TIMELINE_WAIT = 0xCA
NR_SYNCOBJ_TRANSFER = 0xCC

IOCTL_NAMES: dict[int, str] = {
    NR_DEV_QUERY: "DEV_QUERY",
    NR_VM_CREATE: "VM_CREATE",
    NR_VM_BIND: "VM_BIND",
    NR_BO_CREATE: "BO_CREATE",
    NR_BO_MMAP: "BO_MMAP",
    NR_GROUP_CREATE: "GROUP_CREATE",
    NR_GROUP_SUBMIT: "GROUP_SUBMIT",
    NR_TILER_HEAP_CREATE: "TILER_HEAP_CREATE",
    NR_BO_SET_LABEL: "BO_SET_LABEL",
    NR_SYNCOBJ_CREATE: "SYNCOBJ_CREATE",
    NR_SYNCOBJ_DESTROY: "SYNCOBJ_DESTROY",
    NR_SYNCOBJ_WAIT: "SYNCOBJ_WAIT",
    NR_SYNCOBJ_TIMELINE_WAIT: "SYNCOBJ_TIMELINE_WAIT",
    NR_SYNCOBJ_TRANSFER: "SYNCOBJ_TRANSFER",
}


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _u64(buf: bytes, off: int) -> int:
    return struct.unpack_from("<Q", buf, off)[0]


def repr_value(val: Any) -> str:
    if isinstance(val, bytes):
        if len(val) <= 16:
            return repr(val)
        return f"bytes.fromhex({val.hex()!r})"
    if isinstance(val, int) and val > 0xFFFF:
        return f"0x{val:X}"
    return repr(val)


@dataclass
class VmCreateIn:
    flags: int = 0
    user_va_range: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> VmCreateIn:
        return cls(_u32(data, 0), _u64(data, 8) if len(data) >= 16 else 0)

    def pack(self) -> bytes:
        buf = bytearray(16)
        struct.pack_into("<I", buf, 0, self.flags)
        struct.pack_into("<Q", buf, 8, self.user_va_range)
        return bytes(buf)


@dataclass
class VmCreateOut:
    id: int = 0
    user_va_range: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> VmCreateOut:
        return cls(_u32(data, 4) if len(data) >= 8 else 0, _u64(data, 8) if len(data) >= 16 else 0)

    def pack(self) -> bytes:
        buf = bytearray(16)
        struct.pack_into("<I", buf, 4, self.id)
        struct.pack_into("<Q", buf, 8, self.user_va_range)
        return bytes(buf)


@dataclass
class VmBindOp:
    """drm_panthor_vm_bind_op (48 bytes)."""

    flags: int = 0
    bo_handle: int = 0
    bo_offset: int = 0
    va: int = 0
    size: int = 0
    syncs_stride: int = 0
    syncs_count: int = 0
    syncs_ptr: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> VmBindOp:
        if len(data) < 48:
            raise ValueError(f"VmBindOp expects 48 bytes, got {len(data)}")
        return cls(
            _u32(data, 0),
            _u32(data, 4),
            _u64(data, 8),
            _u64(data, 16),
            _u64(data, 24),
            _u32(data, 32),
            _u32(data, 36),
            _u64(data, 40),
        )

    def pack(self) -> bytes:
        buf = bytearray(48)
        struct.pack_into("<I", buf, 0, self.flags)
        struct.pack_into("<I", buf, 4, self.bo_handle)
        struct.pack_into("<Q", buf, 8, self.bo_offset)
        struct.pack_into("<Q", buf, 16, self.va)
        struct.pack_into("<Q", buf, 24, self.size)
        struct.pack_into("<I", buf, 32, self.syncs_stride)
        struct.pack_into("<I", buf, 36, self.syncs_count)
        struct.pack_into("<Q", buf, 40, self.syncs_ptr)
        return bytes(buf)


@dataclass
class VmBindIn:
    vm_id: int = 0
    flags: int = 0
    ops_stride: int = 0
    ops_count: int = 0
    ops_ptr: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> VmBindIn:
        return cls(_u32(data, 0), _u32(data, 4), _u32(data, 8), _u32(data, 12), _u64(data, 16))

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<I", buf, 0, self.vm_id)
        struct.pack_into("<I", buf, 4, self.flags)
        struct.pack_into("<I", buf, 8, self.ops_stride)
        struct.pack_into("<I", buf, 12, self.ops_count)
        struct.pack_into("<Q", buf, 16, self.ops_ptr)
        return bytes(buf)


@dataclass
class BoCreateIn:
    size: int = 0
    flags: int = 0
    exclusive_vm_id: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> BoCreateIn:
        return cls(_u64(data, 0), _u32(data, 8), _u32(data, 12))

    def pack(self) -> bytes:
        return struct.pack(
            "<QIIII", self.size, self.flags, self.exclusive_vm_id, 0, 0
        )


@dataclass
class BoCreateOut:
    size: int = 0
    flags: int = 0
    exclusive_vm_id: int = 0
    handle: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> BoCreateOut:
        return cls(_u64(data, 0), _u32(data, 8), _u32(data, 12), _u32(data, 16))

    def pack(self) -> bytes:
        return struct.pack("<QIII", self.size, self.flags, self.exclusive_vm_id, self.handle)


@dataclass
class BoMmapIn:
    handle: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> BoMmapIn:
        return cls(_u32(data, 0))

    def pack(self) -> bytes:
        return struct.pack("<IIQ", self.handle, 0, 0)


@dataclass
class BoMmapOut:
    handle: int = 0
    offset: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> BoMmapOut:
        return cls(_u32(data, 0), _u64(data, 8))

    def pack(self) -> bytes:
        return struct.pack("<IQ", self.handle, self.offset)


@dataclass
class QueueSubmit:
    """drm_panthor_queue_submit sidecar (40 bytes)."""

    queue_index: int = 0
    stream_size: int = 0
    stream_addr: int = 0
    latest_flush: int = 0
    syncs_stride: int = 0
    syncs_count: int = 0
    syncs_ptr: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> QueueSubmit:
        if len(data) < 40:
            raise ValueError(f"QueueSubmit expects 40 bytes, got {len(data)}")
        return cls(
            _u32(data, 0),
            _u32(data, 4),
            _u64(data, 8),
            _u32(data, 16),
            _u32(data, 24),
            _u32(data, 28),
            _u64(data, 32),
        )

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into("<I", buf, 0, self.queue_index)
        struct.pack_into("<I", buf, 4, self.stream_size)
        struct.pack_into("<Q", buf, 8, self.stream_addr)
        struct.pack_into("<I", buf, 16, self.latest_flush)
        struct.pack_into("<I", buf, 24, self.syncs_stride)
        struct.pack_into("<I", buf, 28, self.syncs_count)
        struct.pack_into("<Q", buf, 32, self.syncs_ptr)
        return bytes(buf)


@dataclass
class SyncOp:
    """drm_panthor_sync_op (16 bytes)."""

    flags: int = 0
    handle: int = 0
    timeline_value: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SyncOp:
        return cls(_u32(data, 0), _u32(data, 4), _u64(data, 8))

    def pack(self) -> bytes:
        return struct.pack("<IIQ", self.flags, self.handle, self.timeline_value)


@dataclass
class VmBindOut:
    vm_id: int = 0
    flags: int = 0
    ops_stride: int = 0
    ops_count: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> VmBindOut:
        return cls(_u32(data, 0), _u32(data, 4), _u32(data, 8), _u32(data, 12))

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<IIII", buf, 0, self.vm_id, self.flags, self.ops_stride, self.ops_count)
        return bytes(buf)


@dataclass
class GroupCreateIn:
    qs_stride: int = 8
    qs_count: int = 1
    qs_ptr: int = 0
    max_compute_cores: int = 0
    max_fragment_cores: int = 0
    max_tiler_cores: int = 0
    priority: int = 0
    compute_core_mask: int = 0
    fragment_core_mask: int = 0
    tiler_core_mask: int = 0
    vm_id: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> GroupCreateIn:
        return cls(
            _u32(data, 0),
            _u32(data, 4),
            _u64(data, 8),
            data[16] if len(data) > 16 else 0,
            data[17] if len(data) > 17 else 0,
            data[18] if len(data) > 18 else 0,
            data[19] if len(data) > 19 else 0,
            _u64(data, 24) if len(data) >= 32 else 0,
            _u64(data, 32) if len(data) >= 40 else 0,
            _u64(data, 40) if len(data) >= 48 else 0,
            _u32(data, 48) if len(data) >= 52 else 0,
        )

    def pack(self) -> bytes:
        buf = bytearray(56)
        struct.pack_into("<II", buf, 0, self.qs_stride, self.qs_count)
        struct.pack_into("<Q", buf, 8, self.qs_ptr)
        buf[16] = self.max_compute_cores
        buf[17] = self.max_fragment_cores
        buf[18] = self.max_tiler_cores
        buf[19] = self.priority
        struct.pack_into("<Q", buf, 24, self.compute_core_mask)
        struct.pack_into("<Q", buf, 32, self.fragment_core_mask)
        struct.pack_into("<Q", buf, 40, self.tiler_core_mask)
        struct.pack_into("<I", buf, 48, self.vm_id)
        return bytes(buf)


@dataclass
class GroupCreateOut(GroupCreateIn):
    group_handle: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> GroupCreateOut:
        base = GroupCreateIn.from_bytes(data)
        return cls(
            base.qs_stride,
            base.qs_count,
            0,
            base.max_compute_cores,
            base.max_fragment_cores,
            base.max_tiler_cores,
            base.priority,
            base.compute_core_mask,
            base.fragment_core_mask,
            base.tiler_core_mask,
            base.vm_id,
            _u32(data, 52) if len(data) >= 56 else 0,
        )

    def pack(self) -> bytes:
        buf = bytearray(GroupCreateIn.pack(self))
        struct.pack_into("<I", buf, 52, self.group_handle)
        return bytes(buf)


@dataclass
class GroupSubmitIn:
    group_handle: int = 0
    qs_stride: int = 0
    qs_count: int = 0
    qs_ptr: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> GroupSubmitIn:
        return cls(_u32(data, 0), _u32(data, 8), _u32(data, 12), _u64(data, 16))

    def pack(self) -> bytes:
        buf = bytearray(24)
        struct.pack_into("<I", buf, 0, self.group_handle)
        struct.pack_into("<I", buf, 8, self.qs_stride)
        struct.pack_into("<I", buf, 12, self.qs_count)
        struct.pack_into("<Q", buf, 16, self.qs_ptr)
        return bytes(buf)


@dataclass
class TilerHeapCreateIn:
    vm_id: int = 0
    initial_chunk_count: int = 0
    chunk_size: int = 0
    max_chunks: int = 0
    target_in_flight: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> TilerHeapCreateIn:
        return cls(_u32(data, 0), _u32(data, 4), _u32(data, 8), _u32(data, 12), _u32(data, 16))

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into(
            "<IIIII",
            buf,
            0,
            self.vm_id,
            self.initial_chunk_count,
            self.chunk_size,
            self.max_chunks,
            self.target_in_flight,
        )
        struct.pack_into("<I", buf, 20, 0)
        struct.pack_into("<Q", buf, 24, 0)
        struct.pack_into("<Q", buf, 32, 0)
        return bytes(buf)


@dataclass
class TilerHeapCreateOut(TilerHeapCreateIn):
    handle: int = 0
    tiler_heap_ctx_gpu_va: int = 0
    first_heap_chunk_gpu_va: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> TilerHeapCreateOut:
        base = TilerHeapCreateIn.from_bytes(data[:20])
        return cls(
            base.vm_id,
            base.initial_chunk_count,
            base.chunk_size,
            base.max_chunks,
            base.target_in_flight,
            _u32(data, 32) if len(data) >= 36 else 0,
            _u64(data, 40) if len(data) >= 48 else 0,
            _u64(data, 48) if len(data) >= 56 else 0,
        )

    def pack(self) -> bytes:
        buf = bytearray(40)
        struct.pack_into(
            "<IIIII",
            buf,
            0,
            self.vm_id,
            self.initial_chunk_count,
            self.chunk_size,
            self.max_chunks,
            self.target_in_flight,
        )
        struct.pack_into("<I", buf, 20, self.handle)
        struct.pack_into("<Q", buf, 24, self.tiler_heap_ctx_gpu_va)
        struct.pack_into("<Q", buf, 32, self.first_heap_chunk_gpu_va)
        return bytes(buf)


@dataclass
class SyncobjCreateIn:
    handle: int = 0
    flags: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SyncobjCreateIn:
        return cls(_u32(data, 0), _u32(data, 4))

    def pack(self) -> bytes:
        return struct.pack("<II", self.handle, self.flags)


@dataclass
class SyncobjCreateOut(SyncobjCreateIn):
    pass


@dataclass
class SyncobjTransferIn:
    src_handle: int = 0
    dst_handle: int = 0
    src_point: int = 0
    dst_point: int = 0
    flags: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SyncobjTransferIn:
        return cls(_u32(data, 0), _u32(data, 4), _u64(data, 8), _u64(data, 16), _u32(data, 24))

    def pack(self) -> bytes:
        return struct.pack("<IIQQI", self.src_handle, self.dst_handle,
                           self.src_point, self.dst_point, self.flags) + b"\x00" * 4


@dataclass
class SyncobjTimelineWaitIn:
    handles_ptr: int = 0
    points_ptr: int = 0
    timeout_nsec: int = -1
    count_handles: int = 0
    flags: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> SyncobjTimelineWaitIn:
        return cls(
            _u64(data, 0),
            _u64(data, 8),
            struct.unpack_from("<q", data, 16)[0],
            _u32(data, 24),
            _u32(data, 28),
        )

    def pack(self) -> bytes:
        buf = bytearray(48)
        struct.pack_into("<Q", buf, 0, self.handles_ptr)
        struct.pack_into("<Q", buf, 8, self.points_ptr)
        struct.pack_into("<q", buf, 16, self.timeout_nsec)
        struct.pack_into("<I", buf, 24, self.count_handles)
        struct.pack_into("<I", buf, 28, self.flags)
        return bytes(buf)


@dataclass
class GroupQueueCreate:
    """drm_panthor_queue_create sidecar (8 bytes)."""

    priority: int = 0
    ringbuf_size: int = 0

    @classmethod
    def from_bytes(cls, data: bytes) -> GroupQueueCreate:
        if len(data) < 8:
            raise ValueError(f"GroupQueueCreate expects 8 bytes, got {len(data)}")
        return cls(data[0], _u32(data, 4))

    def pack(self) -> bytes:
        buf = bytearray(8)
        buf[0] = self.priority & 0xFF
        struct.pack_into("<I", buf, 4, self.ringbuf_size)
        return bytes(buf)


@dataclass
class GemLoad:
    """BO snapshot before GROUP_SUBMIT."""

    handle: int
    gpu_va: int
    bo_offset: int
    data: bytes = field(repr=False)

    @property
    def head_hex(self) -> str:
        return self.data[:32].hex()


IOCTL_IN_DECODERS: dict[int, type] = {
    NR_VM_CREATE: VmCreateIn,
    NR_VM_BIND: VmBindIn,
    NR_BO_CREATE: BoCreateIn,
    NR_BO_MMAP: BoMmapIn,
    NR_GROUP_CREATE: GroupCreateIn,
    NR_GROUP_SUBMIT: GroupSubmitIn,
    NR_TILER_HEAP_CREATE: TilerHeapCreateIn,
    NR_SYNCOBJ_CREATE: SyncobjCreateIn,
    NR_SYNCOBJ_TRANSFER: SyncobjTransferIn,
    NR_SYNCOBJ_TIMELINE_WAIT: SyncobjTimelineWaitIn,
}

IOCTL_OUT_DECODERS: dict[int, type] = {
    NR_VM_CREATE: VmCreateOut,
    NR_VM_BIND: VmBindOut,
    NR_BO_CREATE: BoCreateOut,
    NR_BO_MMAP: BoMmapOut,
    NR_GROUP_CREATE: GroupCreateOut,
    NR_TILER_HEAP_CREATE: TilerHeapCreateOut,
    NR_SYNCOBJ_CREATE: SyncobjCreateOut,
}


def decode_ioctl_in(nr: int, data: bytes) -> Any | None:
    cls = IOCTL_IN_DECODERS.get(nr)
    if cls is None or not data:
        return None
    try:
        return cls.from_bytes(data)
    except (ValueError, struct.error):
        return None


def decode_ioctl_out(nr: int, data: bytes) -> Any | None:
    cls = IOCTL_OUT_DECODERS.get(nr)
    if cls is None or not data:
        return None
    try:
        return cls.from_bytes(data)
    except (ValueError, struct.error):
        return None


def ioctl_name(nr: int) -> str:
    return IOCTL_NAMES.get(nr, f"0x{nr:02x}")
