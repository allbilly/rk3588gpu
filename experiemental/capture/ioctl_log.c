#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/ioctl.h>

static int (*real_ioctl)(int, unsigned long, ...) = NULL;

static int is_dri_fd(int fd, char *out, size_t outsz)
{
	char lpath[64];
	snprintf(lpath, sizeof(lpath), "/proc/self/fd/%d", fd);
	char link[256];
	ssize_t n = readlink(lpath, link, sizeof(link) - 1);
	if (n < 0)
		return 0;
	link[n] = 0;
	if (!strstr(link, "/dev/dri/"))
		return 0;
	if (out && outsz)
		strncpy(out, link, outsz - 1);
	return 1;
}

int ioctl(int fd, unsigned long request, ...)
{
	if (!real_ioctl)
		real_ioctl = dlsym(RTLD_NEXT, "ioctl");

	va_list ap;
	va_start(ap, request);
	void *arg = va_arg(ap, void *);
	va_end(ap);

	char path[256] = "";
	int ret = real_ioctl(fd, request, arg);
	if (!is_dri_fd(fd, path, sizeof(path)))
		return ret;

	unsigned nr = request & 0xff;
	unsigned size = (request >> 16) & 0x3fff;
	fprintf(stderr, "ioctl %s cmd=0x%08lx nr=0x%02x size=%u ret=%d\n",
		path, request, nr, size, ret);
	if (ret == 0 && nr == 0x49 && arg && size >= 24) {
		uint8_t *p = arg;
		uint32_t gh = *(uint32_t *)p;
		uint64_t qs_ptr = *(uint64_t *)(p + 16);
		if (qs_ptr) {
			uint32_t *qs = (uint32_t *)(uintptr_t)qs_ptr;
			fprintf(stderr,
				"  GROUP_SUBMIT gh=%u stream_size=%u stream_addr=0x%llx latest_flush=%u\n",
				gh, qs[1], (unsigned long long)*(uint64_t *)(qs + 2), qs[4]);
		}
	}
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
	int fd;
	if (flags & O_CREAT) {
		mode_t mode = va_arg(ap, mode_t);
		fd = real_open(path, flags, mode);
	} else {
		fd = real_open(path, flags);
	}
	va_end(ap);
	return fd;
}
