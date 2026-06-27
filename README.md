# rk3588gpu

Pure Python Mali GPU bring-up on RK3588 — no libmali, no Mesa in the hot path.
Same idea as [allbilly/applegpu](https://github.com/allbilly/applegpu) `examples/add.py`: open the device, issue ioctls, submit work.

See **[gpt-deepresearch.md](gpt-deepresearch.md)** for the full porting report (Apple `add.py` → Mali, Panfrost vs proprietary stack, ioctl mapping tables, setup prerequisites).

## Two Mali stacks on RK3588

| Stack | Device node | UAPI | This repo |
|-------|-------------|------|-----------|
| **Panthor** (mainline) | `/dev/dri/renderD128` | DRM panthor ioctls + CSF stream | **`examples/add.py`** — standalone like applegpu |
| **Proprietary kbase** (Rockchip BSP) | `/dev/mali0` | `mali_kbase_csf_ioctl.h` — CSF ioctls | **Implemented** — capture, replay, examples |

On many RK3588 boards (including Orange Pi with the vendor `mali` module), **`/dev/mali0` is the GPU** and `renderD128` is the display subsystem, not Panfrost. The research doc notes:

> *If instead using Rockchip's proprietary driver, the Python IOCTLs above will not work; one would then use the `/dev/mali0` interface.*

This repository is that `/dev/mali0` path.

## Apple add.py → kbase (this repo)

From [gpt-deepresearch.md](gpt-deepresearch.md) § *Apple vs Mali IOCTL/Buffers Mapping*, adapted for the proprietary CSF driver:

| **add.py step** | **Apple (Asahi)** | **RK3588 kbase (this repo)** |
|-----------------|-------------------|------------------------------|
| Open device | `open("/dev/dri/cardX")` | `open("/dev/mali0")` — `kbase_dev.KbaseDevice` |
| Version / context | IOKit / AGX setup | `KBASE_IOCTL_VERSION_CHECK`, `KBASE_IOCTL_SET_FLAGS` |
| Query caps | AGX params | `KBASE_IOCTL_CS_GET_GLB_IFACE` |
| Queue setup | AGX queue create | `KBASE_IOCTL_CS_QUEUE_GROUP_CREATE`, `CS_QUEUE_REGISTER`, `CS_QUEUE_BIND` |
| Allocate GPU memory | GEM / UAO alloc | `KBASE_IOCTL_MEM_ALLOC` / `MEM_ALLOC_EX` |
| Upload inputs | mmap + write | mmap via bind handle, or GEM blob in `.mcap` |
| Build command stream | Metal / AGX shader bytes | Mali CSF ring (`cs_disasm.py`) |
| Submit | `AGX_SUBMIT` | `KBASE_IOCTL_CS_QUEUE_KICK` |
| Wait | fence / `AGX_WAIT` | `KBASE_IOCTL_CS_EVENT_SIGNAL` + kick completion |
| Replay captured trace | `.cap` + `replay.py` | `.mcap` + `replay.py` |

Flow (kbase path):

```mermaid
sequenceDiagram
    participant U as Python (examples/init.py)
    participant K as /dev/mali0
    participant G as Mali G610
    U->>K: VERSION_CHECK, SET_FLAGS
    U->>K: CS_GET_GLB_IFACE
    U->>K: CS_QUEUE_GROUP_CREATE
    Note over U,K: full add.py also needs MEM_ALLOC, ring fill, KICK
    U->>K: CS_QUEUE_REGISTER + CS_QUEUE_KICK
    K->>G: CSF scheduler
    G-->>K: completion
```

## Layout

```
kbase_ioctl.py    # ioctl numbers + ctypes unions (CSF UK 1.14)
kbase_dev.py      # open /dev/mali0, ioctl helpers
cap_format.py     # .mcap binary format
cap_decode.py     # named struct decode for dumps
replay.py         # replay captures (dry-run or live)
cs_disasm.py      # CSF command stream disassembler
capture/          # LD_PRELOAD interposer → .mcap
examples/
  add.py          # standalone vector add (panthor DRM ioctls + CSF stream)
  add_cl.py       # optional OpenCL via Mesa rusticl
  cl_add.c        # same OpenCL workload in C
  init.py         # minimal kbase init (/dev/mali0 — needs BSP kernel)
experiemental/    # kbase capture/replay, hand-coded panthor CS (ioctl research)
```

## Quick start

### GPU vector add (mainline panthor — DRM, pure Python)

Standalone script — no repo imports, no OpenCL:

```bash
python3 examples/add.py
python3 examples/add.py --dry-run -v
```

Opens `/dev/dri/renderD128`, builds a CSF command stream, submits via
`DRM_IOCTL_PANTHOR_GROUP_SUBMIT`. Expected:

```
A=[1, 2, 3, 4]
B=[10, 20, 30, 40]
out=[11, 22, 33, 44]
expected=[11, 22, 33, 44]
PASS
```

If submit times out after prior `CS_FATAL` kernel errors, **reboot** to reset the GPU.

**Optional** Mesa OpenCL path (works today on Armbian; not applegpu-style).

One-time setup:

```bash
sudo apt install mesa-opencl-icd ocl-icd-libopencl1 clinfo
export RUSTICL_ENABLE=panfrost   # rusticl hides the GPU unless opted in
clinfo                           # should list Mali-G610 MC4 (Panfrost)
```

Run:

```bash
python3 examples/add_cl.py
# or C build: make -C examples cl-add   # needs ocl-icd-opencl-dev build-essential
```

Expected:

```
device: Mali-G610 MC4 (Panfrost)
out=[11, 22, 33, 44]
PASS
```

### Kbase capture / replay (BSP `/dev/mali0` — vendor kernel)

```bash
make -C experiemental test-dry     # parse synthetic capture (any host)
make -C experiemental test-live    # send real ioctls to /dev/mali0
make -C experiemental capture APP=./your_gles_app CAP=foo.mcap
python3 experiemental/replay.py foo.mcap --dry-run
python3 experiemental/replay.py foo.mcap
```

Permissions: `video` or `render` group for `/dev/mali0` or `/dev/dri/renderD128`.

## References

```
blog  https://icecream95.gitlab.io/mali-g610-reverse-engineering-part-1.html
      … parts 2–4

mesa  https://docs.mesa3d.org/drivers/panfrost.html
      panfrost GL  https://gitlab.freedesktop.org/mesa/mesa/-/tree/main/src/gallium/drivers/panfrost
      panvk        https://gitlab.freedesktop.org/mesa/mesa/-/tree/main/src/panfrost/vulkan

uapi  panfrost     https://github.com/torvalds/linux/blob/master/include/uapi/drm/panfrost_drm.h
      panfrost drm https://dri.freedesktop.org/docs/drm/gpu/panfrost.html

rk3588 / panthor
      https://www.phoronix.com/news/Panthor-DRM-Newer-Mali
      https://www.collabora.com/news-and-blog/news-and-events/from-panthor-to-rk3588-advancing-graphics-video-and-soc-support-linux-kernel-7.html

methodology (applegpu mental model)
      https://asahilinux.org/2023/03/road-to-vulkan/
      https://github.com/allbilly/applegpu
```
