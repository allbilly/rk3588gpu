#define _GNU_SOURCE
#include <dlfcn.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <sys/mman.h>
#include <sys/ioctl.h>

#include <drm/panthor_drm.h>

static int (*real_ioctl)(int, unsigned long, ...) = NULL;

#define MAX_BO 64
struct bo_map {
	uint32_t handle;
	uint64_t gpu_va;
	void *cpu;
	int used;
} bos[MAX_BO];

static int dri_fd = -1;

static struct bo_map *find_bo(uint32_t handle)
{
	for (int i = 0; i < MAX_BO; i++)
		if (bos[i].used && bos[i].handle == handle)
			return &bos[i];
	return NULL;
}

static struct bo_map *alloc_bo(uint32_t handle)
{
	for (int i = 0; i < MAX_BO; i++) {
		if (!bos[i].used) {
			bos[i].used = 1;
			bos[i].handle = handle;
			bos[i].gpu_va = 0;
			bos[i].cpu = NULL;
			return &bos[i];
		}
	}
	return NULL;
}

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

static void dump_cs(uint64_t gpu_va, uint32_t size)
{
	for (int i = 0; i < MAX_BO; i++) {
		if (!bos[i].used || bos[i].gpu_va != gpu_va || !bos[i].cpu)
			continue;
		fprintf(stderr, "CS dump gpu_va=0x%llx size=%u:\n",
			(unsigned long long)gpu_va, size);
		uint8_t *p = bos[i].cpu;
		for (uint32_t off = 0; off < size && off < 256; off += 8) {
			uint64_t w = 0;
			memcpy(&w, p + off, 8);
			fprintf(stderr, "  %04x: %016llx\n", off, (unsigned long long)w);
		}
		return;
	}
	fprintf(stderr, "CS dump: no BO for gpu_va=0x%llx\n", (unsigned long long)gpu_va);
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

	if (fd >= 0)
		dri_fd = fd;

	if (ret == 0 && nr == 0x45 && arg) {
		struct drm_panthor_bo_create *c = arg;
		struct bo_map *b = alloc_bo(c->handle);
		if (b)
			b->handle = c->handle;
	}

	if (ret == 0 && nr == 0x43 && arg) {
		struct drm_panthor_vm_bind *bind = arg;
		if (bind->ops.count && bind->ops.array) {
			struct drm_panthor_vm_bind_op *ops =
				(struct drm_panthor_vm_bind_op *)(uintptr_t)bind->ops.array;
			for (uint32_t i = 0; i < bind->ops.count; i++) {
				struct bo_map *b = find_bo(ops[i].bo_handle);
				if (b)
					b->gpu_va = ops[i].va;
			}
		}
	}

	if (ret == 0 && nr == 0x46 && arg) {
		struct drm_panthor_bo_mmap_offset *m = arg;
		struct bo_map *b = find_bo(m->handle);
		if (b && dri_fd >= 0) {
			void *cpu = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED,
					 dri_fd, m->offset);
			if (cpu != MAP_FAILED)
				b->cpu = cpu;
		}
	}

	if (ret == 0 && nr == 0x49 && arg) {
		struct drm_panthor_group_submit *gs = arg;
		if (gs->queue_submits.count && gs->queue_submits.array) {
			struct drm_panthor_queue_submit *qs =
				(struct drm_panthor_queue_submit *)(uintptr_t)gs->queue_submits.array;
			fprintf(stderr, "GROUP_SUBMIT stream_addr=0x%llx size=%u latest_flush=%u\n",
				(unsigned long long)qs->stream_addr, qs->stream_size, qs->latest_flush);
			dump_cs(qs->stream_addr, qs->stream_size);
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
