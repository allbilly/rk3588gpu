"""Programmatic Mesa/rusticl session init + vadd on panthor DRM.

mesa_init_session() replays the captured init recipe (BO create/bind, groups, init CS).
run_vadd() uploads inputs + CS and submits the compute job.
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mesa_init_recipe import (  # noqa: E402
    GemConst,
    GemStep,
    GemU32s,
    GemZeros,
    IoctlStep,
    MESA_INIT_STEPS,
    PANT_SIDE_SYNCOBJ_HANDLES,
    PANT_SIDE_SYNCOBJ_POINTS,
    RecipeStep,
    VADD_STEPS,
)
from panthor_cap_decode import ioctl_name  # noqa: E402
from panthor_replay import replay_events  # noqa: E402


def _pack_side(kind: int, obj: Any) -> bytes:
    if isinstance(obj, tuple):
        if kind == PANT_SIDE_SYNCOBJ_HANDLES:
            return b"".join(struct.pack("<I", h) for h in obj)
        if kind == PANT_SIDE_SYNCOBJ_POINTS:
            return b"".join(struct.pack("<Q", p) for p in obj)
        raise ValueError(f"unexpected tuple side kind {kind}")
    return obj.pack()


def _ioctl_arg_bytes(step: IoctlStep) -> bytes:
    if step.arg_raw is not None:
        return step.arg_raw
    if step.arg is not None and hasattr(step.arg, "pack"):
        return step.arg.pack()
    raise ValueError(f"{ioctl_name(step.nr)} missing arg")


def _ioctl_cap_out_bytes(step: IoctlStep) -> bytes:
    if step.cap_out_raw is not None:
        return step.cap_out_raw
    if step.cap_out is not None and hasattr(step.cap_out, "pack"):
        return step.cap_out.pack()
    return b""


def steps_to_tuples(
    steps: list[RecipeStep],
    *,
    inputs: dict[str, tuple[int, ...]],
    blobs: dict[str, bytes],
) -> list[tuple]:
    tuples: list[tuple] = []
    for step in steps:
        if isinstance(step, GemZeros):
            tuples.append(("gem", step.cap_handle, step.gpu_va, 0, b"\x00" * step.size))
        elif isinstance(step, GemU32s):
            vals = inputs[step.values]
            tuples.append(
                ("gem", step.cap_handle, step.gpu_va, 0, struct.pack(f"<{len(vals)}I", *vals))
            )
        elif isinstance(step, GemConst):
            tuples.append(("gem", step.cap_handle, step.gpu_va, step.bo_offset, blobs[step.blob]))
        elif isinstance(step, IoctlStep):
            for sk, obj in step.sides:
                tuples.append(("side", sk, _pack_side(sk, obj)))
            tuples.append(
                (
                    "ioctl",
                    step.request,
                    0,
                    _ioctl_arg_bytes(step),
                    _ioctl_cap_out_bytes(step),
                )
            )
    return tuples


def mesa_init_session(*, blobs: dict[str, bytes], verbose: bool = False) -> None:
    """Bring up VM, BOs, syncobjs, groups, and run Mesa init CS submits."""
    replay_events(
        steps_to_tuples(MESA_INIT_STEPS, inputs={}, blobs=blobs),
        verbose=verbose,
    )


def run_vadd(
    input_a: tuple[int, ...],
    input_b: tuple[int, ...],
    *,
    blobs: dict[str, bytes],
    verbose: bool = False,
) -> int:
    """Upload A/B + CS stream and enqueue the vector-add GROUP_SUBMIT.

    Must run in the same replay session as mesa_init_session (use mesa_vadd).
    """
    inputs = {"INPUT_A": input_a, "INPUT_B": input_b}
    return replay_events(
        steps_to_tuples(VADD_STEPS, inputs=inputs, blobs=blobs),
        verbose=verbose,
    )


def mesa_vadd(
    input_a: tuple[int, ...],
    input_b: tuple[int, ...],
    *,
    blobs: dict[str, bytes],
    verbose: bool = False,
) -> int:
    """Full Mesa session: init then vadd in one DRM context."""
    steps = [*MESA_INIT_STEPS, *VADD_STEPS]
    inputs = {"INPUT_A": input_a, "INPUT_B": input_b}
    return replay_events(
        steps_to_tuples(steps, inputs=inputs, blobs=blobs),
        verbose=verbose,
    )
