"""Decode kbase ioctl blobs from Mali captures into named structures."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from kbase_ioctl import (
    IOCTL_CS_GET_GLB_IFACE,
    IOCTL_CS_QUEUE_BIND,
    IOCTL_CS_QUEUE_GROUP_CREATE,
    IOCTL_CS_QUEUE_KICK,
    IOCTL_CS_QUEUE_REGISTER,
    IOCTL_MEM_ALLOC,
    IOCTL_MEM_ALLOC_EX,
    IOCTL_SET_FLAGS,
    IOCTL_VERSION_CHECK,
    KbaseCsGetGlbIface,
    KbaseCsQueueBind,
    KbaseCsQueueGroupCreate,
    KbaseCsQueueKick,
    KbaseCsQueueRegister,
    KbaseMemAlloc,
    KbaseMemAllocEx,
    KbaseSetFlags,
    KbaseVersionCheck,
)


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _u64(buf: bytes, off: int) -> int:
    return struct.unpack_from("<Q", buf, off)[0]


@dataclass
class VersionCheck:
    major: int
    minor: int

    @classmethod
    def from_bytes(cls, data: bytes) -> VersionCheck:
        if len(data) < 4:
            raise ValueError(f"VersionCheck expects >=4 bytes, got {len(data)}")
        major, minor = struct.unpack_from("<HH", data, 0)
        return cls(major, minor)

    def pack(self) -> bytes:
        return struct.pack("<HH", self.major, self.minor)


@dataclass
class SetFlags:
    create_flags: int

    @classmethod
    def from_bytes(cls, data: bytes) -> SetFlags:
        return cls(_u32(data, 0) if data else 0)

    def pack(self) -> bytes:
        return struct.pack("<I", self.create_flags)


@dataclass
class MemAllocIn:
    va_pages: int
    commit_pages: int
    extension: int
    flags: int

    @classmethod
    def from_bytes(cls, data: bytes) -> MemAllocIn:
        if len(data) < 32:
            raise ValueError(f"MemAllocIn expects 32 bytes, got {len(data)}")
        return cls(_u64(data, 0), _u64(data, 8), _u64(data, 16), _u64(data, 24))

    def pack(self) -> bytes:
        return struct.pack("<QQQQ", self.va_pages, self.commit_pages, self.extension, self.flags)


@dataclass
class MemAllocOut:
    flags: int
    gpu_va: int

    @classmethod
    def from_bytes(cls, data: bytes) -> MemAllocOut:
        if len(data) < 16:
            raise ValueError(f"MemAllocOut expects 16 bytes, got {len(data)}")
        return cls(_u64(data, 0), _u64(data, 8))

    def pack(self) -> bytes:
        return struct.pack("<QQ", self.flags, self.gpu_va)


@dataclass
class CsQueueRegister:
    buffer_gpu_addr: int
    buffer_size: int
    priority: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueRegister:
        if len(data) < 16:
            raise ValueError(f"CsQueueRegister expects 16 bytes, got {len(data)}")
        addr, size = struct.unpack_from("<QI", data, 0)
        priority = data[12]
        return cls(addr, size, priority)

    def pack(self) -> bytes:
        return struct.pack("<QIB3x", self.buffer_gpu_addr, self.buffer_size, self.priority)


@dataclass
class CsQueueKick:
    buffer_gpu_addr: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueKick:
        return cls(_u64(data, 0) if data else 0)

    def pack(self) -> bytes:
        return struct.pack("<Q", self.buffer_gpu_addr)


@dataclass
class CsQueueBindIn:
    buffer_gpu_addr: int
    group_handle: int
    csi_index: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueBindIn:
        if len(data) < 16:
            raise ValueError(f"CsQueueBindIn expects 16 bytes, got {len(data)}")
        addr, = struct.unpack_from("<Q", data, 0)
        return cls(addr, data[8], data[9])

    def pack(self) -> bytes:
        return struct.pack("<QBB6x", self.buffer_gpu_addr, self.group_handle, self.csi_index)


@dataclass
class CsQueueBindOut:
    mmap_handle: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueBindOut:
        return cls(_u64(data, 0) if data else 0)

    def pack(self) -> bytes:
        return struct.pack("<Q", self.mmap_handle)


@dataclass
class CsQueueGroupCreateIn:
    tiler_mask: int
    fragment_mask: int
    compute_mask: int
    cs_min: int
    priority: int
    tiler_max: int
    fragment_max: int
    compute_max: int
    csi_handlers: int
    reserved: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueGroupCreateIn:
        if len(data) < 40:
            raise ValueError(f"CsQueueGroupCreateIn expects 40 bytes, got {len(data)}")
        tiler, frag, comp = struct.unpack_from("<QQQ", data, 0)
        return cls(
            tiler,
            frag,
            comp,
            data[24],
            data[25],
            data[26],
            data[27],
            data[28],
            data[29],
            _u64(data, 32),
        )

    def pack(self) -> bytes:
        return struct.pack(
            "<QQQBBBBBB2xQ",
            self.tiler_mask,
            self.fragment_mask,
            self.compute_mask,
            self.cs_min,
            self.priority,
            self.tiler_max,
            self.fragment_max,
            self.compute_max,
            self.csi_handlers,
            self.reserved,
        )


@dataclass
class CsQueueGroupCreateOut:
    group_handle: int
    group_uid: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsQueueGroupCreateOut:
        if len(data) < 8:
            raise ValueError(f"CsQueueGroupCreateOut expects 8 bytes, got {len(data)}")
        handle = data[0]
        uid, = struct.unpack_from("<I", data, 4)
        return cls(handle, uid)

    def pack(self) -> bytes:
        return struct.pack("<B3xI", self.group_handle, self.group_uid)


@dataclass
class CsGetGlbIfaceOut:
    glb_version: int
    features: int
    group_num: int
    prfcnt_size: int
    total_stream_num: int
    instr_features: int

    @classmethod
    def from_bytes(cls, data: bytes) -> CsGetGlbIfaceOut:
        if len(data) < 24:
            raise ValueError(f"CsGetGlbIfaceOut expects 24 bytes, got {len(data)}")
        vals = struct.unpack_from("<6I", data, 0)
        return cls(*vals)


DECODERS_IN: dict[int, type] = {
    IOCTL_VERSION_CHECK: VersionCheck,
    IOCTL_SET_FLAGS: SetFlags,
    IOCTL_MEM_ALLOC: MemAllocIn,
    IOCTL_MEM_ALLOC_EX: MemAllocIn,  # first 32 bytes match
    IOCTL_CS_QUEUE_REGISTER: CsQueueRegister,
    IOCTL_CS_QUEUE_KICK: CsQueueKick,
    IOCTL_CS_QUEUE_BIND: CsQueueBindIn,
    IOCTL_CS_QUEUE_GROUP_CREATE: CsQueueGroupCreateIn,
}

DECODERS_OUT: dict[int, type] = {
    IOCTL_VERSION_CHECK: VersionCheck,
    IOCTL_MEM_ALLOC: MemAllocOut,
    IOCTL_MEM_ALLOC_EX: MemAllocOut,
    IOCTL_CS_QUEUE_BIND: CsQueueBindOut,
    IOCTL_CS_QUEUE_GROUP_CREATE: CsQueueGroupCreateOut,
    IOCTL_CS_GET_GLB_IFACE: CsGetGlbIfaceOut,
}


def decode_ioctl_in(request: int, data: bytes) -> object | None:
    cls = DECODERS_IN.get(request)
    if cls is None:
        return None
    return cls.from_bytes(data)


def decode_ioctl_out(request: int, data: bytes) -> object | None:
    cls = DECODERS_OUT.get(request)
    if cls is None:
        return None
    return cls.from_bytes(data)


def repr_value(obj: object) -> str:
    if obj is None:
        return "None"
    if hasattr(obj, "__dataclass_fields__"):
        parts = [f"{k}={getattr(obj, k)!r}" for k in obj.__dataclass_fields__]
        return f"{type(obj).__name__}({', '.join(parts)})"
    return repr(obj)
