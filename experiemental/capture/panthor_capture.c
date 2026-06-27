/* LD_PRELOAD: record panthor (/dev/dri/renderD*) ioctl traffic + BO blobs.
 *
 *   CAPTURE_PATH=/tmp/add_cl.pcap LD_PRELOAD=./panthor_capture.so python3 examples/add_cl.py
 *
 * Format: experiemental/panthor_cap_format.py
 */

#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm/panthor_drm.h>

#ifndef DRM_COMMAND_BASE
#define DRM_COMMAND_BASE 0x40
#endif

struct drm_syncobj_wait_cap {
	uint64_t handles;
	int64_t timeout_nsec;
	uint32_t count_handles;
	uint32_t flags;
	uint32_t first_signaled;
	uint32_t pad;
	uint64_t deadline_nsec;
};

#define PANTHOR_IOCTL_NR(name) (DRM_COMMAND_BASE + DRM_PANTHOR_##name)

#define PANT_MAGIC 0x504E4154 /* 'PANT' */
#define PANT_VERSION 1

enum pant_type {
	PANT_IOCTL = 1,
	PANT_SIDE = 2,
	PANT_GEM = 3,
	PANT_MARKER = 4,
};

enum pant_side_kind {
	PANT_SIDE_VM_BIND_OPS = 1,
	PANT_SIDE_QUEUE_SUBMITS = 2,
	PANT_SIDE_GROUP_QUEUES = 3,
	PANT_SIDE_SYNC_OPS = 4,
	PANT_SIDE_DEV_QUERY = 5,
	PANT_SIDE_BIND_SYNC_OPS = 6,
	PANT_SIDE_SYNCOBJ_HANDLES = 7,
	PANT_SIDE_SYNCOBJ_POINTS = 8,
};

struct pant_hdr {
	uint32_t magic;
	uint32_t version;
	uint32_t count;
	uint32_t pad;
};

struct pant_ioctl_hdr {
	uint8_t type;
	uint8_t pad[3];
	uint32_t request;
	uint32_t arg_in_sz;
	uint32_t arg_out_sz;
	int32_t ret;
};

struct pant_side_hdr {
	uint8_t type;
	uint8_t kind;
	uint16_t pad;
	uint32_t data_sz;
};

struct pant_gem_hdr {
	uint8_t type;
	uint8_t pad[3];
	uint32_t handle;
	uint32_t pad2;
	uint64_t gpu_va;
	uint64_t bo_offset;
	uint32_t data_sz;
	uint32_t pad3;
};

struct pant_marker_hdr {
	uint8_t type;
	uint8_t pad[3];
	uint32_t tag_sz;
};

#define MAX_BO 256
struct bo_entry {
	int used;
	uint32_t handle;
	uint64_t size;
	uint64_t gpu_va;
	void *cpu;
	uint64_t map_sz;
};

static int cap_fd = -1;
static int dri_fd = -1;
static uint32_t cap_count;
static struct bo_entry bos[MAX_BO];
static int (*real_ioctl)(int, unsigned long, ...) = NULL;

static void cap_write(const void *buf, size_t len)
{
	if (cap_fd < 0)
		return;
	if (write(cap_fd, buf, len) != (ssize_t)len)
		fprintf(stderr, "panthor_capture: write failed\n");
}

static void cap_open(void)
{
	if (cap_fd >= 0)
		return;
	const char *path = getenv("CAPTURE_PATH");
	if (!path || !path[0])
		return;
	cap_fd = open(path, O_WRONLY | O_CREAT | O_TRUNC, 0644);
	if (cap_fd < 0) {
		fprintf(stderr, "panthor_capture: open %s: %s\n", path, strerror(errno));
		return;
	}
	struct pant_hdr hdr = { PANT_MAGIC, PANT_VERSION, 0, 0 };
	cap_write(&hdr, sizeof(hdr));
}

static void cap_bump(void)
{
	cap_count++;
	if (cap_fd < 0)
		return;
	if (lseek(cap_fd, offsetof(struct pant_hdr, count), SEEK_SET) < 0)
		return;
	write(cap_fd, &cap_count, sizeof(cap_count));
	lseek(cap_fd, 0, SEEK_END);
}

static void cap_side(uint8_t kind, const void *data, uint32_t sz)
{
	if (!sz || !data)
		return;
	cap_open();
	if (cap_fd < 0)
		return;
	struct pant_side_hdr hdr = { .type = PANT_SIDE, .kind = kind, .data_sz = sz };
	cap_write(&hdr, sizeof(hdr));
	cap_write(data, sz);
	cap_bump();
}

static struct bo_entry *bo_find(uint32_t handle)
{
	for (int i = 0; i < MAX_BO; i++)
		if (bos[i].used && bos[i].handle == handle)
			return &bos[i];
	return NULL;
}

static struct bo_entry *bo_alloc(uint32_t handle)
{
	struct bo_entry *b = bo_find(handle);
	if (b)
		return b;
	for (int i = 0; i < MAX_BO; i++) {
		if (!bos[i].used) {
			memset(&bos[i], 0, sizeof(bos[i]));
			bos[i].used = 1;
			bos[i].handle = handle;
			return &bos[i];
		}
	}
	return NULL;
}

static int is_dri_fd(int fd)
{
	char lpath[64];
	snprintf(lpath, sizeof(lpath), "/proc/self/fd/%d", fd);
	char link[256];
	ssize_t n = readlink(lpath, link, sizeof(link) - 1);
	if (n < 0)
		return 0;
	link[n] = 0;
	return strstr(link, "/dev/dri/") != NULL;
}

static void cap_gems_snapshot(void)
{
	for (int i = 0; i < MAX_BO; i++) {
		struct bo_entry *b = &bos[i];
		if (!b->used || !b->cpu || !b->map_sz)
			continue;
		struct pant_gem_hdr gh = {
			.type = PANT_GEM,
			.handle = b->handle,
			.gpu_va = b->gpu_va,
			.bo_offset = 0,
			.data_sz = (uint32_t)b->map_sz,
		};
		cap_write(&gh, sizeof(gh));
		cap_write(b->cpu, b->map_sz);
		cap_bump();
	}
}

static void capture_sidecars(unsigned long request, void *arg)
{
	unsigned nr = request & 0xff;
	if (!arg)
		return;

	if (nr == PANTHOR_IOCTL_NR(VM_BIND)) {
		struct drm_panthor_vm_bind *bind = arg;
		if (bind->ops.count && bind->ops.array) {
			size_t sz = (size_t)bind->ops.stride * bind->ops.count;
			cap_side(PANT_SIDE_VM_BIND_OPS, (void *)(uintptr_t)bind->ops.array, (uint32_t)sz);
			struct drm_panthor_vm_bind_op *ops =
				(struct drm_panthor_vm_bind_op *)(uintptr_t)bind->ops.array;
			for (uint32_t i = 0; i < bind->ops.count; i++) {
				if (ops[i].syncs.count && ops[i].syncs.array) {
					size_t ssz = (size_t)ops[i].syncs.stride * ops[i].syncs.count;
					cap_side(PANT_SIDE_BIND_SYNC_OPS, (void *)(uintptr_t)ops[i].syncs.array,
						 (uint32_t)ssz);
				}
			}
		}
		return;
	}

	if (nr == PANTHOR_IOCTL_NR(GROUP_CREATE)) {
		struct drm_panthor_group_create *gc = arg;
		if (gc->queues.count && gc->queues.array) {
			size_t sz = (size_t)gc->queues.stride * gc->queues.count;
			cap_side(PANT_SIDE_GROUP_QUEUES, (void *)(uintptr_t)gc->queues.array, (uint32_t)sz);
		}
		return;
	}

	if (nr == PANTHOR_IOCTL_NR(GROUP_SUBMIT)) {
		struct drm_panthor_group_submit *gs = arg;
		if (gs->queue_submits.count && gs->queue_submits.array) {
			size_t sz = (size_t)gs->queue_submits.stride * gs->queue_submits.count;
			cap_side(PANT_SIDE_QUEUE_SUBMITS, (void *)(uintptr_t)gs->queue_submits.array,
				 (uint32_t)sz);
			struct drm_panthor_queue_submit *qs =
				(struct drm_panthor_queue_submit *)(uintptr_t)gs->queue_submits.array;
			for (uint32_t i = 0; i < gs->queue_submits.count; i++) {
				if (qs[i].syncs.count && qs[i].syncs.array) {
					size_t ssz = (size_t)qs[i].syncs.stride * qs[i].syncs.count;
					cap_side(PANT_SIDE_SYNC_OPS, (void *)(uintptr_t)qs[i].syncs.array,
						 (uint32_t)ssz);
				}
			}
		}
		cap_gems_snapshot();
		return;
	}

	if (nr == PANTHOR_IOCTL_NR(DEV_QUERY)) {
		struct drm_panthor_dev_query *q = arg;
		if (q->size && q->pointer)
			cap_side(PANT_SIDE_DEV_QUERY, (void *)(uintptr_t)q->pointer, q->size);
		return;
	}

	if ((request & 0xff) == 0xc3 && arg) {
		struct drm_syncobj_wait_cap *w = arg;
		if (w->count_handles && w->handles)
			cap_side(PANT_SIDE_SYNCOBJ_HANDLES, (void *)(uintptr_t)w->handles,
				 w->count_handles * sizeof(uint32_t));
	}

	if ((request & 0xff) == 0xca && arg) {
		struct drm_syncobj_timeline_wait *w = arg;
		if (w->count_handles && w->handles)
			cap_side(PANT_SIDE_SYNCOBJ_HANDLES, (void *)(uintptr_t)w->handles,
				 w->count_handles * sizeof(uint32_t));
		if (w->count_handles && w->points)
			cap_side(PANT_SIDE_SYNCOBJ_POINTS, (void *)(uintptr_t)w->points,
				 w->count_handles * sizeof(uint64_t));
	}
}

static void track_post_ioctl(unsigned long request, void *arg, int ret)
{
	if (ret != 0 || !arg)
		return;
	unsigned nr = request & 0xff;

	if (nr == PANTHOR_IOCTL_NR(BO_CREATE)) {
		struct drm_panthor_bo_create *c = arg;
		struct bo_entry *b = bo_alloc(c->handle);
		if (b) {
			b->size = c->size;
			b->handle = c->handle;
		}
		return;
	}

	if (nr == PANTHOR_IOCTL_NR(BO_MMAP_OFFSET)) {
		struct drm_panthor_bo_mmap_offset *m = arg;
		struct bo_entry *b = bo_find(m->handle);
		if (!b || dri_fd < 0)
			return;
		uint64_t map_sz = (b->size + 4095) & ~4095ULL;
		void *cpu = mmap(NULL, map_sz, PROT_READ | PROT_WRITE, MAP_SHARED, dri_fd, m->offset);
		if (cpu != MAP_FAILED) {
			b->cpu = cpu;
			b->map_sz = map_sz;
		}
		return;
	}

	if (nr == PANTHOR_IOCTL_NR(VM_BIND)) {
		struct drm_panthor_vm_bind *bind = arg;
		if (bind->ops.count && bind->ops.array) {
			struct drm_panthor_vm_bind_op *ops =
				(struct drm_panthor_vm_bind_op *)(uintptr_t)bind->ops.array;
			for (uint32_t i = 0; i < bind->ops.count; i++) {
				struct bo_entry *b = bo_find(ops[i].bo_handle);
				if (b)
					b->gpu_va = ops[i].va;
			}
		}
	}
}

static void record_ioctl(int fd, unsigned long request, void *arg, int ret,
			 const void *arg_in, uint32_t arg_sz)
{
	if (!is_dri_fd(fd))
		return;
	cap_open();
	if (cap_fd < 0)
		return;

	struct pant_ioctl_hdr hdr = {
		.type = PANT_IOCTL,
		.request = (uint32_t)request,
		.arg_in_sz = arg_sz,
		.arg_out_sz = arg_sz,
		.ret = ret,
	};
	cap_write(&hdr, sizeof(hdr));
	if (arg_sz && arg_in)
		cap_write(arg_in, arg_sz);
	if (arg_sz && arg)
		cap_write(arg, arg_sz);
	cap_bump();
}

int ioctl(int fd, unsigned long request, ...)
{
	if (!real_ioctl)
		real_ioctl = dlsym(RTLD_NEXT, "ioctl");

	va_list ap;
	va_start(ap, request);
	void *arg = va_arg(ap, void *);
	va_end(ap);

	if (fd >= 0 && is_dri_fd(fd))
		dri_fd = fd;

	uint32_t arg_sz = _IOC_SIZE(request);
	void *arg_in = NULL;
	if (arg_sz && arg) {
		arg_in = malloc(arg_sz);
		if (arg_in)
			memcpy(arg_in, arg, arg_sz);
	}

	if (is_dri_fd(fd) && arg)
		capture_sidecars(request, arg);

	int ret = real_ioctl(fd, request, arg);

	if (arg_in) {
		record_ioctl(fd, request, arg, ret, arg_in, arg_sz);
		track_post_ioctl(request, arg, ret);
		free(arg_in);
	} else {
		record_ioctl(fd, request, arg, ret, NULL, 0);
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
