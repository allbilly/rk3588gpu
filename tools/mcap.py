#!/usr/bin/env python3
"""Inspect or synthesize a minimal Mali capture for dry-run testing."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from cap_format import MALI_MAGIC, MALI_IOCTL, MALI_MARKER, MALI_VERSION
from kbase_ioctl import (
    IOCTL_CS_QUEUE_KICK,
    IOCTL_CS_QUEUE_REGISTER,
    IOCTL_VERSION_CHECK,
)


def write_hdr(count: int) -> bytes:
    return struct.pack("<4I", MALI_MAGIC, MALI_VERSION, count, 0)


def write_ioctl(request: int, arg_in: bytes, ret: int, arg_out: bytes) -> bytes:
    hdr = struct.pack("<B3xIIIi", MALI_IOCTL, request, len(arg_in), len(arg_out), ret)
    return hdr + arg_in + arg_out


def write_marker(tag: str) -> bytes:
    tag_b = tag.encode()
    return struct.pack("<B3xI", MALI_MARKER, len(tag_b)) + tag_b


def make_sample() -> bytes:
    """Minimal synthetic capture for parser/replay dry-run on any host."""
    ver_in = struct.pack("<HH", 1, 14)
    ver_out = struct.pack("<HH", 1, 14)
    reg_in = struct.pack("<QIB3x", 0x1000_0000, 4096, 0)
    kick_in = struct.pack("<Q", 0x1000_0000)
    events = [
        write_marker("synthetic-sample"),
        write_ioctl(IOCTL_VERSION_CHECK, ver_in, 0, ver_out),
        write_ioctl(IOCTL_CS_QUEUE_REGISTER, reg_in, 0, b""),
        write_ioctl(IOCTL_CS_QUEUE_KICK, kick_in, 0, b""),
    ]
    body = b"".join(events) + b"\x00"
    return write_hdr(len(events)) + body


def main() -> None:
    parser = argparse.ArgumentParser(description="Mali capture utilities")
    sub = parser.add_subparsers(dest="cmd", required=True)

    gen = sub.add_parser("gen-sample", help="write synthetic test.mcap")
    gen.add_argument("-o", default="test.mcap")

    args = parser.parse_args()
    if args.cmd == "gen-sample":
        out = Path(args.o)
        out.write_bytes(make_sample())
        print(f"wrote {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
