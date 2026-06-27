"""Mali kbase capture format parser and GPU VA remapping."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from kbase_ioctl import ioctl_name

MALI_MAGIC = 0x4D414C49  # 'MALI'
MALI_VERSION = 1

MALI_IOCTL = 1
MALI_GEM = 2
MALI_MARKER = 3

HDR_FMT = "<4I"
IOCTL_HDR_FMT = "<B3xIIIi"
GEM_HDR_FMT = "<B3xQQI"
MARKER_HDR_FMT = "<B3xI"


@dataclass
class MaliIoctl:
    request: int
    arg_in: bytes
    ret: int
    arg_out: bytes

    @property
    def name(self) -> str:
        return ioctl_name(self.request)


@dataclass
class MaliGem:
    gpu_va: int
    label: str
    data: bytes


@dataclass
class MaliMarker:
    tag: str


MaliEvent = MaliIoctl | MaliGem | MaliMarker


class AddrMap:
    """Remap GPU VAs from capture into live process allocations."""

    def __init__(self) -> None:
        self._maps: dict[int, int] = {}

    def add(self, old: int, new: int) -> None:
        if not old or not new or old == new:
            return
        self._maps[old] = new

    def remap(self, value: int) -> int:
        return self._maps.get(value, value)

    def patch_u64_buf(self, buf: bytearray) -> None:
        for off in range(0, len(buf) - 7, 8):
            old, = struct.unpack_from("<Q", buf, off)
            new = self.remap(old)
            if new != old:
                struct.pack_into("<Q", buf, off, new)

    def learn_mem_alloc(self, arg_in: bytes, arg_out: bytes) -> None:
        """MEM_ALLOC / MEM_ALLOC_EX: no stable in-GPU-VA to learn from in alone."""
        _ = (arg_in, arg_out)

    def learn_from_gem(self, gem: MaliGem, live_gpu_va: int) -> None:
        self.add(gem.gpu_va, live_gpu_va)

    def __len__(self) -> int:
        return len(self._maps)


class CaptureReader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.off = 0

    def read(self, n: int) -> bytes:
        chunk = self.data[self.off : self.off + n]
        if len(chunk) != n:
            raise EOFError(f"truncated capture at offset {self.off}")
        self.off += n
        return chunk

    def peek_type(self) -> int | None:
        if self.off >= len(self.data):
            return None
        return self.data[self.off]

    def read_hdr(self) -> tuple[int, int, int]:
        magic, version, count, _pad = struct.unpack(HDR_FMT, self.read(16))
        if magic != MALI_MAGIC:
            raise ValueError(f"bad magic 0x{magic:08x} (expected MALI)")
        if version != MALI_VERSION:
            raise ValueError(f"unsupported capture version {version}")
        return magic, version, count

    def read_ioctl(self) -> MaliIoctl:
        hdr = self.read(struct.calcsize(IOCTL_HDR_FMT))
        _typ, request, arg_in_sz, arg_out_sz, ret = struct.unpack(IOCTL_HDR_FMT, hdr)
        arg_in = self.read(arg_in_sz) if arg_in_sz else b""
        arg_out = self.read(arg_out_sz) if arg_out_sz else b""
        return MaliIoctl(request, arg_in, ret, arg_out)

    def read_gem(self) -> MaliGem:
        hdr = self.read(struct.calcsize(GEM_HDR_FMT))
        _typ, gpu_va, _pad, data_sz = struct.unpack(GEM_HDR_FMT, hdr)
        label_len = struct.unpack("<I", self.read(4))[0]
        label = self.read(label_len).decode("utf-8", errors="replace") if label_len else ""
        data = self.read(data_sz) if data_sz else b""
        return MaliGem(gpu_va, label, data)

    def read_marker(self) -> MaliMarker:
        hdr = self.read(struct.calcsize(MARKER_HDR_FMT))
        _typ, tag_len = struct.unpack(MARKER_HDR_FMT, hdr)
        tag = self.read(tag_len).decode("utf-8", errors="replace") if tag_len else ""
        return MaliMarker(tag)

    def iter_events(self) -> Iterator[MaliEvent]:
        self.read_hdr()
        while True:
            op_type = self.peek_type()
            if op_type is None or op_type == 0:
                break
            if op_type == MALI_IOCTL:
                yield self.read_ioctl()
            elif op_type == MALI_GEM:
                yield self.read_gem()
            elif op_type == MALI_MARKER:
                yield self.read_marker()
            else:
                raise ValueError(f"bad capture type {op_type} at offset {self.off}")


def load_events(path: Path) -> list[MaliEvent]:
    return list(CaptureReader(path.read_bytes()).iter_events())
