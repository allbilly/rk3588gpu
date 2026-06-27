"""Panthor DRM ioctl numbers and ctypes layouts (mainline Mali CSF)."""

from __future__ import annotations

import ctypes
from typing import Final

DRM_COMMAND_BASE: Final = 0x40
DRM_IOCTL_TYPE: Final = ord("d")

DRM_PANTHOR_DEV_QUERY = 0
DRM_PANTHOR_VM_CREATE = 1
DRM_PANTHOR_VM_DESTROY = 2
DRM_PANTHOR_VM_BIND = 3
DRM_PANTHOR_BO_CREATE = 5
DRM_PANTHOR_BO_MMAP_OFFSET = 6
DRM_PANTHOR_GROUP_CREATE = 7
DRM_PANTHOR_GROUP_DESTROY = 8
DRM_PANTHOR_GROUP_SUBMIT = 9
DRM_PANTHOR_BO_SYNC = 15

DRM_PANTHOR_BO_SYNC_CPU_CACHE_FLUSH = 0

DRM_PANTHOR_DEV_QUERY_GPU_INFO = 0
DRM_PANTHOR_DEV_QUERY_CSIF_INFO = 1

DRM_PANTHOR_VM_BIND_OP_TYPE_MAP = 0 << 28

PANTHOR_GROUP_PRIORITY_MEDIUM = 1

DRM_PANTHOR_SYNC_OP_HANDLE_TYPE_SYNCOBJ = 0
DRM_PANTHOR_SYNC_OP_SIGNAL = 1 << 31

DRM_IOCTL_GEM_CLOSE_NR = 0x09
DRM_IOCTL_SYNCOBJ_CREATE_NR = 0xBF
DRM_IOCTL_SYNCOBJ_DESTROY_NR = 0xC0
DRM_IOCTL_SYNCOBJ_WAIT_NR = 0xC3


def _ioc(dir_: int, nr: int, size: int) -> int:
    return (dir_ << 30) | (size << 16) | (DRM_IOCTL_TYPE << 8) | (DRM_COMMAND_BASE + nr)


def _iow(nr: int, size: int) -> int:
    return _ioc(1, nr, size)


def _iowr(nr: int, size: int) -> int:
    return _ioc(3, nr, size)


def _drm_iowr(nr: int, size: int) -> int:
    return (3 << 30) | (size << 16) | (DRM_IOCTL_TYPE << 8) | nr


def _ioc_size(req: int) -> int:
    return (req >> 16) & 0x3FFF


class DrmPanthorObjArray(ctypes.Structure):
    _fields_ = [
        ("stride", ctypes.c_uint32),
        ("count", ctypes.c_uint32),
        ("array", ctypes.c_uint64),
    ]


def obj_array(count: int, ptr: ctypes.Array | ctypes.Structure) -> DrmPanthorObjArray:
    return DrmPanthorObjArray(stride=ctypes.sizeof(type(ptr)), count=count, array=ctypes.addressof(ptr))


class DrmPanthorGpuInfo(ctypes.Structure):
    _fields_ = [
        ("gpu_id", ctypes.c_uint32),
        ("gpu_rev", ctypes.c_uint32),
        ("csf_id", ctypes.c_uint32),
        ("l2_features", ctypes.c_uint32),
        ("tiler_features", ctypes.c_uint32),
        ("mem_features", ctypes.c_uint32),
        ("mmu_features", ctypes.c_uint32),
        ("thread_features", ctypes.c_uint32),
        ("max_threads", ctypes.c_uint32),
        ("thread_max_workgroup_size", ctypes.c_uint32),
        ("thread_max_barrier_size", ctypes.c_uint32),
        ("coherency_features", ctypes.c_uint32),
        ("texture_features", ctypes.c_uint32 * 4),
        ("as_present", ctypes.c_uint32),
        ("selected_coherency", ctypes.c_uint32),
        ("shader_present", ctypes.c_uint64),
        ("l2_present", ctypes.c_uint64),
        ("tiler_present", ctypes.c_uint64),
        ("core_features", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
        ("gpu_features", ctypes.c_uint64),
    ]


class DrmPanthorCsifInfo(ctypes.Structure):
    _fields_ = [
        ("csg_slot_count", ctypes.c_uint32),
        ("cs_slot_count", ctypes.c_uint32),
        ("cs_reg_count", ctypes.c_uint32),
        ("scoreboard_slot_count", ctypes.c_uint32),
        ("unpreserved_cs_reg_count", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
    ]


class DrmPanthorDevQuery(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_uint32),
        ("size", ctypes.c_uint32),
        ("pointer", ctypes.c_uint64),
    ]


class DrmPanthorVmCreate(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("id", ctypes.c_uint32),
        ("user_va_range", ctypes.c_uint64),
    ]


class DrmPanthorVmDestroy(ctypes.Structure):
    _fields_ = [("id", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class DrmPanthorVmBindOp(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("bo_handle", ctypes.c_uint32),
        ("bo_offset", ctypes.c_uint64),
        ("va", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
        ("syncs", DrmPanthorObjArray),
    ]


class DrmPanthorVmBind(ctypes.Structure):
    _fields_ = [
        ("vm_id", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("ops", DrmPanthorObjArray),
    ]


class DrmPanthorBoCreate(ctypes.Structure):
    _fields_ = [
        ("size", ctypes.c_uint64),
        ("flags", ctypes.c_uint32),
        ("exclusive_vm_id", ctypes.c_uint32),
        ("handle", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
    ]


class DrmPanthorBoMmapOffset(ctypes.Structure):
    _fields_ = [
        ("handle", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
        ("offset", ctypes.c_uint64),
    ]


class DrmPanthorQueueCreate(ctypes.Structure):
    _fields_ = [
        ("priority", ctypes.c_uint8),
        ("pad", ctypes.c_uint8 * 3),
        ("ringbuf_size", ctypes.c_uint32),
    ]


class DrmPanthorGroupCreate(ctypes.Structure):
    _fields_ = [
        ("queues", DrmPanthorObjArray),
        ("max_compute_cores", ctypes.c_uint8),
        ("max_fragment_cores", ctypes.c_uint8),
        ("max_tiler_cores", ctypes.c_uint8),
        ("priority", ctypes.c_uint8),
        ("pad", ctypes.c_uint32),
        ("compute_core_mask", ctypes.c_uint64),
        ("fragment_core_mask", ctypes.c_uint64),
        ("tiler_core_mask", ctypes.c_uint64),
        ("vm_id", ctypes.c_uint32),
        ("group_handle", ctypes.c_uint32),
    ]


class DrmPanthorGroupDestroy(ctypes.Structure):
    _fields_ = [("group_handle", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class DrmPanthorSyncOp(ctypes.Structure):
    _fields_ = [
        ("flags", ctypes.c_uint32),
        ("handle", ctypes.c_uint32),
        ("timeline_value", ctypes.c_uint64),
    ]


class DrmPanthorQueueSubmit(ctypes.Structure):
    _fields_ = [
        ("queue_index", ctypes.c_uint32),
        ("stream_size", ctypes.c_uint32),
        ("stream_addr", ctypes.c_uint64),
        ("latest_flush", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
        ("syncs", DrmPanthorObjArray),
    ]


class DrmPanthorGroupSubmit(ctypes.Structure):
    _fields_ = [
        ("group_handle", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
        ("queue_submits", DrmPanthorObjArray),
    ]


class DrmPanthorBoSyncOp(ctypes.Structure):
    _fields_ = [
        ("handle", ctypes.c_uint32),
        ("type", ctypes.c_uint32),
        ("offset", ctypes.c_uint64),
        ("size", ctypes.c_uint64),
    ]


class DrmPanthorBoSync(ctypes.Structure):
    _fields_ = [("ops", DrmPanthorObjArray)]


class DrmGemClose(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class DrmPrimeHandle(ctypes.Structure):
    _fields_ = [
        ("handle", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("fd", ctypes.c_int32),
        ("pad", ctypes.c_uint32),
    ]


class DrmSyncobjCreate(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32), ("flags", ctypes.c_uint32)]


class DrmSyncobjDestroy(ctypes.Structure):
    _fields_ = [("handle", ctypes.c_uint32), ("pad", ctypes.c_uint32)]


class DrmSyncobjWait(ctypes.Structure):
    _fields_ = [
        ("handles", ctypes.c_uint64),
        ("timeout_nsec", ctypes.c_int64),
        ("count_handles", ctypes.c_uint32),
        ("flags", ctypes.c_uint32),
        ("first_signaled", ctypes.c_uint32),
        ("pad", ctypes.c_uint32),
        ("deadline_nsec", ctypes.c_uint64),
    ]


IOCTL_PANTHOR_DEV_QUERY = _iowr(DRM_PANTHOR_DEV_QUERY, ctypes.sizeof(DrmPanthorDevQuery))
IOCTL_PANTHOR_VM_CREATE = _iowr(DRM_PANTHOR_VM_CREATE, ctypes.sizeof(DrmPanthorVmCreate))
IOCTL_PANTHOR_VM_DESTROY = _iowr(DRM_PANTHOR_VM_DESTROY, ctypes.sizeof(DrmPanthorVmDestroy))
IOCTL_PANTHOR_VM_BIND = _iowr(DRM_PANTHOR_VM_BIND, ctypes.sizeof(DrmPanthorVmBind))
IOCTL_PANTHOR_BO_CREATE = _iowr(DRM_PANTHOR_BO_CREATE, ctypes.sizeof(DrmPanthorBoCreate))
IOCTL_PANTHOR_BO_MMAP_OFFSET = _iowr(DRM_PANTHOR_BO_MMAP_OFFSET, ctypes.sizeof(DrmPanthorBoMmapOffset))
IOCTL_PANTHOR_GROUP_CREATE = _iowr(DRM_PANTHOR_GROUP_CREATE, ctypes.sizeof(DrmPanthorGroupCreate))
IOCTL_PANTHOR_GROUP_DESTROY = _iowr(DRM_PANTHOR_GROUP_DESTROY, ctypes.sizeof(DrmPanthorGroupDestroy))
IOCTL_PANTHOR_GROUP_SUBMIT = _iowr(DRM_PANTHOR_GROUP_SUBMIT, ctypes.sizeof(DrmPanthorGroupSubmit))
IOCTL_PANTHOR_BO_SYNC = _iowr(DRM_PANTHOR_BO_SYNC, ctypes.sizeof(DrmPanthorBoSync))

IOCTL_GEM_CLOSE = _drm_iowr(DRM_IOCTL_GEM_CLOSE_NR, ctypes.sizeof(DrmGemClose))
IOCTL_PRIME_HANDLE_TO_FD = _drm_iowr(0x2D, ctypes.sizeof(DrmPrimeHandle))
IOCTL_SYNCOBJ_CREATE = _drm_iowr(DRM_IOCTL_SYNCOBJ_CREATE_NR, ctypes.sizeof(DrmSyncobjCreate))
IOCTL_SYNCOBJ_DESTROY = _drm_iowr(DRM_IOCTL_SYNCOBJ_DESTROY_NR, ctypes.sizeof(DrmSyncobjDestroy))
IOCTL_SYNCOBJ_WAIT = _drm_iowr(DRM_IOCTL_SYNCOBJ_WAIT_NR, ctypes.sizeof(DrmSyncobjWait))
