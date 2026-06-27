/* Panthor NOP test with full DRM init sequence. */
#define _GNU_SOURCE
#include <drm/panthor_drm.h>
#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <unistd.h>

#define DRM_IOCTL_SYNCOBJ_CREATE DRM_IOWR(0xBF, struct drm_syncobj_create)
#define DRM_IOCTL_SYNCOBJ_DESTROY DRM_IOWR(0xC0, struct drm_syncobj_destroy)
#define DRM_IOCTL_SYNCOBJ_WAIT DRM_IOWR(0xC3, struct drm_syncobj_wait)

struct drm_syncobj_create {
	uint32_t handle;
	uint32_t flags;
};

struct drm_syncobj_destroy {
	uint32_t handle;
	uint32_t pad;
};

static void drm_init_caps(int fd)
{
	struct drm_set_version ver = {
		.drm_di_major = 3,
		.drm_di_minor = 0,
		.drm_dd_major = -1,
		.drm_dd_minor = -1,
	};
	ioctl(fd, DRM_IOCTL_SET_VERSION, &ver);

	struct drm_get_cap cap;
	for (int i = 0; i <= 20; i++) {
		cap.capability = i;
		cap.value = 0;
		if (ioctl(fd, DRM_IOCTL_GET_CAP, &cap) == 0 && cap.value)
			fprintf(stderr, "CAP %d = %llu\n", i, (unsigned long long)cap.value);
	}
}

static int sync_bo(int fd, uint32_t handle)
{
	struct drm_prime_handle prime = { .handle = handle, .flags = 0 };
	if (ioctl(fd, DRM_IOCTL_PRIME_HANDLE_TO_FD, &prime) < 0)
		return -1;
	struct { uint64_t flags; } arg = { .flags = (1 << 0) | (1 << 1) | (1 << 2) };
	int ret = ioctl(prime.fd, (1u << 30) | (8u << 16) | ((unsigned)'b' << 8), &arg);
	close(prime.fd);
	return ret;
}

static uint32_t read_flush_id(int fd)
{
	unsigned long pgoff = sizeof(unsigned long) < 8 ?
		DRM_PANTHOR_USER_MMIO_OFFSET_32BIT : DRM_PANTHOR_USER_MMIO_OFFSET_64BIT;
	void *map = mmap(NULL, 4096, PROT_READ, MAP_SHARED, fd, pgoff);
	if (map == MAP_FAILED)
		return 0;
	uint32_t id = *(volatile uint32_t *)map;
	munmap(map, 4096);
	return id;
}

int main(void)
{
	const uint64_t cmd_va = 0x7ffffffe6000ULL;
	const uint32_t cs_size = 8;
	int fd = open("/dev/dri/renderD128", O_RDWR | O_CLOEXEC);
	if (fd < 0) {
		perror("open");
		return 1;
	}

	drm_init_caps(fd);

	struct drm_panthor_dev_query dq;
	struct drm_panthor_gpu_info gpu = { 0 };
	dq.type = DRM_PANTHOR_DEV_QUERY_GPU_INFO;
	dq.size = sizeof(gpu);
	dq.pointer = (uint64_t)(uintptr_t)&gpu;
	ioctl(fd, DRM_IOCTL_PANTHOR_DEV_QUERY, &dq);
	fprintf(stderr, "gpu_id=0x%x shader_present=0x%llx\n", gpu.gpu_id,
		(unsigned long long)gpu.shader_present);

	struct drm_panthor_vm_create vm = { 0 };
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_CREATE, &vm) < 0) {
		perror("VM_CREATE");
		return 1;
	}
	fprintf(stderr, "vm id=%u user_va_range=0x%llx\n", vm.id,
		(unsigned long long)vm.user_va_range);

	struct drm_panthor_tiler_heap_create heap = {
		.vm_id = vm.id,
		.initial_chunk_count = 1,
		.chunk_size = 128 * 1024,
		.max_chunks = 16,
		.target_in_flight = 1,
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_TILER_HEAP_CREATE, &heap) < 0) {
		perror("TILER_HEAP_CREATE");
		return 1;
	}

	struct drm_syncobj_create so = { 0 };
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_CREATE, &so) < 0) {
		perror("SYNCOBJ_CREATE");
		return 1;
	}

	struct drm_panthor_bo_create bo = {
		.size = 4096,
		.flags = 0,
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_CREATE, &bo) < 0) {
		perror("BO_CREATE");
		return 1;
	}

	struct drm_panthor_vm_bind_op bop = {
		.flags = DRM_PANTHOR_VM_BIND_OP_TYPE_MAP,
		.bo_handle = bo.handle,
		.va = cmd_va,
		.size = 4096,
	};
	struct drm_panthor_vm_bind bind = {
		.vm_id = vm.id,
		.ops = DRM_PANTHOR_OBJ_ARRAY(1, &bop),
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_BIND, &bind) < 0) {
		perror("VM_BIND");
		return 1;
	}

	struct drm_panthor_vm_get_state vms = { .vm_id = vm.id };
	if (ioctl(fd, DRM_IOCTL_PANTHOR_VM_GET_STATE, &vms) == 0)
		fprintf(stderr, "vm state=%u (1=usable)\n", vms.state);

	struct drm_panthor_bo_mmap_offset mmap_off = { .handle = bo.handle };
	if (ioctl(fd, DRM_IOCTL_PANTHOR_BO_MMAP_OFFSET, &mmap_off) < 0) {
		perror("BO_MMAP_OFFSET");
		return 1;
	}

	void *map = mmap(NULL, 4096, PROT_READ | PROT_WRITE, MAP_SHARED, fd, mmap_off.offset);
	if (map == MAP_FAILED) {
		perror("mmap");
		return 1;
	}
	memset(map, 0, cs_size);
	sync_bo(fd, bo.handle);

	struct drm_panthor_queue_create queue = { .priority = 0, .ringbuf_size = 65536 };
	struct drm_panthor_group_create grp = {
		.queues = DRM_PANTHOR_OBJ_ARRAY(1, &queue),
		.max_compute_cores = 1,
		.max_fragment_cores = 0,
		.max_tiler_cores = 0,
		.priority = PANTHOR_GROUP_PRIORITY_MEDIUM,
		.compute_core_mask = 1,
		.fragment_core_mask = 0,
		.tiler_core_mask = 0,
		.vm_id = vm.id,
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_CREATE, &grp) < 0) {
		perror("GROUP_CREATE");
		return 1;
	}

	uint32_t latest_flush = read_flush_id(fd);
	struct drm_panthor_sync_op sync = {
		.flags = DRM_PANTHOR_SYNC_OP_SIGNAL,
		.handle = so.handle,
	};
	struct drm_panthor_queue_submit qs = {
		.queue_index = 0,
		.stream_size = cs_size,
		.stream_addr = cmd_va,
		.latest_flush = latest_flush,
		.syncs = DRM_PANTHOR_OBJ_ARRAY(1, &sync),
	};
	struct drm_panthor_group_submit gs = {
		.group_handle = grp.group_handle,
		.queue_submits = DRM_PANTHOR_OBJ_ARRAY(1, &qs),
	};
	if (ioctl(fd, DRM_IOCTL_PANTHOR_GROUP_SUBMIT, &gs) < 0) {
		perror("GROUP_SUBMIT");
		return 1;
	}

	uint32_t handle = so.handle;
	struct drm_syncobj_wait wait = {
		.handles = (uint64_t)(uintptr_t)&handle,
		.timeout_nsec = 10000000000LL,
		.count_handles = 1,
	};
	if (ioctl(fd, DRM_IOCTL_SYNCOBJ_WAIT, &wait) < 0) {
		fprintf(stderr, "SYNCOBJ_WAIT: %s (latest_flush=%u)\n", strerror(errno), latest_flush);
		return 1;
	}

	printf("PASS\n");
	return 0;
}
