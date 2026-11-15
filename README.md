# clorraine-installer

Cross-platform installer for [Clorraine](https://github.com/OpenLorraine/clorraine),
built with the [Qt Installer Framework](https://doc.qt.io/qtinstallerframework/).

The installer provides a graphical setup wizard and an unattended command-line
mode. It is a thin online installer: it embeds no component payload and
downloads the selected components from a Qt Installer Framework repository.
The installed maintenance tool adds, updates, and removes components.

## Status

**Online channel scaffold.** The project builds a per-platform component
repository and a thin installer. The Amiga SDK component, editor extension,
and publishing workflow are not implemented yet.

## How it works

| Piece | Responsibility |
|---|---|
| Repository | Single source of truth; built with `repogen` and copied to any HTTPS host |
| Installer | Built with `binarycreator -n`; contains the repository URL and downloads everything |
| Maintenance tool | Installed with the product; updates and removes components |

Repositories are **per platform**, because component payloads are platform
specific. The configured URL contains a `{platform}` placeholder that the
build tool replaces with the build host's `<os>-<arch>` slug, for example
`linux-x86_64`.

The installer version in `config/config.xml` identifies the installer build.
The component version comes from `--version` and identifies the Clorraine
release. They are independent: the stable channel always installs the latest
components.

## Components

| Component | Status | Contents |
|---|---|---|
| `org.openlorraine.clorraine.core` | scaffolded | `clc`, `clorraine`, `clorraine-lsp`, licence notices |
| `org.openlorraine.clorraine.sdk` | planned | Amiga cross-compilation and emulation environment |
| `org.openlorraine.clorraine.editor` | planned | VS Code extension |

Building host programs needs a C99 compiler on `PATH` named `cc`
(GCC/Clang compatible). The installer reports whether one is available; it does
not bundle a host C toolchain.

## Building

Requirements:

- Qt Installer Framework 4.x, which provides `binarycreator` and `repogen`.
- Python 3.9 or newer for the build tool.
- A payload directory containing the release binaries for the build host.

```sh
python3 tools/build_installer.py \
    --version 1.1.2 \
    --payload ../clorraine/build/release/v1.1.2/linux-x86_64
```

This writes:

| Output | Default location |
|---|---|
| Component repository | `build/repository/` |
| Thin online installer | `build/out/clorraine-installer-1.0.0-<platform>` |

Pass `--qtifw /path/to/QtInstallerFramework` when the tools are not on `PATH`.

### Choosing the download location

The URL is baked into the installer and can be changed per build:

```sh
python3 tools/build_installer.py \
    --version 1.1.2 \
    --payload DIR \
    --repository-url https://cdn.example.com/clorraine/linux-x86_64/
```

Without `--repository-url`, the URL in `config/config.xml` is used with
`{platform}` replaced. Point it at a stable vanity URL or CDN so moving the
physical storage later does not invalidate installers.

## Publishing the repository

Copy the contents of `build/repository/` to the configured URL. Qt Installer
Framework resolves archives relative to `Updates.xml`, so the repository is
relocatable.

On object storage, upload component directories first and `Updates.xml` last.
Otherwise clients can see metadata that points at archives that are not
uploaded yet. Atomic deployments, such as a GitHub Pages artifact, avoid this
ordering problem.

Use HTTPS. Qt Installer Framework has no documented repository signing; it
verifies archive hashes from `Updates.xml`, which catches corruption but not a
compromised host. Sign the installer binaries separately for Windows and macOS.

## Checks

```sh
xmllint --noout config/config.xml packages/*/meta/package.xml
python3 -m py_compile tools/build_installer.py
python3 -m unittest discover -s tools/tests -t . -v

# End-to-end online install; needs QtIFW and curl.
QTIFW_DIR=/path/to/QtInstallerFramework tools/smoke-online-install.sh
```

The smoke test builds a stub repository, serves it on a local port, builds an
installer against that URL, installs unattended, runs the installed compiler,
and purges the installation.

### Try the wizard locally

```sh
QTIFW_DIR=/path/to/QtInstallerFramework tools/demo-online-install.sh
```

This builds stub tools, serves a local repository, and opens the real wizard.
The installed stubs only answer `--version`; they are not a compiler. The demo
installs under `build/demo/install`.

On Linux, the Qt GUI needs the X11 runtime libraries. On Debian or Ubuntu:

```sh
sudo apt-get install -y \
  libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 \
  libxcb-render-util0 libxcb-xkb1 libxcb-shape0 libxcb-randr0 \
  libxcb-xfixes0 libxcb-sync1 libxcb-shm0 libxcb-glx0 libxcb-xinerama0
```

These are runtime dependencies of every Linux installer built with Qt
Installer Framework, not only of the demo.

## Layout

| Path | Purpose |
|---|---|
| `config/config.xml` | Installer identity, target directory, repository URL |
| `packages/<component>/meta/` | Component metadata, install script, licence text |
| `packages/<component>/data/` | Payload assembled by the build tool (not committed) |
| `tools/build_installer.py` | Verification, staging, `repogen`, and `binarycreator` |
| `tools/smoke-online-install.sh` | Local end-to-end online install check |
| `tools/tests/` | Unit tests for the build tool |
| `docs/release-artifacts.md` | Release binary input contract |

## Licensing

Project files are Apache-2.0, matching the Clorraine compiler repository; see
[LICENSE](LICENSE) and [NOTICE](NOTICE). Qt Installer Framework is licensed
under GPL-3.0-only with the Qt GPL exception, which permits distributing
generated installers under other terms. Review the licensing of the Qt runtime
that is statically linked into an installer before public distribution.
Clorraine trademarks are described in the compiler repository's
`TRADEMARKS.md`.
