#!/usr/bin/env bash
# Launch a local demo of the online installer with stub binaries.
#
# The demo builds a stub payload, a local component repository, and a thin
# installer that downloads from a local HTTP server. It then opens the real
# Qt Installer Framework wizard with the installation directory set to
# build/demo/install.
#
# Environment:
#   QTIFW_DIR  Qt Installer Framework root; optional when its tools are on PATH.
#   PORT       Local repository port; defaults to an available port.
#
# The stub tools only answer --version. They are not a compiler.

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=${VERSION:-0.0.0-demo}
DEMO_ROOT="$ROOT/build/demo"
PAYLOAD="$DEMO_ROOT/payload"
SERVER_PID=""

# The Qt platform plugin needs the X11 runtime libraries. Without them the
# installer exits in the dynamic loader with a message that does not mention
# Clorraine, so check before building.
if ! ldconfig -p 2>/dev/null | grep -q 'libxkbcommon-x11\.so\.0'; then
    cat >&2 <<'EOF'
The Qt GUI needs the X11 runtime libraries, which are not installed.
On Debian or Ubuntu, run:

  sudo apt-get install -y \
    libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
    libxcb-render-util0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
    libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-glx0 libxcb-xinerama0
EOF
    exit 1
fi

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
}
trap cleanup EXIT

mkdir -p "$PAYLOAD"
for name in clc clorraine clorraine-lsp; do
    printf '#!/bin/sh\nif [ "${1:-}" = "--version" ]; then\n    echo "%s %s (demo stub)"\n    exit 0\nfi\necho "%s %s (demo stub): this is a packaging demo, not a real Clorraine tool"\n' \
        "$name" "$VERSION" "$name" "$VERSION" >"$PAYLOAD/$name"
    chmod +x "$PAYLOAD/$name"
done

PORT=${PORT:-$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')}
REPOSITORY_URL="http://127.0.0.1:$PORT/"

cd "$ROOT"
BUILD_ARGS=(
    --version "$VERSION"
    --payload "$PAYLOAD"
    --repository-url "$REPOSITORY_URL"
    --repository-output "$DEMO_ROOT/repository"
    --target-dir "$DEMO_ROOT/install"
    --output "$DEMO_ROOT/clorraine-installer-demo.run"
)
if [ -n "${QTIFW_DIR:-}" ]; then
    BUILD_ARGS+=(--qtifw "$QTIFW_DIR")
fi
python3 tools/build_installer.py "${BUILD_ARGS[@]}"

python3 -m http.server "$PORT" --bind 127.0.0.1 \
    --directory "$DEMO_ROOT/repository" >"$DEMO_ROOT/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 50); do
    if curl -fsS "${REPOSITORY_URL}Updates.xml" >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done

rm -rf "$DEMO_ROOT/install"
"$DEMO_ROOT/clorraine-installer-demo.run"

echo "demo installation: $DEMO_ROOT/install"
