"""Open /dev/dri/renderD* and issue Panthor DRM ioctls via ctypes."""

from __future__ import annotations

import ctypes
import os

from panthor_ioctl import _ioc_size

_libc = ctypes.CDLL(None, use_errno=True)
_libc.ioctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_void_p]
_libc.ioctl.restype = ctypes.c_int


class PanthorDevice:
    def __init__(self, path: str) -> None:
        self.path = path
        self.fd = os.open(path, os.O_RDWR | os.O_CLOEXEC)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1

    def __enter__(self) -> PanthorDevice:
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
                    raise OSError(err, os.strerror(err), hex(request))
                return rc
        arg = buf if isinstance(buf, ctypes.Array) else ctypes.byref(buf)
        rc = _libc.ioctl(self.fd, request, arg)
        if rc < 0:
            err = ctypes.get_errno()
            raise OSError(err, os.strerror(err), hex(request))
        return rc
