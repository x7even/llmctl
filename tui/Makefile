# go is frequently missing from the PATH of non-interactive shells, and of shells older
# than the profile line that added it, and make runs recipes under /bin/sh — so look in the
# usual install locations before failing, with a message more useful than "go: not found"
# and exit 127. Override with `make build GO=/path/to/go`.
GO      := $(shell command -v go 2>/dev/null || \
             for g in "$(GOROOT)/bin/go" /usr/local/go/bin/go; do \
               [ -x "$$g" ] && { echo "$$g"; break; }; \
             done)
BIN     := ../bin/llmpanel
INSTALL := $(HOME)/.local/bin/llmpanel
VERSION := $(shell git -C .. describe --tags --always --dirty 2>/dev/null || echo dev)

.PHONY: build install clean tidy

build: check-go
	$(GO) build -ldflags="-s -w -X main.version=$(VERSION)" -o $(BIN) .

install: build
	ln -sf "$(abspath $(BIN))" $(INSTALL)
	@echo "Installed: llmpanel → $(INSTALL)"

tidy: check-go
	$(GO) mod tidy

clean:
	rm -f $(BIN)

.PHONY: check-go
check-go:
	@test -n "$(GO)" || { \
	  echo "make: go not found. Put it on PATH or pass GO=/path/to/go" >&2; exit 1; }
