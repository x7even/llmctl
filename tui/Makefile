GO      := $(shell command -v go 2>/dev/null || echo /home/xin/go-sdk/go/bin/go)
BIN     := ../bin/llmpanel
INSTALL := $(HOME)/.local/bin/llmpanel
VERSION := $(shell git -C .. describe --tags --always --dirty 2>/dev/null || echo dev)

.PHONY: build install clean tidy

build:
	$(GO) build -ldflags="-s -w -X main.version=$(VERSION)" -o $(BIN) .

install: build
	ln -sf "$(abspath $(BIN))" $(INSTALL)
	@echo "Installed: llmpanel → $(INSTALL)"

tidy:
	$(GO) mod tidy

clean:
	rm -f $(BIN)
