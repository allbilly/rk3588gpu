CC ?= gcc
CFLAGS = -O2 -Wall -Wextra
LDFLAGS = -lOpenCL

.PHONY: cl-add clean

cl-add: cl_add
	RUSTICL_ENABLE=panfrost ./cl_add

cl_add: cl_add.c
	$(CC) $(CFLAGS) -o $@ $< $(LDFLAGS)

clean:
	rm -f cl_add
