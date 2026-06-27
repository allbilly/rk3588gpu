/*
 * Vector add via Mesa OpenCL (rusticl). Setup: README.md
 * Build: make -C examples cl-add
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
	"__kernel void vadd(__global const int *a,\n"
	"                   __global const int *b,\n"
	"                   __global int *out,\n"
	"                   const uint n)\n"
	"{\n"
	"    uint i = get_global_id(0);\n"
	"    if (i < n) out[i] = a[i] + b[i];\n"
	"}\n";

int main(void)
{
	const size_t n = 4;
	const int a_h[] = {1, 2, 3, 4};
	const int b_h[] = {10, 20, 30, 40};
	const int expect[] = {11, 22, 33, 44};
	int out_h[4];

	cl_platform_id platform;
	cl_device_id device;
	cl_context context;
	cl_command_queue queue;
	cl_program program;
	cl_kernel kernel;
	cl_mem a_buf, b_buf, out_buf;
	cl_int err;

	err = clGetPlatformIDs(1, &platform, NULL);
	if (err != CL_SUCCESS) {
		fprintf(stderr, "clGetPlatformIDs failed (%d). See README.md (OpenCL setup)\n", err);
		return 1;
	}

	err = clGetDeviceIDs(platform, CL_DEVICE_TYPE_GPU, 1, &device, NULL);
	if (err != CL_SUCCESS) {
		fprintf(stderr,
			"no OpenCL GPU (%d). Run: clinfo\n",
			err);
		return 1;
	}

	{
		char name[128];
		clGetDeviceInfo(device, CL_DEVICE_NAME, sizeof(name), name, NULL);
		printf("device: %s\n", name);
	}

	context = clCreateContext(NULL, 1, &device, NULL, NULL, &err);
	CHECK(err, "clCreateContext");

#ifdef CL_VERSION_2_0
	queue = clCreateCommandQueueWithProperties(context, device, NULL, &err);
#else
	queue = clCreateCommandQueue(context, device, 0, &err);
#endif
	CHECK(err, "clCreateCommandQueue");

	program = clCreateProgramWithSource(context, 1, &kernel_src, NULL, &err);
	CHECK(err, "clCreateProgramWithSource");

	err = clBuildProgram(program, 1, &device, NULL, NULL, NULL);
	if (err != CL_SUCCESS) {
		size_t log_len;
		clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG, 0, NULL,
				      &log_len);
		char *log = calloc(1, log_len + 1);
		if (log)
			clGetProgramBuildInfo(program, device, CL_PROGRAM_BUILD_LOG,
					      log_len, log, NULL);
		fprintf(stderr, "clBuildProgram failed:\n%s\n", log ? log : "");
		free(log);
		return 1;
	}

	kernel = clCreateKernel(program, "vadd", &err);
	CHECK(err, "clCreateKernel");

	a_buf = clCreateBuffer(context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
			       sizeof(a_h), (void *)a_h, &err);
	CHECK(err, "clCreateBuffer a");
	b_buf = clCreateBuffer(context, CL_MEM_READ_ONLY | CL_MEM_COPY_HOST_PTR,
			       sizeof(b_h), (void *)b_h, &err);
	CHECK(err, "clCreateBuffer b");
	out_buf = clCreateBuffer(context, CL_MEM_WRITE_ONLY, sizeof(out_h), NULL,
				 &err);
	CHECK(err, "clCreateBuffer out");

	cl_uint n_u = (cl_uint)n;
	CHECK(clSetKernelArg(kernel, 0, sizeof(a_buf), &a_buf), "arg0");
	CHECK(clSetKernelArg(kernel, 1, sizeof(b_buf), &b_buf), "arg1");
	CHECK(clSetKernelArg(kernel, 2, sizeof(out_buf), &out_buf), "arg2");
	CHECK(clSetKernelArg(kernel, 3, sizeof(n_u), &n_u), "arg3");

	CHECK(clEnqueueNDRangeKernel(queue, kernel, 1, NULL, &n, NULL, 0, NULL, NULL),
	      "clEnqueueNDRangeKernel");
	CHECK(clFinish(queue), "clFinish");
	CHECK(clEnqueueReadBuffer(queue, out_buf, CL_TRUE, 0, sizeof(out_h), out_h,
				  0, NULL, NULL),
	      "clEnqueueReadBuffer");

	printf("A=%d %d %d %d\n", a_h[0], a_h[1], a_h[2], a_h[3]);
	printf("B=%d %d %d %d\n", b_h[0], b_h[1], b_h[2], b_h[3]);
	printf("out=%d %d %d %d\n", out_h[0], out_h[1], out_h[2], out_h[3]);
	printf("expect=%d %d %d %d\n", expect[0], expect[1], expect[2],
	       expect[3]);

	for (size_t i = 0; i < n; i++) {
		if (out_h[i] != expect[i]) {
			fprintf(stderr, "FAIL at [%zu]\n", i);
			return 1;
		}
	}
	printf("PASS\n");

	clReleaseMemObject(a_buf);
	clReleaseMemObject(b_buf);
	clReleaseMemObject(out_buf);
	clReleaseKernel(kernel);
	clReleaseProgram(program);
	clReleaseCommandQueue(queue);
	clReleaseContext(context);
	return 0;
}
