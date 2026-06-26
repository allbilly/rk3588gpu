/* LD_PRELOAD interposer: record kbase ioctl traffic to a binary .mcap file.
 *
 * Usage on RK3588 (vendor kbase + libmali):
 *   CAPTURE_PATH=/tmp/test.mcap LD_PRELOAD=./kbase_capture.so ./your_gles_app
 *
 * Set CAPTURE_GEM=1 to also snapshot ioctl argument buffers tagged as ring/cs.
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <unistd.h>

#define MALI_MAGIC 0x4D414C49
#define MALI_VERSION 1

enum mali_cap_type {
	MALI_IOCTL = 1,
	MALI_GEM = 2,
	MALI_MARKER = 3,
};

struct mali_hdr {
	uint32_t magic;
	uint32_t version;
	uint32_t count;
	uint32_t pad;
};

struct mali_ioctl_hdr {
	uint8_t type;
	uint8_t pad[3];
	uint32_t request;
	uint32_t arg_in_sz;
	uint32_t arg_out_sz;
	int32_t ret;
};

struct mali_gem_hdr {
	uint8_t type;
	uint8_t pad[3];
	uint64_t gpu_va;
	uint32_t pad2;
	uint32_t data_sz;
};

static int cap_fd = -1;
static int mali_fd = -1;
static int (*real_ioctl)(int, unsigned long, ...) = NULL;

static void cap_open(void)
{
	if (cap_fd >= 0)
		return;
	const char *path = getenv("CAPTURE_PATH");
	if (!path || !path[0])
		return;
	cap_fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
	if (cap_fd < 0) {
		fprintf(stderr, "kbase_capture: open %s failed\n", path);
		return;
	}
	struct mali_hdr hdr = { MALI_MAGIC, MALI_VERSION, 0, 0 };
	write(cap_fd, &hdr, sizeof(hdr));
}

static void cap_write(const void *buf, size_t len)
{
	if (cap_fd < 0)
		return;
	write(cap_fd, buf, len);
}

static int is_mali_fd(int fd)
{
	return mali_fd >= 0 && fd == mali_fd;
}

static void maybe_tag_mali(int fd)
{
	if (mali_fd >= 0)
		return;
	char path[64];
	snprintf(path, sizeof(path), "/proc/self/fd/%d", fd);
	char link[256];
	ssize_t n = readlink(path, link, sizeof(link) - 1);
	if (n < 0)
		return;
	link[n] = '\0';
	if (strstr(link, "/dev/mali") != NULL)
		mali_fd = fd;
}

static void record_ioctl(int fd, unsigned long request, void *arg, int ret)
{
	if (!is_mali_fd(fd))
		return;
	cap_open();
	if (cap_fd < 0)
		return;

	size_t arg_sz = _IOC_SIZE(request);
	struct mali_ioctl_hdr hdr = {
		.type = MALI_IOCTL,
		.request = (uint32_t)request,
		.arg_in_sz = (uint32_t)arg_sz,
		.arg_out_sz = (uint32_t)arg_sz,
		.ret = ret,
	};
	cap_write(&hdr, sizeof(hdr));
	if (arg_sz && arg)
		cap_write(arg, arg_sz);
	if (arg_sz && arg)
		cap_write(arg, arg_sz);
}

int ioctl(int fd, unsigned long request, ...)
{
	if (!real_ioctl)
		real_ioctl = dlsym(RTLD_NEXT, "ioctl");

	va_list ap;
	va_start(ap, request);
	void *arg = va_arg(ap, void *);
	va_end(ap);

	maybe_tag_mali(fd);
	int ret = real_ioctl(fd, request, arg);
	record_ioctl(fd, request, arg, ret);
	return ret;
}

int open(const char *path, int flags, ...)
{
	typedef int (*open_fn)(const char *, int, ...);
	static open_fn real_open = NULL;
	if (!real_open)
		real_open = dlsym(RTLD_NEXT, "open");

	va_list ap;
	va_start(ap, flags);
	mode_t mode = 0;
	int fd;
	if (flags & O_CREAT) {
		mode = va_arg(ap, mode_t);
		fd = real_open(path, flags, mode);
	} else {
		fd = real_open(path, flags);
	}
	va_end(ap);

	if (fd >= 0 && path && strstr(path, "/dev/mali") != NULL)
		mali_fd = fd;
	return fd;
}

int openat(int dirfd, const char *path, int flags, ...)
{
	typedef int (*openat_fn)(int, const char *, int, ...);
	static openat_fn real_openat = NULL;
	if (!real_openat)
		real_openat = dlsym(RTLD_NEXT, "openat");

	mode_t mode = 0;
	if (flags & O_CREAT) {
		va_list ap;
		va_start(ap, flags);
		mode = va_arg(ap, mode_t);
		va_end(ap);
		return real_openat(dirfd, path, flags, mode);
	}
	int fd = real_openat(dirfd, path, flags);
	if (fd >= 0 && path && strstr(path, "/dev/mali") != NULL)
		mali_fd = fd;
	return fd;
}
