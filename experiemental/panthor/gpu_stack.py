"""Detect Mali GPU stack: proprietary kbase (/dev/mali0) vs DRM panthor/panfrost."""

from __future__ import annotations

import os


def _drm_driver(render_path: str) -> str | None:
    name = os.path.basename(render_path)
    uevent = f"/sys/class/drm/{name}/device/uevent"
    try:
        with open(uevent, encoding="ascii") as f:
            for line in f:
                if line.startswith("DRIVER="):
                    return line.strip().split("=", 1)[1]
    except OSError:
        pass
    return None


def find_kbase_device() -> str | None:
    for path in ("/dev/mali0", "/dev/mali"):
        if os.path.exists(path):
            return path
    return None


def find_drm_gpu() -> str | None:
    dri = "/dev/dri"
    if not os.path.isdir(dri):
        return None
    for name in sorted(os.listdir(dri)):
        if not name.startswith("renderD"):
            continue
        path = os.path.join(dri, name)
        driver = _drm_driver(path)
        if driver in ("panthor", "panfrost"):
            return path
    return None


def detect_gpu_stack() -> str | None:
    if find_kbase_device():
        return "kbase"
    if find_drm_gpu():
        return "drm"
    return None


def find_mali_device() -> str | None:
    """Default GPU device for live examples (kbase path only)."""
    return find_kbase_device()
