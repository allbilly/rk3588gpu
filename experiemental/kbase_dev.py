"""Open /dev/mali0 and issue kbase ioctls via ctypes."""

from __future__ import annotations

import ctypes
import os

from kbase_ioctl import _ioc_size, ioctl_name

__all__ = ["KbaseDevice", "find_mali_device"]

_libc = ctypes.CDLL(None, use_errno=True)
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
_libc.ioctl.restype = ctypes.c_int


class KbaseDevice:
    """Thin wrapper around the Arm kbase character device."""

    def __init__(self, path: str = "/dev/mali0") -> None:
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> KbaseDevice:
        return self

    def __exit__(self, *_) -> None:
        self.close()

    def ioctl(self, request: int, buf: ctypes.Array | ctypes.Structure | None = None) -> int:
        if buf is None:
            size = _ioc_size(request)
            if size:
                buf = (ctypes.c_uint8 * size)()
            else:
                rc = _libc.ioctl(self.fd, request, 0)
                if rc < 0:
                    err = ctypes.get_errno()
                    raise OSError(err, os.strerror(err), ioctl_name(request))
                return rc
        arg = buf if isinstance(buf, ctypes.Array) else ctypes.byref(buf)
        rc = _libc.ioctl(self.fd, request, arg)
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), ioctl_name(request))
        return rc

    def ioctl_bytes(self, request: int, arg_in: bytes = b"") -> tuple[int, bytes]:
        size = _ioc_size(request)
        if size == 0:
            return self.ioctl(request), b""
        buf = bytearray(size)
        if arg_in:
            buf[: len(arg_in)] = arg_in
        arr = (ctypes.c_uint8 * size).from_buffer(buf)
        ret = self.ioctl(request, arr)
        return ret, bytes(buf)


def find_mali_device() -> str | None:
    for path in ("/dev/mali0", "/dev/mali"):
        if os.path.exists(path):
            return path
    return None
