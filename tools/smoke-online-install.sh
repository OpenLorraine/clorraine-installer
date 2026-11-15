#!/usr/bin/env bash
# End-to-end check for the online installer.
#
# Builds a repository from a stub or real payload, serves it locally, builds a
# thin installer against that URL, installs unattended, runs the installed
# compiler, and purges the installation.
#
# Usage:
#   QTIFW_DIR=/path/to/QtInstallerFramework tools/smoke-online-install.sh
#
# Environment:
#   QTIFW_DIR    Qt Installer Framework root; optional when its tools are on PATH.
#   PAYLOAD_DIR  Directory with clc, clorraine, and clorraine-lsp. A stub
#                payload is created when this is unset.
#   VERSION      Component version for the test build (default: 0.0.0-smoke).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
VERSION=${VERSION:-0.0.0-smoke}
TMPROOT=$(mktemp -d "${TMPDIR:-/tmp}/clorraine-installer-smoke.XXXXXX")
SERVER_PID=""

cleanup() {
    if [ -n "$SERVER_PID" ]; then
        kill "$SERVER_PID" 2>/dev/null || true
        wait "$SERVER_PID" 2>/dev/null || true
    fi
    rm -rf "$TMPROOT"
}
trap cleanup EXIT

PAYLOAD_DIR=${PAYLOAD_DIR:-"$TMPROOT/payload"}
if [ ! -d "$PAYLOAD_DIR" ]; then
    mkdir -p "$PAYLOAD_DIR"
    for name in clc clorraine clorraine-lsp; do
        printf '#!/bin/sh\nprintf "%s %s (stub)\\n"\n' "$name" "$VERSION" \
            >"$PAYLOAD_DIR/$name"
        chmod +x "$PAYLOAD_DIR/$name"
    done
fi

PORT=$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1]); s.close()')
REPOSITORY_URL="http://127.0.0.1:$PORT/"
INSTALLER="$ROOT/build/out/clorraine-installer-smoke.run"

cd "$ROOT"
BUILD_ARGS=(
    --version "$VERSION"
    --payload "$PAYLOAD_DIR"
    --repository-url "$REPOSITORY_URL"
    --repository-output "$ROOT/build/repository"
    --output "$INSTALLER"
)
if [ -n "${QTIFW_DIR:-}" ]; then
    BUILD_ARGS+=(--qtifw "$QTIFW_DIR")
fi
python3 tools/build_installer.py "${BUILD_ARGS[@]}"

python3 -m http.server "$PORT" --bind 127.0.0.1 \
    --directory "$ROOT/build/repository" >"$TMPROOT/server.log" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 50); do
    if curl -fsS "${REPOSITORY_URL}Updates.xml" >/dev/null 2>&1; then
        break
    fi
    sleep 0.1
done

INSTALL_ROOT="$TMPROOT/install"
"$INSTALLER" -p offscreen --accept-licenses --default-answer --confirm-command \
    install -t "$INSTALL_ROOT" >"$TMPROOT/install.log" 2>&1 || {
    cat "$TMPROOT/install.log" >&2
    exit 1
}

"$INSTALL_ROOT/bin/clc" --version

"$INSTALL_ROOT/ClorraineMaintenanceTool" \
    -p offscreen --accept-licenses --default-answer --confirm-command \
    purge >"$TMPROOT/purge.log" 2>&1 || {
    cat "$TMPROOT/purge.log" >&2
    exit 1
}

echo "online install smoke test passed"
