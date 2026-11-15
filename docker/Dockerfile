# Build environment for Linux Clorraine installers.
#
# Qt Installer Framework's tools are linked against the Qt X11 libraries even
# when they run without a display. Keeping those libraries here avoids
# installing the whole set on a developer machine. The installers produced here
# are native Linux applications and still need the libraries on the target.
#
# The image builds Linux installers only. macOS and Windows installers must be
# built on their own platforms.
#
# QtIFW is licensed under GPL-3.0-only with the Qt GPL exception. This image is
# a build environment, not a redistributed Clorraine artifact.

FROM debian:bookworm-slim

ARG DEBIAN_FRONTEND=noninteractive
ARG AQTINSTALL_VERSION=3.3.0
ARG QTIFW_VARIANT=qt.tools.ifw.47
ARG QTIFW_ROOT=/opt/qtifw/Tools/QtInstallerFramework/4.7

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        python3 \
        python3-venv \
        libdbus-1-3 \
        libfontconfig1 \
        libfreetype6 \
        libice6 \
        libsm6 \
        libx11-6 \
        libx11-xcb1 \
        libxext6 \
        libxi6 \
        libxrender1 \
        libxtst6 \
        libxkbcommon-x11-0 \
        libxcb-icccm4 \
        libxcb-image0 \
        libxcb-keysyms1 \
        libxcb-render-util0 \
        libxcb-xkb1 \
        libxcb-shape0 \
        libxcb-randr0 \
        libxcb-xfixes0 \
        libxcb-sync1 \
        libxcb-shm0 \
        libxcb-glx0 \
        libxcb-xinerama0 \
    && rm -rf /var/lib/apt/lists/*

RUN python3 -m venv /opt/aqt \
    && /opt/aqt/bin/pip install --no-cache-dir "aqtinstall==${AQTINSTALL_VERSION}" \
    && /opt/aqt/bin/aqt install-tool linux desktop tools_ifw \
        "${QTIFW_VARIANT}" -O /opt/qtifw

# Resolving the version through one symlink keeps $ORIGIN/../lib working for
# the dynamically linked QtIFW tools.
RUN ln -s "${QTIFW_ROOT}" /opt/qtifw-current
ENV PATH="/opt/qtifw-current/bin:${PATH}"
ENV LANG=C.UTF-8
ENV LC_ALL=C.UTF-8

WORKDIR /work
CMD ["bash"]
