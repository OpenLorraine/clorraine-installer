#!/usr/bin/env bash
# Run a command in the Linux installer build container.
#
# The repository is mounted at /work and the container runs as the host user,
# so build outputs stay owned by you. The image is built on first use. When
# DISPLAY points at a local X socket, the socket and Xauthority are forwarded
# so the wizard demo can open on the host.
#
# Usage:
#   docker/run.sh python3 -m unittest discover -s tools/tests -t . -v
#   docker/run.sh tools/smoke-online-install.sh
#   docker/run.sh tools/demo-online-install.sh
#
# Environment:
#   IMAGE  Image tag (default: clorraine-installer-builder).

set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
IMAGE=${IMAGE:-clorraine-installer-builder}

if ! command -v docker >/dev/null 2>&1; then
    echo "error: docker is required to use the build container" >&2
    exit 1
fi

if ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
    echo "building $IMAGE"
    docker build -t "$IMAGE" "$ROOT/docker"
fi

RUN_ARGS=(--rm -v "$ROOT:/work" -w /work)
RUN_ARGS+=(--user "$(id -u):$(id -g)" -e HOME=/tmp)

if [ -n "${DISPLAY:-}" ]; then
    DISPLAY_NUMBER=${DISPLAY#*:}
    DISPLAY_NUMBER=${DISPLAY_NUMBER%%.*}
    if [ -S "/tmp/.X11-unix/X${DISPLAY_NUMBER}" ]; then
        RUN_ARGS+=(-e "DISPLAY=${DISPLAY}")
        RUN_ARGS+=(-v /tmp/.X11-unix:/tmp/.X11-unix:ro)
        XAUTHORITY_FILE=${XAUTHORITY:-$HOME/.Xauthority}
        if [ -f "$XAUTHORITY_FILE" ]; then
            RUN_ARGS+=(-e XAUTHORITY=/tmp/.Xauthority)
            RUN_ARGS+=(-v "$XAUTHORITY_FILE:/tmp/.Xauthority:ro")
        fi
    fi
fi

exec docker run "${RUN_ARGS[@]}" "$IMAGE" "$@"
