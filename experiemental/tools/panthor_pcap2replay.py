#!/usr/bin/env python3
"""Convert panthor .pcap capture to standalone examples/add_replay.py."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from panthor_cap_format import PantEvent, PantGem, PantIoctl, PantSide, load_events  # noqa: E402


def _hex_blob(data: bytes, indent: str) -> str:
    w = 64
    if len(data) <= w:
        return f'{indent}bytes.fromhex("{data.hex()}"),'
    parts = ",\n".join(f'{indent}        "{data[off : off + w].hex()}"' for off in range(0, len(data), w))
    return f"{indent}bytes.fromhex(\n{indent}    ''.join([\n{parts}\n{indent}    ]),\n{indent}),"


def _emit_stream(events: list[PantEvent]) -> str:
    chunks: list[str] = []
    for ev in events:
        if isinstance(ev, PantIoctl):
            chunks.append(
                "    (\n"
                '        "ioctl",\n'
                f"        0x{ev.request:08x},\n"
                f"        {ev.ret},\n"
                + _hex_blob(ev.arg_in, "        ")
                + "\n"
                + _hex_blob(ev.arg_out, "        ")
                + "\n    ),"
            )
        elif isinstance(ev, PantSide):
            chunks.append(
                "    (\n"
                f'        "side",\n'
                f"        {ev.kind},\n"
                + _hex_blob(ev.data, "        ")
                + "\n    ),"
            )
        elif isinstance(ev, PantGem):
            chunks.append(
                "    (\n"
                '        "gem",\n'
                f"        0x{ev.handle:x},\n"
                f"        0x{ev.gpu_va:x},\n"
                f"        {ev.bo_offset},\n"
                + _hex_blob(ev.data, "        ")
                + "\n    ),"
            )
    return "\n".join(chunks)


def _replay_engine_source() -> str:
    src = (ROOT / "panthor_replay.py").read_text()
    src = re.sub(r"^#!/usr/bin/env python3\n", "", src)
    src = re.sub(r"from __future__ import annotations\n\n", "", src)
    src = re.sub(
        r"def main\(\) -> int:.*?if __name__ == \"__main__\":.*",
        "",
        src,
        flags=re.S,
    )
    return src


def generate(events: list[PantEvent], source: Path, *, start: int) -> str:
    stream = _emit_stream(events)
    return f'''#!/usr/bin/env python3
"""Replay panthor capture from {source.name} — standalone, no LD_PRELOAD.

Capture:
  gcc -shared -fPIC -o /tmp/panthor_capture.so experiemental/capture/panthor_capture.c -ldl
  CAPTURE_PATH=/tmp/add_cl.pcap LD_PRELOAD=/tmp/panthor_capture.so python3 examples/add_cl.py

Regenerate:
  python3 experiemental/tools/panthor_pcap2replay.py {source}
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import mmap
import os
import struct
import sys

{_replay_engine_source()}

CAPTURE = [
{stream}
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--from", dest="start", type=int, default={start},
                   help="skip first N capture events (default {start}: after dev_query)")
    p.add_argument("--until", type=int, default=0, help="stop after N events (0=all)")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    events = CAPTURE[args.start :]
    if args.until:
        events = events[: args.until]
    try:
        return replay_events(events, verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("examples/add_replay.py"))
    ap.add_argument("--from", dest="start", type=int, default=18,
                    help="event index where embedded replay starts (default 18)")
    args = ap.parse_args()

    events = load_events(args.pcap)
    n_i = sum(1 for e in events if isinstance(e, PantIoctl))
    n_g = sum(1 for e in events if isinstance(e, PantGem))
    n_s = sum(1 for e in events if isinstance(e, PantSide))
    print(f"loaded {len(events)} events: {n_i} ioctls, {n_s} sides, {n_g} gems")

    out = generate(events, args.pcap, start=args.start)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out)
    print(f"wrote {args.output} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
