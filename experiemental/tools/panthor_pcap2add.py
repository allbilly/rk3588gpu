#!/usr/bin/env python3
"""Generate examples/add.py from a panthor .pcap (Mesa-decoded standalone path)."""

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


def _find_cs_blobs(events: list[PantEvent]) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    for ev in events:
        if isinstance(ev, PantSide) and ev.kind == 2:
            size = int.from_bytes(ev.data[4:8], "little")
            if size == 40 and "INIT_CS_0" not in out:
                out["INIT_CS_0"] = ev.data
            elif size == 40 and "INIT_CS_1" not in out:
                out["INIT_CS_1"] = ev.data
            elif size == 160:
                out["VADD_QS"] = ev.data
    for ev in events:
        if isinstance(ev, PantGem) and ev.gpu_va == 0x7FFFFFFB2000:
            out["VADD_CS"] = ev.data[:160]
            break
    for ev in events:
        if isinstance(ev, PantGem) and ev.gpu_va == 0x7FFFFFFE6000:
            out["INIT_GEM_0"] = ev.data[:40]
        if isinstance(ev, PantGem) and ev.gpu_va == 0x7FFFFFFCD000:
            out["INIT_GEM_1"] = ev.data[:40]
    return out


def _replay_engine_source() -> str:
    src = (ROOT / "panthor_replay.py").read_text()
    src = re.sub(r"^#!/usr/bin/env python3\n", "", src)
    src = re.sub(r'"""Replay panthor.*?"""\n\n', "", src, flags=re.S)
    src = re.sub(r"from __future__ import annotations\n\n", "", src)
    # drop stdlib imports already in template header
    src = re.sub(r"^import (ctypes|glob|mmap|os|struct|sys|time)\n", "", src, flags=re.M)
    src = re.sub(r"^from pathlib import Path\n", "", src, flags=re.M)
    src = re.sub(
        r"def main\(\) -> int:.*?if __name__ == \"__main__\":.*",
        "",
        src,
        flags=re.S,
    )
    return src.strip()


def generate(
    events: list[PantEvent],
    source: Path,
    *,
    start: int,
    end: int,
) -> str:
    blobs = _find_cs_blobs(events)
    vadd_cs = blobs.get("VADD_CS", b"")
    vadd_cs_lit = _hex_blob(vadd_cs, "").rstrip(",")
    stream = _emit_stream(events[start:end])
    return f'''#!/usr/bin/env python3
"""Vector add on Mali G610 — standalone pure Python (panthor DRM).

Decoded from Mesa/rusticl capture ({source.name}): ioctl replay + embedded CS blobs.
Replay engine matches examples/add_replay.py; this is the minimal PASS slice.

Workload: [1,2,3,4] + [10,20,30,40] -> [11,22,33,44] (uint32)

Regenerate:
  make -C experiemental capture-panthor CAP=/tmp/add_cl2.pcap
  python3 experiemental/tools/panthor_pcap2add.py /tmp/add_cl2.pcap

Also see:
  examples/add_replay.py  — full capture replay
  examples/add_old.py     — hand-coded CSF loop (broken)
  examples/add_cl.py      — OpenCL health check
"""

from __future__ import annotations

import argparse
import ctypes
import glob
import mmap
import os
import struct
import sys
import time
from pathlib import Path

# --- Decoded Mesa command streams (from capture) ---
MESA_VADD_CS = {vadd_cs_lit}
MESA_VADD_CS_VA = 0x7FFFFFFB2000
MESA_VA_OUT = 0x7FFFFFFCB000
MESA_VA_A = 0x7FFFFFFCA000
MESA_VA_B = 0x7FFFFFFB1000
MESA_USER_VA_RANGE = 0x800000000000

INPUT_A = (1, 2, 3, 4)
INPUT_B = (10, 20, 30, 40)
EXPECTED = (11, 22, 33, 44)

{_replay_engine_source()}

MESA_CAPTURE = [
{stream}
]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    try:
        return replay_events(MESA_CAPTURE, verbose=args.verbose)
    except OSError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
'''


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("pcap", type=Path)
    ap.add_argument("-o", "--output", type=Path, default=Path("examples/add.py"))
    ap.add_argument("--from", dest="start", type=int, default=18)
    ap.add_argument("--until", dest="end", type=int, default=0, help="capture end index (0=auto)")
    args = ap.parse_args()

    events = load_events(args.pcap)
    end = args.end or len(events)
    slice_ev = events[args.start : end]
    n_i = sum(1 for e in slice_ev if isinstance(e, PantIoctl))
    n_g = sum(1 for e in slice_ev if isinstance(e, PantGem))
    n_s = sum(1 for e in slice_ev if isinstance(e, PantSide))
    print(f"slice [{args.start}:{end}] -> {len(slice_ev)} events ({n_i} ioctls, {n_s} sides, {n_g} gems)")

    out = generate(events, args.pcap, start=args.start, end=end)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(out)
    print(f"wrote {args.output} ({len(out)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
