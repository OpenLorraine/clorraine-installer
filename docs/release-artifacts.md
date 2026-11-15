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

## Version and date

`--version` stamps the installer and core component version.
`--release-date` defaults to the build date. The versions committed in
`config/config.xml` and `packages/*/meta/package.xml` are placeholders; the
build tool rewrites them only in the staging copy.

## Release pipeline responsibility

The pipeline that downloads a release archive must verify the published
SHA-256 digest before extracting it. The build tool then verifies the extracted
payload when it includes its own `SHA256SUMS`.

## Future online components

The first builds are offline installers that embed the selected payload. Once a
published Qt Installer Framework repository exists, the same component
metadata is reused with `repogen`, and the repository URL is added to
`config/config.xml`. Installation-time downloads are then verified by Qt
Installer Framework against the repository metadata rather than by this build
tool.
