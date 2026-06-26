"""kbase ioctl numbers and ctypes layouts (CSF / Valhall v10, G610).

Derived from Arm mali_kbase_csf_ioctl.h (UK API 1.14). ioctl request values
use KBASE_IOCTL_TYPE = 0x80.
"""

from __future__ import annotations

import ctypes
import struct
from typing import Final

KBASE_IOCTL_TYPE: Final = 0x80


def _ioc(dir_: int, typ: int, nr: int, size: int) -> int:
    return (dir_ << 30) | (typ << 8) | nr | (size << 16)


def _iow(typ: int, nr: int, fmt: str) -> int:
    return _ioc(1, typ, nr, struct.calcsize(fmt))


def _ior(typ: int, nr: int, fmt: str) -> int:
    return _ioc(2, typ, nr, struct.calcsize(fmt))


def _iowr(typ: int, nr: int, fmt: str) -> int:
    return _ioc(3, typ, nr, struct.calcsize(fmt))


def _io(typ: int, nr: int) -> int:
    return _ioc(0, typ, nr, 0)


def _ioc_size(req: int) -> int:
    return (req >> 16) & 0x3FFF


def _ioc_nr(req: int) -> int:
    return req & 0xFF


# --- structs ---


class KbaseVersionCheck(ctypes.Structure):
    _fields_ = [("major", ctypes.c_uint16), ("minor", ctypes.c_uint16)]


class KbaseSetFlags(ctypes.Structure):
    _fields_ = [("create_flags", ctypes.c_uint32)]


class KbaseMemAllocIn(ctypes.Structure):
    _fields_ = [
        ("va_pages", ctypes.c_uint64),
        ("commit_pages", ctypes.c_uint64),
        ("extension", ctypes.c_uint64),
        ("flags", ctypes.c_uint64),
    ]


class KbaseMemAllocOut(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64), ("gpu_va", ctypes.c_uint64)]


class KbaseMemAlloc(ctypes.Structure):
    _fields_ = [("in_", KbaseMemAllocIn), ("out", KbaseMemAllocOut)]

    @property
    def in_fields(self) -> KbaseMemAllocIn:
        return self.in_

    @in_fields.setter
    def in_fields(self, v: KbaseMemAllocIn) -> None:
        self.in_ = v


class KbaseMemAllocExIn(ctypes.Structure):
    _fields_ = [
        ("va_pages", ctypes.c_uint64),
        ("commit_pages", ctypes.c_uint64),
        ("extension", ctypes.c_uint64),
        ("flags", ctypes.c_uint64),
        ("fixed_address", ctypes.c_uint64),
        ("extra", ctypes.c_uint64 * 3),
    ]


class KbaseMemAllocEx(ctypes.Structure):
    _fields_ = [("in_", KbaseMemAllocExIn), ("out", KbaseMemAllocOut)]


class KbaseCsQueueRegister(ctypes.Structure):
    _fields_ = [
        ("buffer_gpu_addr", ctypes.c_uint64),
        ("buffer_size", ctypes.c_uint32),
        ("priority", ctypes.c_uint8),
        ("padding", ctypes.c_uint8 * 3),
    ]


class KbaseCsQueueKick(ctypes.Structure):
    _fields_ = [("buffer_gpu_addr", ctypes.c_uint64)]


class KbaseCsQueueBindIn(ctypes.Structure):
    _fields_ = [
        ("buffer_gpu_addr", ctypes.c_uint64),
        ("group_handle", ctypes.c_uint8),
        ("csi_index", ctypes.c_uint8),
        ("padding", ctypes.c_uint8 * 6),
    ]


class KbaseCsQueueBindOut(ctypes.Structure):
    _fields_ = [("mmap_handle", ctypes.c_uint64)]


class KbaseCsQueueBind(ctypes.Structure):
    _fields_ = [("in_", KbaseCsQueueBindIn), ("out", KbaseCsQueueBindOut)]


class KbaseCsQueueGroupCreateIn(ctypes.Structure):
    _fields_ = [
        ("tiler_mask", ctypes.c_uint64),
        ("fragment_mask", ctypes.c_uint64),
        ("compute_mask", ctypes.c_uint64),
        ("cs_min", ctypes.c_uint8),
        ("priority", ctypes.c_uint8),
        ("tiler_max", ctypes.c_uint8),
        ("fragment_max", ctypes.c_uint8),
        ("compute_max", ctypes.c_uint8),
        ("csi_handlers", ctypes.c_uint8),
        ("padding", ctypes.c_uint8 * 2),
        ("reserved", ctypes.c_uint64),
    ]


class KbaseCsQueueGroupCreateOut(ctypes.Structure):
    _fields_ = [
        ("group_handle", ctypes.c_uint8),
        ("padding", ctypes.c_uint8 * 3),
        ("group_uid", ctypes.c_uint32),
    ]


class KbaseCsQueueGroupCreate(ctypes.Structure):
    _fields_ = [("in_", KbaseCsQueueGroupCreateIn), ("out", KbaseCsQueueGroupCreateOut)]


class KbaseCsGetGlbIfaceIn(ctypes.Structure):
    _fields_ = [
        ("max_group_num", ctypes.c_uint32),
        ("max_total_stream_num", ctypes.c_uint32),
        ("groups_ptr", ctypes.c_uint64),
        ("streams_ptr", ctypes.c_uint64),
    ]


class KbaseCsGetGlbIfaceOut(ctypes.Structure):
    _fields_ = [
        ("glb_version", ctypes.c_uint32),
        ("features", ctypes.c_uint32),
        ("group_num", ctypes.c_uint32),
        ("prfcnt_size", ctypes.c_uint32),
        ("total_stream_num", ctypes.c_uint32),
        ("instr_features", ctypes.c_uint32),
    ]


class KbaseCsGetGlbIface(ctypes.Structure):
    _fields_ = [("in_", KbaseCsGetGlbIfaceIn), ("out", KbaseCsGetGlbIfaceOut)]


# ioctl requests
IOCTL_VERSION_CHECK = _iowr(KBASE_IOCTL_TYPE, 52, "<HH")
IOCTL_SET_FLAGS = _iow(KBASE_IOCTL_TYPE, 1, "<I")
IOCTL_MEM_ALLOC = _iowr(KBASE_IOCTL_TYPE, 5, "<QQQQQQ")
IOCTL_MEM_ALLOC_EX = _iowr(KBASE_IOCTL_TYPE, 59, "<QQQQQQQQQQQQ")
IOCTL_CS_QUEUE_REGISTER = _iow(KBASE_IOCTL_TYPE, 36, "<QIB3x")
IOCTL_CS_QUEUE_KICK = _iow(KBASE_IOCTL_TYPE, 37, "<Q")
IOCTL_CS_QUEUE_BIND = _iowr(KBASE_IOCTL_TYPE, 39, "<QBB6xQ")
IOCTL_CS_QUEUE_GROUP_CREATE = _iowr(KBASE_IOCTL_TYPE, 58, "<QQQBBBBBB2xQQ")
IOCTL_CS_GET_GLB_IFACE = _iowr(KBASE_IOCTL_TYPE, 51, "<IIQQIIIIII")
IOCTL_CS_EVENT_SIGNAL = _io(KBASE_IOCTL_TYPE, 44)
IOCTL_GET_CONTEXT_ID = _ior(KBASE_IOCTL_TYPE, 17, "<I")
IOCTL_TLSTREAM_ACQUIRE = _iow(KBASE_IOCTL_TYPE, 18, "<I")

IOCTL_NAMES: dict[int, str] = {
    IOCTL_VERSION_CHECK: "VERSION_CHECK",
    IOCTL_SET_FLAGS: "SET_FLAGS",
    IOCTL_MEM_ALLOC: "MEM_ALLOC",
    IOCTL_MEM_ALLOC_EX: "MEM_ALLOC_EX",
    IOCTL_CS_QUEUE_REGISTER: "CS_QUEUE_REGISTER",
    IOCTL_CS_QUEUE_KICK: "CS_QUEUE_KICK",
    IOCTL_CS_QUEUE_BIND: "CS_QUEUE_BIND",
    IOCTL_CS_QUEUE_GROUP_CREATE: "CS_QUEUE_GROUP_CREATE",
    IOCTL_CS_GET_GLB_IFACE: "CS_GET_GLB_IFACE",
    IOCTL_CS_EVENT_SIGNAL: "CS_EVENT_SIGNAL",
    IOCTL_GET_CONTEXT_ID: "GET_CONTEXT_ID",
    IOCTL_TLSTREAM_ACQUIRE: "TLSTREAM_ACQUIRE",
}


def ioctl_name(req: int) -> str:
    nr = _ioc_nr(req)
    named = IOCTL_NAMES.get(req)
    if named:
        return named
    for k, v in IOCTL_NAMES.items():
        if _ioc_nr(k) == nr:
            return f"{v}?"
    return f"ioctl_{nr}"
