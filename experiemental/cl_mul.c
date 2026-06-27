/*
 * Vector mul via Mesa OpenCL (rusticl). Setup: README.md
 * Build: gcc -O2 -o cl_mul experiemental/cl_mul.c -lOpenCL
 * Capture: CAPTURE_PATH=/tmp/mul_cl.pcap LD_PRELOAD=experiemental/capture/panthor_capture.so RUSTICL_ENABLE=panfrost ./cl_mul
 */
#define CL_TARGET_OPENCL_VERSION 120
#include <CL/cl.h>

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CHECK(call, msg)                                                       \
	do {                                                                   \
		cl_int err = (call);                                           \
		if (err != CL_SUCCESS) {                                       \
			fprintf(stderr, "%s: %d\n", (msg), err);               \
			return 1;                                              \
		}                                                              \
	} while (0)

static const char *kernel_src =
	"__kernel void vmul(__global const int *a,\n"
	"                   __global const int *b,\n"
	"                   __global int *out,\n"
	"                   const uint n)\n"
	"{\n"
	"    uint i = get_global_id(0);\n"
	"    if (i < n) out[i] = a[i] * b[i];\n"
	"}\n";

int main(void)
{
	cl_platform_id plat;
	CHECK(clGetPlatformIDs(1, &plat, NULL), "clGetPlatformIDs");

	cl_device_id dev;
	CHECK(clGetDeviceIDs(plat, CL_DEVICE_TYPE_GPU, 1, &dev, NULL), "clGetDeviceIDs");

	cl_context ctx = clCreateContext(NULL, 1, &dev, NULL, NULL, NULL);
	CHECK(!ctx, "clCreateContext");

	cl_command_queue q = clCreateCommandQueue(ctx, dev, 0, NULL);
	CHECK(!q, "clCreateCommandQueue");

	const int n = 4;
	int A[4]  = {1, 2, 3, 4};
	int B[4]  = {10, 20, 30, 40};
	int OUT[4] = {0};

	cl_mem bufA  = clCreateBuffer(ctx, CL_MEM_READ_ONLY  | CL_MEM_COPY_HOST_PTR, sizeof(A),  A,  NULL);
	cl_mem bufB  = clCreateBuffer(ctx, CL_MEM_READ_ONLY  | CL_MEM_COPY_HOST_PTR, sizeof(B),  B,  NULL);
	cl_mem bufO  = clCreateBuffer(ctx, CL_MEM_WRITE_ONLY, sizeof(OUT), NULL, NULL);
	CHECK(!bufA || !bufB || !bufO, "clCreateBuffer");

	cl_program prog = clCreateProgramWithSource(ctx, 1, &kernel_src, NULL, NULL);
	CHECK(!prog, "clCreateProgramWithSource");
	CHECK(clBuildProgram(prog, 1, &dev, NULL, NULL, NULL), "clBuildProgram");

	cl_kernel k = clCreateKernel(prog, "vmul", NULL);
	CHECK(!k, "clCreateKernel");

	CHECK(clSetKernelArg(k, 0, sizeof(cl_mem), &bufA), "arg0");
	CHECK(clSetKernelArg(k, 1, sizeof(cl_mem), &bufB), "arg1");
	CHECK(clSetKernelArg(k, 2, sizeof(cl_mem), &bufO), "arg2");
	CHECK(clSetKernelArg(k, 3, sizeof(unsigned int), &n), "arg3");

	size_t gws[1] = {n};
	CHECK(clEnqueueNDRangeKernel(q, k, 1, NULL, gws, NULL, 0, NULL, NULL), "clEnqueueNDRangeKernel");
	CHECK(clFinish(q), "clFinish");

	CHECK(clEnqueueReadBuffer(q, bufO, CL_TRUE, 0, sizeof(OUT), OUT, 0, NULL, NULL), "clEnqueueReadBuffer");

	for (int i = 0; i < n; i++) printf("out[%d] = %d\n", i, OUT[i]);
	printf("expected: [10, 40, 90, 160]\n");

	clReleaseMemObject(bufA); clReleaseMemObject(bufB); clReleaseMemObject(bufO);
	clReleaseKernel(k); clReleaseProgram(prog); clReleaseCommandQueue(q); clReleaseContext(ctx);
	return 0;
}