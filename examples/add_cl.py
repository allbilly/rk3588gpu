#!/usr/bin/env python3
"""Vector add on Mali G610 via Mesa OpenCL (rusticl) — standalone helper.

Not the primary path. See examples/add.py for applegpu-style DRM ioctls.
Setup: README.md (mesa-opencl-icd, RUSTICL_ENABLE=panfrost).

Run: python3 examples/add_cl.py
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
from ctypes import byref, c_char_p, c_int, c_size_t, c_uint, c_void_p, create_string_buffer

os.environ.setdefault("RUSTICL_ENABLE", "panfrost")

INPUT_A = (1, 2, 3, 4)
INPUT_B = (10, 20, 30, 40)
EXPECTED = (11, 22, 33, 44)

KERNEL = """
__kernel void vadd(__global const int *a,
                   __global const int *b,
                   __global int *out,
                   const uint n)
{
    uint i = get_global_id(0);
    if (i < n) out[i] = a[i] + b[i];
}
"""

CL_SUCCESS = 0
CL_DEVICE_TYPE_GPU = 1 << 2
CL_MEM_READ_ONLY = 1 << 0
CL_MEM_WRITE_ONLY = 1 << 1
CL_MEM_COPY_HOST_PTR = 1 << 5
CL_PROGRAM_BUILD_LOG = 0x1183
CL_DEVICE_NAME = 0x102B
CL_TRUE = 1


def _opencl() -> ctypes.CDLL:
    for name in ("libOpenCL.so.1", "libOpenCL.so"):
        try:
            return ctypes.CDLL(name)
        except OSError:
            continue
        print("libOpenCL not found — see README.md (OpenCL setup)", file=sys.stderr)
    sys.exit(1)


def _check(err: int, msg: str) -> None:
    if err != CL_SUCCESS:
        raise RuntimeError(f"{msg}: OpenCL error {err}")


def run(*, dry_run: bool, verbose: bool) -> int:
    print(f"add: OpenCL/rusticl (RUSTICL_ENABLE={os.environ.get('RUSTICL_ENABLE')})")
    if dry_run:
        print(f"dry-run: compile vadd, enqueue {len(INPUT_A)} threads")
        print(f"  A={list(INPUT_A)} B={list(INPUT_B)} expected={list(EXPECTED)}")
        return 0

    cl = _opencl()
    cl.clGetPlatformIDs.argtypes = [c_uint, c_void_p, ctypes.POINTER(c_uint)]
    cl.clGetPlatformIDs.restype = c_int
    cl.clGetDeviceIDs.argtypes = [c_void_p, c_uint, c_uint, c_void_p, ctypes.POINTER(c_uint)]
    cl.clGetDeviceIDs.restype = c_int
    cl.clCreateContext.argtypes = [c_void_p, c_uint, c_void_p, c_void_p, c_void_p, ctypes.POINTER(c_int)]
    cl.clCreateContext.restype = c_void_p
    cl.clCreateCommandQueue.argtypes = [c_void_p, c_void_p, c_uint, ctypes.POINTER(c_int)]
    cl.clCreateCommandQueue.restype = c_void_p
    cl.clCreateProgramWithSource.argtypes = [
        c_void_p, c_uint, ctypes.POINTER(c_char_p), c_void_p, ctypes.POINTER(c_int),
    ]
    cl.clCreateProgramWithSource.restype = c_void_p
    cl.clBuildProgram.argtypes = [c_void_p, c_uint, c_void_p, c_char_p, c_void_p, c_void_p]
    cl.clBuildProgram.restype = c_int
    cl.clGetProgramBuildInfo.argtypes = [c_void_p, c_void_p, c_uint, c_size_t, c_void_p, ctypes.POINTER(c_size_t)]
    cl.clGetProgramBuildInfo.restype = c_int
    cl.clCreateKernel.argtypes = [c_void_p, c_char_p, ctypes.POINTER(c_int)]
    cl.clCreateKernel.restype = c_void_p
    cl.clCreateBuffer.argtypes = [c_void_p, c_uint, c_size_t, c_void_p, ctypes.POINTER(c_int)]
    cl.clCreateBuffer.restype = c_void_p
    cl.clSetKernelArg.argtypes = [c_void_p, c_uint, c_size_t, c_void_p]
    cl.clSetKernelArg.restype = c_int
    cl.clEnqueueNDRangeKernel.argtypes = [
        c_void_p, c_void_p, c_uint, c_void_p, ctypes.POINTER(c_size_t),
        ctypes.POINTER(c_size_t), c_uint, c_void_p, c_void_p,
    ]
    cl.clEnqueueNDRangeKernel.restype = c_int
    cl.clFinish.argtypes = [c_void_p]
    cl.clFinish.restype = c_int
    cl.clEnqueueReadBuffer.argtypes = [
        c_void_p, c_void_p, c_uint, c_size_t, c_size_t, c_void_p, c_uint, c_void_p, c_void_p,
    ]
    cl.clEnqueueReadBuffer.restype = c_int
    cl.clGetDeviceInfo.argtypes = [c_void_p, c_uint, c_size_t, c_void_p, ctypes.POINTER(c_size_t)]
    cl.clGetDeviceInfo.restype = c_int
    cl.clReleaseMemObject.argtypes = [c_void_p]
    cl.clReleaseMemObject.restype = c_int
    cl.clReleaseKernel.argtypes = [c_void_p]
    cl.clReleaseKernel.restype = c_int
    cl.clReleaseProgram.argtypes = [c_void_p]
    cl.clReleaseProgram.restype = c_int
    cl.clReleaseCommandQueue.argtypes = [c_void_p]
    cl.clReleaseCommandQueue.restype = c_int
    cl.clReleaseContext.argtypes = [c_void_p]
    cl.clReleaseContext.restype = c_int

    n = len(INPUT_A)
    a_h = (c_int * n)(*INPUT_A)
    b_h = (c_int * n)(*INPUT_B)
    out_h = (c_int * n)()
    err_p = c_int()

    platform = c_void_p()
    _check(cl.clGetPlatformIDs(1, byref(platform), None), "clGetPlatformIDs")

    device = c_void_p()
    err = cl.clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 1, byref(device), None)
    if err != CL_SUCCESS:
        print("no OpenCL GPU — try: RUSTICL_ENABLE=panfrost clinfo", file=sys.stderr)
        return 1

    if verbose:
        name = create_string_buffer(128)
        cl.clGetDeviceInfo(device, CL_DEVICE_NAME, 128, name, None)
        print(f"device: {name.value.decode()}")

    context = cl.clCreateContext(None, 1, byref(device), None, None, byref(err_p))
    _check(err_p.value, "clCreateContext")
    queue = cl.clCreateCommandQueue(context, device, 0, byref(err_p))
    _check(err_p.value, "clCreateCommandQueue")

    src = c_char_p(KERNEL.encode())
    program = cl.clCreateProgramWithSource(context, 1, byref(src), None, byref(err_p))
    _check(err_p.value, "clCreateProgramWithSource")

    err = cl.clBuildProgram(program, 1, byref(device), None, None, None)
    if err != CL_SUCCESS:
        log_len = c_size_t()
        cl.clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, None, byref(log_len))
        log = create_string_buffer(log_len.value + 1)
        cl.clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, log_len, log, None)
        print(f"clBuildProgram failed:\n{log.value.decode()}", file=sys.stderr)
        return 1

    kernel = cl.clCreateKernel(program, b"vadd", byref(err_p))
    _check(err_p.value, "clCreateKernel")

    def _buf(ptr, label: str) -> c_void_p:
        _check(err_p.value, label)
        return c_void_p(ptr)

    a_buf = _buf(
        cl.clCreateBuffer(
            context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, ctypes.sizeof(a_h), byref(a_h), byref(err_p),
        ),
        "clCreateBuffer A",
    )
    b_buf = _buf(
        cl.clCreateBuffer(
            context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR, ctypes.sizeof(b_h), byref(b_h), byref(err_p),
        ),
        "clCreateBuffer B",
    )
    out_buf = _buf(
        cl.clCreateBuffer(context, CL_MEM_WRITE_ONLY, ctypes.sizeof(out_h), None, byref(err_p)),
        "clCreateBuffer out",
    )

    n_u = c_uint(n)
    for idx, buf in enumerate((a_buf, b_buf, out_buf)):
        _check(cl.clSetKernelArg(kernel, idx, ctypes.sizeof(c_void_p), byref(buf)), f"arg{idx}")
    _check(cl.clSetKernelArg(kernel, 3, ctypes.sizeof(n_u), byref(n_u)), "arg3")

    gws = c_size_t(n)
    _check(cl.clEnqueueNDRangeKernel(queue, kernel, 1, None, byref(gws), None, 0, None, None), "enqueue")
    _check(cl.clFinish(queue), "clFinish")
    _check(
        cl.clEnqueueReadBuffer(queue, out_buf, CL_TRUE, 0, ctypes.sizeof(out_h), byref(out_h), 0, None, None),
        "read",
    )

    got = tuple(out_h[i] for i in range(n))
    print(f"A={list(INPUT_A)}")
    print(f"B={list(INPUT_B)}")
    print(f"out={list(got)}")
    print(f"expected={list(EXPECTED)}")

    cl.clReleaseMemObject(a_buf)
    cl.clReleaseMemObject(b_buf)
    cl.clReleaseMemObject(out_buf)
    cl.clReleaseKernel(kernel)
    cl.clReleaseProgram(program)
    cl.clReleaseCommandQueue(queue)
    cl.clReleaseContext(context)

    if got != EXPECTED:
        print("FAIL", file=sys.stderr)
        return 1
    print("PASS")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    try:
        return run(dry_run=args.dry_run, verbose=args.verbose)
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
