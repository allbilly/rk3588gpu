"""High-level Panthor DRM helpers for buffer allocation and job submit."""

from __future__ import annotations

import ctypes
import mmap
import os
from dataclasses import dataclass

from panthor_dev import PanthorDevice
from panthor_ioctl import (
    DRM_PANTHOR_DEV_QUERY_GPU_INFO,
    DRM_PANTHOR_SYNC_OP_SIGNAL,
    DRM_PANTHOR_VM_BIND_OP_TYPE_MAP,
    PANTHOR_GROUP_PRIORITY_MEDIUM,
    DrmGemClose,
    DrmPanthorBoCreate,
    DrmPanthorBoMmapOffset,
    DrmPanthorDevQuery,
    DrmPanthorGpuInfo,
    DrmPanthorGroupCreate,
    DrmPanthorGroupDestroy,
    DrmPanthorGroupSubmit,
    DrmPanthorQueueCreate,
    DrmPanthorQueueSubmit,
    DrmPanthorSyncOp,
    DrmPanthorVmBind,
    DrmPanthorVmBindOp,
    DrmPanthorVmCreate,
    DrmPanthorVmDestroy,
    DrmPrimeHandle,
    DrmSyncobjCreate,
    DrmSyncobjDestroy,
    DrmSyncobjWait,
    IOCTL_GEM_CLOSE,
    IOCTL_PANTHOR_BO_CREATE,
    IOCTL_PANTHOR_BO_MMAP_OFFSET,
    IOCTL_PANTHOR_DEV_QUERY,
    IOCTL_PANTHOR_GROUP_CREATE,
    IOCTL_PANTHOR_GROUP_DESTROY,
    IOCTL_PANTHOR_GROUP_SUBMIT,
    IOCTL_PANTHOR_VM_BIND,
    IOCTL_PANTHOR_VM_CREATE,
    IOCTL_PANTHOR_VM_DESTROY,
    IOCTL_PRIME_HANDLE_TO_FD,
    IOCTL_SYNCOBJ_CREATE,
    IOCTL_SYNCOBJ_DESTROY,
    IOCTL_SYNCOBJ_WAIT,
    obj_array,
)

PAGE_SIZE = 4096

DMA_BUF_SYNC_START = 1 << 0
DMA_BUF_SYNC_END = 1 << 1
DMA_BUF_SYNC_WRITE = 1 << 2
DMA_BUF_IOCTL_SYNC = (1 << 30) | (8 << 16) | (ord("b") << 8) | 0


class DrmDmaBufSync(ctypes.Structure):
    _fields_ = [("flags", ctypes.c_uint64)]


def _dma_buf_sync(fd: int, flags: int) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
    libc.ioctl.restype = ctypes.c_int
    arg = DrmDmaBufSync(flags=flags)
    if libc.ioctl(fd, DMA_BUF_IOCTL_SYNC, ctypes.byref(arg)) < 0:
        err = ctypes.get_errno()
        raise OSError(err, os.strerror(err), "DMA_BUF_IOCTL_SYNC")


def first_core_mask(present: int) -> int:
    if present == 0:
        return 0
    return 1 << ((present & -present).bit_length() - 1)


@dataclass
class PanthorBo:
    handle: int
    size: int
    va: int
    map: mmap.mmap | None = None

    def close(self, dev: PanthorDevice) -> None:
        if self.map is not None:
            self.map.close()
            self.map = None
        if self.handle:
            dev.ioctl(IOCTL_GEM_CLOSE, DrmGemClose(handle=self.handle))
            self.handle = 0


class PanthorSession:
    def __init__(self, dev: PanthorDevice) -> None:
        self.dev = dev
        self.vm_id = 0
        self.group_handle = 0
        self._syncobj = 0
        self._gpu = DrmPanthorGpuInfo()

    def __enter__(self) -> PanthorSession:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def close(self) -> None:
        if self.group_handle:
            self.dev.ioctl(IOCTL_PANTHOR_GROUP_DESTROY, DrmPanthorGroupDestroy(group_handle=self.group_handle))
            self.group_handle = 0
        if self._syncobj:
            self.dev.ioctl(IOCTL_SYNCOBJ_DESTROY, DrmSyncobjDestroy(handle=self._syncobj))
            self._syncobj = 0
        if self.vm_id:
            self.dev.ioctl(IOCTL_PANTHOR_VM_DESTROY, DrmPanthorVmDestroy(id=self.vm_id))
            self.vm_id = 0

    def init(self) -> DrmPanthorGpuInfo:
        gpu = DrmPanthorGpuInfo()
        q = DrmPanthorDevQuery(
            type=DRM_PANTHOR_DEV_QUERY_GPU_INFO,
            size=ctypes.sizeof(gpu),
            pointer=ctypes.addressof(gpu),
        )
        self.dev.ioctl(IOCTL_PANTHOR_DEV_QUERY, q)

        vm = DrmPanthorVmCreate()
        self.dev.ioctl(IOCTL_PANTHOR_VM_CREATE, vm)
        self.vm_id = vm.id

        sync = DrmSyncobjCreate()
        self.dev.ioctl(IOCTL_SYNCOBJ_CREATE, sync)
        self._syncobj = sync.handle
        self._gpu = gpu
        return gpu

    def create_group(self) -> None:
        if self.group_handle:
            return
        gpu = self._gpu
        queue = DrmPanthorQueueCreate(priority=0, ringbuf_size=PAGE_SIZE)
        queues = obj_array(1, queue)
        grp = DrmPanthorGroupCreate(
            queues=queues,
            max_compute_cores=1,
            max_fragment_cores=1,
            max_tiler_cores=1,
            priority=PANTHOR_GROUP_PRIORITY_MEDIUM,
            compute_core_mask=first_core_mask(gpu.shader_present),
            fragment_core_mask=first_core_mask(gpu.shader_present),
            tiler_core_mask=first_core_mask(gpu.tiler_present),
            vm_id=self.vm_id,
        )
        self.dev.ioctl(IOCTL_PANTHOR_GROUP_CREATE, grp)
        self.group_handle = grp.group_handle

    def _prime_fd(self, handle: int) -> int:
        prime = DrmPrimeHandle(handle=handle, flags=0)
        self.dev.ioctl(IOCTL_PRIME_HANDLE_TO_FD, prime)
        return prime.fd

    def sync_bo_for_device(self, bo: PanthorBo) -> None:
        fd = self._prime_fd(bo.handle)
        try:
            _dma_buf_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE)
        finally:
            os.close(fd)

    def sync_bo_for_cpu(self, bo: PanthorBo) -> None:
        fd = self._prime_fd(bo.handle)
        try:
            _dma_buf_sync(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_END)
        finally:
            os.close(fd)

    def create_bo(self, size: int, va: int) -> PanthorBo:
        size = (size + PAGE_SIZE - 1) & ~(PAGE_SIZE - 1)
        create = DrmPanthorBoCreate(size=size, flags=0)
        self.dev.ioctl(IOCTL_PANTHOR_BO_CREATE, create)

        op = DrmPanthorVmBindOp(
            flags=DRM_PANTHOR_VM_BIND_OP_TYPE_MAP,
            bo_handle=create.handle,
            va=va,
            size=create.size,
        )
        bind = DrmPanthorVmBind(vm_id=self.vm_id, ops=obj_array(1, op))
        self.dev.ioctl(IOCTL_PANTHOR_VM_BIND, bind)

        off = DrmPanthorBoMmapOffset(handle=create.handle)
        self.dev.ioctl(IOCTL_PANTHOR_BO_MMAP_OFFSET, off)

        mm = mmap.mmap(
            self.dev.fd,
            create.size,
            mmap.MAP_SHARED,
            mmap.PROT_READ | mmap.PROT_WRITE,
            offset=off.offset,
        )
        return PanthorBo(handle=create.handle, size=create.size, va=va, map=mm)

    def submit_cs(self, stream_addr: int, stream_size: int, *bos: PanthorBo) -> None:
        for bo in bos:
            self.sync_bo_for_device(bo)
        self.create_group()
        sync = DrmPanthorSyncOp(flags=DRM_PANTHOR_SYNC_OP_SIGNAL, handle=self._syncobj)
        qs = DrmPanthorQueueSubmit(
            queue_index=0,
            stream_size=stream_size,
            stream_addr=stream_addr,
            latest_flush=1,
            syncs=obj_array(1, sync),
        )
        gs = DrmPanthorGroupSubmit(group_handle=self.group_handle, queue_submits=obj_array(1, qs))
        self.dev.ioctl(IOCTL_PANTHOR_GROUP_SUBMIT, gs)

        handle_arr = (ctypes.c_uint32 * 1)(self._syncobj)
        wait = DrmSyncobjWait(
            handles=ctypes.addressof(handle_arr),
            timeout_nsec=-1,
            count_handles=1,
        )
        self.dev.ioctl(IOCTL_SYNCOBJ_WAIT, wait)

    @staticmethod
    def write_u32_array(bo: PanthorBo, values: tuple[int, ...]) -> None:
        assert bo.map is not None
        for i, v in enumerate(values):
            bo.map[i * 4 : (i + 1) * 4] = int(v).to_bytes(4, "little")

    @staticmethod
    def read_u32_array(bo: PanthorBo, count: int) -> list[int]:
        assert bo.map is not None
        out = []
        for i in range(count):
            out.append(int.from_bytes(bo.map[i * 4 : (i + 1) * 4], "little"))
        return out
