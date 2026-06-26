# rk3588gpu progress

Last updated: 2026-06-26  
Board: Orange Pi / RK3588, kernel `6.1.99-rockchip-rk3588`

## Goal

Pure Python GPU bring-up on RK3588 Mali-G610 — same *pattern* as [allbilly/applegpu](https://github.com/allbilly/applegpu) `examples/add.py`: open device, issue ioctls, submit work. No libmali in the hot path.

See also [gpt-deepresearch.md](gpt-deepresearch.md) (Apple `add.py` porting report) and [README.md](README.md).

---

## Stack reality (Orange Pi vs references)

Most external references assume **Mesa + Panfrost/Panthor on mainline-ish kernel**:

| | References (Mesa path) | This board (Rockchip BSP) |
|--|------------------------|---------------------------|
| Kernel | Mainline / panthor overlay | `6.1.99-rockchip-rk3588` |
| GPU driver | `panfrost` DRM module | Built-in proprietary `mali` (kbase CSF) |
| Device node | `/dev/dri/renderD128` | `/dev/mali0` |
| UAPI | `drm/panfrost_drm.h` | `mali_kbase_csf_ioctl.h` (UK 1.14) |
| Buffer API | `CREATE_BO`, `MMAP_BO`, `SUBMIT` | `MEM_ALLOC`, `CS_QUEUE_*`, `CS_QUEUE_KICK` |

Verified on this board:

- `/dev/mali0` — Mali G610 (`dmesg`: `mali fb000000.gpu`, CSF firmware loaded)
- `/dev/dri/renderD128` — display subsystem; Panfrost `GET_PARAM` / `CREATE_BO` fail
- `/dev/dri/renderD129` — NPU (`fdab0000.npu`), not GPU
- Mesa 23.2 installed but does **not** own Mali compute on this kernel

**This repo targets the Rockchip BSP / kbase path**, not the Panfrost `direct_add.py` from the research doc.

---

## What exists

| Component | Role | Status |
|-----------|------|--------|
| `kbase_ioctl.py` | Ioctl numbers + ctypes unions (CSF UK 1.14) | Done; sizes fixed (see below) |
| `kbase_dev.py` | Open `/dev/mali0`, ioctl helpers | Done |
| `cap_format.py` | `.mcap` binary capture format | Done |
| `cap_decode.py` | Named struct decode for dumps | Done |
| `replay.py` | Parse / dry-run / live replay captures | Done |
| `cs_disasm.py` | CSF command stream disassembler | Done |
| `capture/kbase_capture.so` | LD_PRELOAD interposer → `.mcap` | Builds |
| `tools/mcap.py` | Synthetic capture for parser tests | Done |
| `examples/init.py` | Minimal live CSF init | **Works** |
| `examples/add.py` | Vector add workload (init + MEM_ALLOC + kick) | **Partial** |

---

## Bugs fixed (2026-06-26)

1. **`kbase_dev.py`** — Set `ioctl.argtypes` / `restype` and use `byref()` for union buffers. Without this, direct ctypes calls returned `EFAULT`.

2. **Wrong `_IOWR` buffer sizes in `kbase_ioctl.py`** — Kernel uses C **union** sizes, not `in + out`. Wrong sizes caused `ENOTTY`:

   | Ioctl | Was | Now |
   |-------|-----|-----|
   | `MEM_ALLOC` | 48 | **32** |
   | `MEM_ALLOC_EX` | 96 | **64** |
   | `CS_QUEUE_BIND` | 24 | **16** |
   | `CS_QUEUE_GROUP_CREATE` | 48 | **40** |
   | `CS_GET_GLB_IFACE` | 48 | **24** |

   All nine tracked ioctls now match `ctypes.sizeof` (verified on device).

3. **Docs** — README maps research doc / applegpu flow to kbase path; AGENTS.md points at `gpt-deepresearch.md`.

---

## Test results (this board)

```bash
make test-dry     # PASS — synthetic .mcap parses
make test-live    # PASS — examples/init.py
```

### `examples/init.py` — PASS

Live ioctls on `/dev/mali0`:

1. `VERSION_CHECK` → major=1 minor=14  
2. `SET_FLAGS`  
3. `CS_GET_GLB_IFACE` → group_num=8, total_stream_num=64, …  
4. `CS_QUEUE_GROUP_CREATE` → group_handle=0, group_uid=N  

### `examples/add.py` — FAIL (partial)

Same init as above, then:

- `MEM_ALLOC` × 3 (buffers A, B, out) → **`ENOMEM`** with every flag combo tried so far  
- No CSF ring build / `CS_QUEUE_KICK` — not implemented  

### `replay.py` live on synthetic `test.mcap` — partial

- `VERSION_CHECK` succeeds  
- `CS_QUEUE_REGISTER` / `CS_QUEUE_KICK` → `EPERM` (synthetic capture, no real GPU VAs / init sequence)

---

## Apple add.py mapping (kbase path)

| add.py step | Status on Orange Pi BSP |
|-------------|-------------------------|
| Open device (`/dev/mali0`) | Done |
| Context init (`VERSION_CHECK`, `SET_FLAGS`) | Done |
| Query GPU (`CS_GET_GLB_IFACE`) | Done |
| Queue group create | Done |
| GPU memory alloc (`MEM_ALLOC`) | **Blocked** — ENOMEM / flags TBD |
| Upload inputs (mmap) | Not started |
| CSF ring / shader bytes | Not started (`cs_disasm.py` exists for decode only) |
| Submit (`CS_QUEUE_REGISTER` + `KICK`) | Needs capture or hand-built ring |
| Readback + verify | Not started |
| Capture / replay workflow | Infrastructure done; needs real app capture |

---

## Capture / replay workflow (recommended next path)

Record a working libmali app, replay in pure Python:

```bash
make capture APP=./your_gles_app CAP=foo.mcap
python3 replay.py foo.mcap --dry-run    # inspect
python3 replay.py foo.mcap              # live replay
```

This mirrors applegpu `.cap` → `replay.py`, adapted for `.mcap` + kbase.

---

## Open issues

1. **`MEM_ALLOC` flags** — Driver rejects or fails alloc (`ENOMEM`). Need flags from a real libmali capture or BSP header (`BASE_MEM_*`). `dmesg` showed `kbase_mem_alloc called with bad flags` during probing.

2. **`examples/add.py` incomplete** — Init ioctls work; full vector add needs MEM_ALLOC flags + CSF ring + kick.

3. **AddrMap / GEM replay** — `replay.py` notes GEM blobs are not re-uploaded; live replay needs full `MEM_ALLOC` sequence in capture.

4. **Panfrost path** — Documented in research doc but **not implemented**; would need different kernel (panthor overlay, panfrost owning GPU).

---

## Next steps (priority)

1. Capture ioctl trace from any app that successfully uses `/dev/mali0` (even `eglinfo`, a tiny GLES binary, or vendor demo).
2. Diff captured `MEM_ALLOC` flags / order vs our Python init.
3. Wire `AddrMap.learn_mem_alloc` to remap GPU VAs on replay.
4. Replay capture end-to-end; then trim toward minimal hand-written sequence.
5. Finish `examples/add.py` once MEM_ALLOC + kick work.
6. Optional: Panfrost `examples/panfrost_add.py` for boards with mainline + render node (out of scope for Orange Pi BSP).

---

## References used

- [gpt-deepresearch.md](gpt-deepresearch.md) — porting report (Panfrost vs kbase)
- [allbilly/applegpu](https://github.com/allbilly/applegpu) — pure Python ioctl replay pattern
- [allbilly/rk3588gpu](https://github.com/allbilly/rk3588gpu) — upstream repo layout
- icecream95 Mali G610 RE blogs (CSF opcodes → `cs_disasm.py`)
- Arm `mali_kbase_csf_ioctl.h` UK 1.14 → `kbase_ioctl.py`
