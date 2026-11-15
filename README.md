# clorraine-installer

Cross-platform installer for [Clorraine](https://github.com/OpenLorraine/clorraine),
built with the [Qt Installer Framework](https://doc.qt.io/qtinstallerframework/).

The same installer project provides a graphical setup wizard and an unattended
command-line mode. It installs the Clorraine compiler, driver, and language
server, verifies that the installed compiler runs, and keeps a maintenance tool
for later updates and uninstallation.

## Status

**Scaffold.** The project builds an offline installer for the core component.
The Amiga SDK component, the online component repository, PATH integration, and
editor extension packaging are not implemented yet.

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

- Qt Installer Framework 4.x, which provides `binarycreator`.
- Python 3.9 or newer for the build tool.
- A payload directory containing the release binaries built for the host
  platform.

```sh
python3 tools/build_installer.py \
    --version 1.1.2 \
    --payload ../clorraine/build/release/v1.1.2/linux-x86_64 \
    --output build/out/clorraine-1.1.2-linux-x86_64.run
```

Pass `--qtifw /path/to/QtInstallerFramework` when `binarycreator` is not on
`PATH`.

The build tool verifies `SHA256SUMS` when the payload contains it, copies the
payload into `build/staging/`, stamps the version into a staging copy of the
metadata, and invokes QtIFW. The input contract is documented in
[docs/release-artifacts.md](docs/release-artifacts.md).

QtIFW builds one platform at a time. Produce the Linux, macOS, and Windows
installers on their respective systems, or in a release workflow that runs the
same command on each platform.

## Layout

| Path | Purpose |
|---|---|
| `config/config.xml` | Installer identity, target directory, maintenance tool |
| `packages/<component>/meta/` | Component metadata, install script, licence text |
| `packages/<component>/data/` | Payload assembled by the build tool (not committed) |
| `tools/build_installer.py` | Payload verification, staging, and QtIFW invocation |
| `tools/tests/` | Unit tests for the build tool |
| `docs/release-artifacts.md` | Release binary input contract |

## Checks

```sh
xmllint --noout config/config.xml packages/*/meta/package.xml
python3 -m py_compile tools/build_installer.py
python3 -m unittest discover -s tools/tests -t . -v
```

## Licensing

Project files are Apache-2.0, matching the Clorraine compiler repository; see
[LICENSE](LICENSE) and [NOTICE](NOTICE). Qt Installer Framework is licensed
under GPL-3.0-only with the Qt GPL exception, which permits distributing
generated installers under other terms. Review the licensing of the Qt runtime
that is statically linked into an installer before public distribution.
Clorraine trademarks are described in the compiler repository's
`TRADEMARKS.md`.
