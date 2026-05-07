#!/usr/bin/env bash
# Install llmpanel — the llmstack terminal control panel.
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/x7even/llmctl/master/install-llmpanel.sh | bash
#   INSTALL_DIR=/usr/local/bin bash install-llmpanel.sh   # custom location
set -euo pipefail

REPO="x7even/llmctl"
BIN="llmpanel"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)  ARCH=amd64 ;;
  aarch64) ARCH=arm64 ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 1 ;;
esac

if [[ "$OS" != "linux" ]]; then
  echo "Only Linux is currently supported." >&2; exit 1
fi

TAG=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
  | grep '"tag_name"' | cut -d'"' -f4)

if [[ -z "$TAG" ]]; then
  echo "Could not determine latest release — check https://github.com/${REPO}/releases" >&2
  exit 1
fi

URL="https://github.com/${REPO}/releases/download/${TAG}/${BIN}-${OS}-${ARCH}"

echo "Installing ${BIN} ${TAG} (${OS}/${ARCH}) → ${INSTALL_DIR}/${BIN}"
mkdir -p "$INSTALL_DIR"
curl -fsSL "$URL" -o "${INSTALL_DIR}/${BIN}"
chmod +x "${INSTALL_DIR}/${BIN}"

if ! echo "$PATH" | grep -q "$INSTALL_DIR"; then
  echo "Note: ${INSTALL_DIR} is not in your PATH. Add it:"
  echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo "Done. Run: ${BIN} --version"
