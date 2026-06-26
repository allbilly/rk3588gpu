CC ?= gcc
CFLAGS = -g -Wall -Wextra -O2 -fPIC
LDFLAGS = -shared -ldl

.PHONY: all clean capture replay sample test-dry

all: capture/kbase_capture.so

capture/kbase_capture.so: capture/kbase_capture.c
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ $<

sample:
	python3 tools/mcap.py gen-sample -o test.mcap

test-dry: sample
	python3 replay.py test.mcap --dry-run

replay:
	chmod +x replay.py
	python3 replay.py $(CAP) --dry-run

capture: capture/kbase_capture.so
	@test -n "$(APP)" || (echo "usage: make capture APP=./glmark2-es2 CAP=/tmp/foo.mcap" && exit 1)
	CAPTURE_PATH=$(or $(CAP),test.mcap) LD_PRELOAD=$(CURDIR)/capture/kbase_capture.so $(APP)
	@echo "wrote $(or $(CAP),test.mcap) ($$(wc -c < $(or $(CAP),test.mcap)) bytes)"

clean:
	rm -f capture/kbase_capture.so test.mcap
