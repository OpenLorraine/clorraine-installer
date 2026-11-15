# Installer input contract

The installer repository consumes release artifacts and never builds the
compiler. This keeps installation fixes independent from compiler releases and
gives both repositories a small, explicit interface.

## Payload directory

`tools/build_installer.py --payload DIR` expects an extracted release payload
for the build host's operating system and CPU architecture.

| Path | Required | Purpose |
|---|---|---|
| `clc` (`clc.exe` on Windows) | yes | Compiler |
| `clorraine` (`clorraine.exe` on Windows) | yes | Build/run driver |
| `clorraine-lsp` (`clorraine-lsp.exe` on Windows) | yes | Language server |
| `SHA256SUMS` | recommended | Payload integrity check |
| `LICENSE`, `LICENSE-EXCEPTION.md`, `NOTICE`, `TRADEMARKS.md`, `THIRD_PARTY_NOTICES.md` | optional | Copied to `share/doc/clorraine` |

The build tool rejects a payload that omits any required executable. Entries in
`SHA256SUMS` that name files outside the payload directory are ignored, so a
release-level checksum file may list source archives as well.

The current Linux release tarball predates this contract and ships only `clc`
and `clorraine`. The compiler repository's release job must include
`clorraine-lsp` before the installer can consume that artifact.

## Versions

| Value | Source | Meaning |
|---|---|---|
| Component version | `--version` | Clorraine release installed from the repository |
| Component release date | `--release-date` (default: build date) | Metadata for the component |
| Installer version | `config/config.xml` | Installer build; independent of the compiler |

The build tool rewrites the component values only in the staging copy. The
source project is never modified.

## Repository location

The repository URL is baked into the installer at build time:

- `--repository-url URL` uses the exact URL and skips placeholder substitution.
- Otherwise the `<Url>` in `config/config.xml` is used with `{platform}`
  replaced by the build host's `<os>-<arch>` slug.

Repositories are per platform because the component payloads are platform
specific. `build/repository/` is relocatable: `Updates.xml` references
archives relative to itself.

## Release pipeline responsibility

The pipeline that downloads a release archive must verify the published
SHA-256 digest before extracting it. The build tool then verifies the extracted
payload when it includes its own `SHA256SUMS`.

## Publishing

Copy `build/repository/` to the configured URL. On object storage, upload
component directories before `Updates.xml`. Use HTTPS. Qt Installer Framework
has no documented repository signing, so host integrity controls and signed
installer binaries carry the trust.
