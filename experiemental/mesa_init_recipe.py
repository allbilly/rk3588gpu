"""Mesa/rusticl init + vadd recipe from add_cl2.pcap (generated)."""

from __future__ import annotations

from dataclasses import dataclass, field

from panthor_cap_decode import (
    BoCreateIn,
    BoCreateOut,
    BoMmapIn,
    BoMmapOut,
    GroupQueueCreate,
    GroupSubmitIn,
    QueueSubmit,
    SyncOp,
    SyncobjCreateIn,
    SyncobjCreateOut,
    SyncobjTransferIn,
    SyncobjTimelineWaitIn,
    TilerHeapCreateIn,
    TilerHeapCreateOut,
    VmBindIn,
    VmBindOp,
    VmCreateIn,
    VmCreateOut,
)

PANT_SIDE_VM_BIND_OPS = 1
PANT_SIDE_QUEUE_SUBMITS = 2
PANT_SIDE_GROUP_QUEUES = 3
PANT_SIDE_SYNC_OPS = 4
PANT_SIDE_BIND_SYNC_OPS = 6
PANT_SIDE_SYNCOBJ_HANDLES = 7
PANT_SIDE_SYNCOBJ_POINTS = 8


@dataclass
class IoctlStep:
    nr: int
    request: int
    arg: object | None = None
    arg_raw: bytes | None = None
    cap_out: object | None = None
    cap_out_raw: bytes | None = None
    sides: list[tuple[int, object]] = field(default_factory=list)


@dataclass
class GemZeros:
    cap_handle: int
    gpu_va: int
    size: int


@dataclass
class GemU32s:
    cap_handle: int
    gpu_va: int
    values: str


@dataclass
class GemConst:
    cap_handle: int
    gpu_va: int
    bo_offset: int
    blob: str


GemStep = GemZeros | GemU32s | GemConst
RecipeStep = GemStep | IoctlStep


MESA_INIT_STEPS: list[RecipeStep] = [
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=1, flags=1),
    ),
    # VM_CREATE
    IoctlStep(nr=65, request=0xc0106441,
        arg=VmCreateIn(user_va_range=0x800000000000),
        cap_out=VmCreateOut(id=1, user_va_range=0x800000000000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=1),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000048af04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=1, va=0x7FFFFFFFF000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=1),
        cap_out=BoMmapOut(handle=1, offset=0x1000B0000),
    ),
    # 0x0c
    IoctlStep(nr=12, request=0xc010640c,
        arg_raw=bytes.fromhex('05000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('05000000000000000300000000000000'),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=2),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a8ab04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=2, va=0x7FFFFFFFE000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=2),
        cap_out=BoMmapOut(handle=2, offset=0x1000B1000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=2, flags=1),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=3),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89e04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=3, va=0x7FFFFFFFD000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=3),
        cap_out=BoMmapOut(handle=3, offset=0x1000B2000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=4),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89e04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=4, va=0x7FFFFFFFC000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=4),
        cap_out=BoMmapOut(handle=4, offset=0x1000B3000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=3),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=16384, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=16384, exclusive_vm_id=1, handle=5),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000f89e04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=5, va=0x7FFFFFFF8000, size=16384, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=5),
        cap_out=BoMmapOut(handle=5, offset=0x1000B4000),
    ),
    # GROUP_CREATE
    IoctlStep(nr=71, request=0xc0386447,
        arg_raw=bytes.fromhex('0800000001000000009d04feffff000004040101000000000500050000000000050005000000000001000000000000000100000000000000'),
        cap_out_raw=bytes.fromhex('0800000001000000009d04feffff000004040101000000000500050000000000050005000000000001000000000000000100000001000000'),
        sides=[
            (PANT_SIDE_GROUP_QUEUES, GroupQueueCreate(priority=1, ringbuf_size=0x10000)),
        ],
    ),
    # TILER_HEAP_CREATE
    IoctlStep(nr=75, request=0xc028644b,
        arg=TilerHeapCreateIn(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535),
        cap_out=TilerHeapCreateOut(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535, handle=0xA00000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=6),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89704feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=6, va=0x7FFFFFFF7000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=6),
        cap_out=BoMmapOut(handle=6, offset=0x100ADF000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, flags=1, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, flags=1, exclusive_vm_id=1, handle=7),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89704feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=7, va=0x7FFFFFFE7000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=8),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89704feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=8, va=0x7FFFFFFE6000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=8),
        cap_out=BoMmapOut(handle=8, offset=0x100AF0000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=9),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89704feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=9, va=0x7FFFFFFE5000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=9),
        cap_out=BoMmapOut(handle=9, offset=0x100AF1000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=10),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000a89704feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=10, va=0x7FFFFFFE4000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=10),
        cap_out=BoMmapOut(handle=10, offset=0x100AF2000),
    ),
    GemConst(cap_handle=0x1, gpu_va=0x7ffffffff000, bo_offset=0, blob="MESA_BO_FFFFF000"),
    GemConst(cap_handle=0x2, gpu_va=0x7fffffffe000, bo_offset=0, blob="MESA_BO_FFFFE000"),
    GemZeros(cap_handle=0x3, gpu_va=0x7fffffffd000, size=4096),
    GemZeros(cap_handle=0x4, gpu_va=0x7fffffffc000, size=4096),
    GemConst(cap_handle=0x5, gpu_va=0x7fffffff8000, bo_offset=0, blob="MESA_BO_FFFF8000"),
    GemConst(cap_handle=0x6, gpu_va=0x7fffffff7000, bo_offset=0, blob="MESA_BO_FFFF7000"),
    GemConst(cap_handle=0x8, gpu_va=0x7ffffffe6000, bo_offset=0, blob="MESA_INIT_CS_0"),
    GemConst(cap_handle=0x9, gpu_va=0x7ffffffe5000, bo_offset=0, blob="MESA_BO_FFFE5000"),
    GemZeros(cap_handle=0xa, gpu_va=0x7ffffffe4000, size=4096),
    # GROUP_SUBMIT
    IoctlStep(nr=73, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=1, qs_stride=40, qs_count=1),
        cap_out_raw=bytes.fromhex('01000000000000002800000001000000689c04feffff0000'),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=40, stream_addr=0x7FFFFFFE6000, latest_flush=0xFFFFE0, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=0x80000000, handle=2)),
        ],
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('c0260f2900000000ffffffffffffff7f010000000000000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('c0260f2900000000ffffffffffffff7f010000000000000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (2,)),
        ],
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(flags=1),
        cap_out=SyncobjCreateOut(handle=4, flags=1),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=8),
        cap_out=BoMmapOut(handle=8, offset=0x100AF0000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=11),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078c504feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=1, bo_handle=11, va=0x7FFFFFFE3000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=11),
        cap_out=BoMmapOut(handle=11, offset=0x100AF3000),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=5),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=16384, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=16384, exclusive_vm_id=1, handle=12),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('01000000000000003000000001000000c8c504feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=12, va=0x7FFFFFFDF000, size=16384, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=12),
        cap_out=BoMmapOut(handle=12, offset=0x100AF4000),
    ),
    # GROUP_CREATE
    IoctlStep(nr=71, request=0xc0386447,
        arg_raw=bytes.fromhex('0800000001000000d0c304feffff000004040101000000000500050000000000050005000000000001000000000000000100000000000000'),
        cap_out_raw=bytes.fromhex('0800000001000000d0c304feffff000004040101000000000500050000000000050005000000000001000000000000000100000002000000'),
        sides=[
            (PANT_SIDE_GROUP_QUEUES, GroupQueueCreate(priority=1, ringbuf_size=0x10000)),
        ],
    ),
    # TILER_HEAP_CREATE
    IoctlStep(nr=75, request=0xc028644b,
        arg=TilerHeapCreateIn(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535),
        cap_out=TilerHeapCreateOut(vm_id=1, initial_chunk_count=5, chunk_size=0x200000, max_chunks=64, target_in_flight=65535, handle=0x1400000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=13),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078be04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=13, va=0x7FFFFFFDE000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=13),
        cap_out=BoMmapOut(handle=13, offset=0x10151D000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, flags=1, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, flags=1, exclusive_vm_id=1, handle=14),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078be04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=14, va=0x7FFFFFFCE000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=15),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078be04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=15, va=0x7FFFFFFCD000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=15),
        cap_out=BoMmapOut(handle=15, offset=0x10152E000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=16),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078be04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=16, va=0x7FFFFFFCC000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=16),
        cap_out=BoMmapOut(handle=16, offset=0x10152F000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=17),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078be04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=17, va=0x7FFFFFFCB000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=17),
        cap_out=BoMmapOut(handle=17, offset=0x101530000),
    ),
    GemZeros(cap_handle=0xb, gpu_va=0x7ffffffe3000, size=4096),
    GemConst(cap_handle=0xc, gpu_va=0x7ffffffdf000, bo_offset=0, blob="MESA_BO_FFFDF000"),
    GemConst(cap_handle=0xd, gpu_va=0x7ffffffde000, bo_offset=0, blob="MESA_BO_FFFDE000"),
    GemConst(cap_handle=0xf, gpu_va=0x7ffffffcd000, bo_offset=0, blob="MESA_INIT_CS_1"),
    GemConst(cap_handle=0x10, gpu_va=0x7ffffffcc000, bo_offset=0, blob="MESA_BO_FFFCC000"),
    GemZeros(cap_handle=0x11, gpu_va=0x7ffffffcb000, size=4096),
    # GROUP_SUBMIT
    IoctlStep(nr=73, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=2, qs_stride=40, qs_count=1),
        cap_out_raw=bytes.fromhex('0200000000000000280000000100000038c304feffff0000'),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=40, stream_addr=0x7FFFFFFCD000, latest_flush=1, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=0x80000000, handle=4)),
        ],
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('c062762c00000000ffffffffffffff7f010000000000000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('c062762c00000000ffffffffffffff7f010000000000000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (4,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=18),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000048bf04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=18, va=0x7FFFFFFCA000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=18),
        cap_out=BoMmapOut(handle=18, offset=0x101531000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, exclusive_vm_id=1, handle=19),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000078bc04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=19, va=0x7FFFFFFBA000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=32768, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=32768, exclusive_vm_id=1, handle=20),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000068bb04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=20, va=0x7FFFFFFB2000, size=32768, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=193, request=0xc01864c1,
        arg_raw=bytes.fromhex('0200000001000000ffffffff000000000000000000000000'),
        cap_out_raw=bytes.fromhex('020000000100000006000000000000000000000000000000'),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('f451eb2800000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('f451eb2800000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=21),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000048bf04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=21, va=0x7FFFFFFB1000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=21),
        cap_out=BoMmapOut(handle=21, offset=0x10154A000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=193, request=0xc01864c1,
        arg_raw=bytes.fromhex('0200000001000000ffffffff000000000000000000000000'),
        cap_out_raw=bytes.fromhex('020000000100000006000000000000000000000000000000'),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('f451eb2800000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('f451eb2800000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=4096, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=4096, exclusive_vm_id=1, handle=22),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000048bf04feffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=22, va=0x7FFFFFFB0000, size=4096, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
]


VADD_STEPS: list[RecipeStep] = [
    GemConst(cap_handle=0x3, gpu_va=0x7fffffffd000, bo_offset=0, blob="MESA_BO_FFFFD000"),
    GemConst(cap_handle=0x4, gpu_va=0x7fffffffc000, bo_offset=0, blob="MESA_BO_FFFFC000"),
    GemU32s(cap_handle=0x12, gpu_va=0x7ffffffca000, values="INPUT_A"),
    GemConst(cap_handle=0x13, gpu_va=0x7ffffffba000, bo_offset=0, blob="MESA_BO_FFFBA000"),
    GemConst(cap_handle=0x14, gpu_va=0x7ffffffb2000, bo_offset=0, blob="MESA_VADD_CS"),
    GemU32s(cap_handle=0x15, gpu_va=0x7ffffffb1000, values="INPUT_B"),
    # GROUP_SUBMIT
    IoctlStep(nr=73, request=0xc0186449,
        arg=GroupSubmitIn(group_handle=2, qs_stride=40, qs_count=1),
        cap_out_raw=bytes.fromhex('02000000000000002800000001000000d0be5da8ffff0000'),
        sides=[
            (PANT_SIDE_QUEUE_SUBMITS, QueueSubmit(stream_size=160, stream_addr=0x7FFFFFFB2000, latest_flush=0xFFFFE0, syncs_stride=16, syncs_count=1)),
            (PANT_SIDE_SYNC_OPS, SyncOp(flags=0x80000001, handle=1, timeline_value=1)),
        ],
    ),
    # SYNCOBJ_TRANSFER
    IoctlStep(nr=204, request=0xc02064cc,
        arg=SyncobjTransferIn(src_handle=1, dst_handle=4, src_point=1),
        cap_out_raw=bytes.fromhex('0100000004000000010000000000000000000000000000000000000000000000'),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=202, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD139F9B, count_handles=1, flags=1),
        cap_out_raw=bytes.fromhex('28e700290000000068c95da8ffff00009b9f13bd2dcd0a00010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_CREATE
    IoctlStep(nr=69, request=0xc0186445,
        arg=BoCreateIn(size=0x10000, exclusive_vm_id=1),
        cap_out=BoCreateOut(size=0x10000, exclusive_vm_id=1, handle=23),
    ),
    # VM_BIND
    IoctlStep(nr=67, request=0xc0186443,
        arg=VmBindIn(vm_id=1, ops_stride=48, ops_count=1),
        cap_out_raw=bytes.fromhex('0100000000000000300000000100000038c65da8ffff0000'),
        sides=[
            (PANT_SIDE_VM_BIND_OPS, VmBindOp(flags=2, bo_handle=23, va=0x7FFFFFFA0000, size=0x10000, syncs_stride=16)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=23),
        cap_out=BoMmapOut(handle=23, offset=0x10154C000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=202, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD17104A, count_handles=1, flags=1),
        cap_out_raw=bytes.fromhex('d8e700290000000058c85da8ffff00004a1017bd2dcd0a00010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=202, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0xACD2DBD186CEB, count_handles=1, flags=1),
        cap_out_raw=bytes.fromhex('28e7002900000000b8dc5da8ffff0000eb6c18bd2dcd0a00010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=19),
        cap_out=BoMmapOut(handle=19, offset=0x101532000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=193, request=0xc01864c1,
        arg_raw=bytes.fromhex('0400000001000000ffffffff000000000000000000000000'),
        cap_out_raw=bytes.fromhex('040000000100000006000000000000000000000000000000'),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('14410d2900000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('14410d2900000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=22),
        cap_out=BoMmapOut(handle=22, offset=0x10154B000),
    ),
    # SYNCOBJ_TIMELINE_WAIT
    IoctlStep(nr=202, request=0xc03064ca,
        arg=SyncobjTimelineWaitIn(timeout_nsec=0x7FFFFFFFFFFFFFFF, count_handles=1, flags=1),
        cap_out_raw=bytes.fromhex('a8f6002900000000c8d75da8ffff0000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (1,)),
            (PANT_SIDE_SYNCOBJ_POINTS, (1,)),
        ],
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=23),
        cap_out=BoMmapOut(handle=23, offset=0x10154C000),
    ),
    # BO_MMAP
    IoctlStep(nr=70, request=0xc0106446,
        arg=BoMmapIn(handle=20),
        cap_out=BoMmapOut(handle=20, offset=0x101542000),
    ),
    # 0xc1
    IoctlStep(nr=193, request=0xc01864c1,
        arg_raw=bytes.fromhex('0400000001000000ffffffff000000000000000000000000'),
        cap_out_raw=bytes.fromhex('040000000100000006000000000000000000000000000000'),
    ),
    # SYNCOBJ_CREATE
    IoctlStep(nr=191, request=0xc00864bf,
        arg=SyncobjCreateIn(),
        cap_out=SyncobjCreateOut(handle=6),
    ),
    # SYNCOBJ_WAIT
    IoctlStep(nr=195, request=0xc02864c3,
        arg_raw=bytes.fromhex('040b0b2900000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        cap_out_raw=bytes.fromhex('040b0b2900000000ffffffffffffff7f010000000100000000000000000000000000000000000000'),
        sides=[
            (PANT_SIDE_SYNCOBJ_HANDLES, (6,)),
        ],
    ),
]
