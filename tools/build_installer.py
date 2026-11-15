#!/usr/bin/env python3
"""Assemble a Clorraine installer from release binaries.

This tool owns the packaging step only. It verifies the payload, copies it into
a staging tree, stamps the release version into the Qt Installer Framework
metadata, and invokes ``binarycreator``. Downloading the payload belongs to the
release pipeline; component downloads at installation time belong to a Qt
Installer Framework repository.

Usage::

    python3 tools/build_installer.py --version 1.1.2 --payload DIR
"""

from __future__ import annotations

import argparse
import datetime
import hashlib
import platform
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

CORE_COMPONENT = "org.openlorraine.clorraine.core"
PROJECT_ROOT = Path(__file__).resolve().parents[1]

#: Executable base names shipped by the core component. The platform suffix is
#: added by :func:`binary_filename`.
BINARY_NAMES = ("clc", "clorraine", "clorraine-lsp")

#: Release documents copied next to the installed binaries when present in the
#: payload directory.
DOCUMENT_NAMES = (
    "LICENSE",
    "LICENSE-EXCEPTION.md",
    "NOTICE",
    "TRADEMARKS.md",
    "THIRD_PARTY_NOTICES.md",
)


class BuildError(Exception):
    """Raised when the payload or the build environment is invalid."""


def normalize_os(system: str) -> str:
    """Map ``platform.system()`` values to the installer's OS slugs."""
    normalized = system.strip().lower()
    if normalized == "linux":
        return "linux"
    if normalized == "darwin":
        return "macos"
    if normalized == "windows":
        return "windows"
    raise BuildError(f"unsupported operating system: {system}")


def normalize_arch(machine: str) -> str:
    """Map ``platform.machine()`` values to the installer's CPU slugs."""
    normalized = machine.strip().lower()
    if normalized in ("x86_64", "amd64"):
        return "x86_64"
    if normalized in ("arm64", "aarch64"):
        return "aarch64"
    raise BuildError(f"unsupported CPU architecture: {machine}")


def platform_slug(system: str | None = None, machine: str | None = None) -> str:
    """Return the ``<os>-<arch>`` slug for the build host or given values."""
    return "{}-{}".format(
        normalize_os(system or platform.system()),
        normalize_arch(machine or platform.machine()),
    )


def binary_filename(name: str, system: str | None = None) -> str:
    """Return the release file name for ``name`` on ``system``."""
    suffix = ".exe" if normalize_os(system or platform.system()) == "windows" else ""
    return name + suffix


def default_output_name(
    version: str, system: str | None = None, machine: str | None = None
) -> str:
    """Return the conventional installer file name for the build host."""
    os_slug = normalize_os(system or platform.system())
    suffix = {"linux": ".run", "macos": ".app", "windows": ".exe"}[os_slug]
    return f"clorraine-{version}-{platform_slug(system, machine)}{suffix}"


def verify_checksums(payload_dir: Path) -> int:
    """Verify every payload file listed in ``SHA256SUMS``.

    The file may also list release archives that are not part of the payload
    directory; those entries are ignored. Returns the number of verified files.
    Raises :class:`BuildError` when a file is missing from the manifest or a
    digest does not match.
    """
    sums_path = payload_dir / "SHA256SUMS"
    if not sums_path.is_file():
        return 0

    verified = 0
    for line_number, raw_line in enumerate(
        sums_path.read_text(encoding="utf-8").splitlines(), start=1
    ):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        if len(parts) < 2:
            raise BuildError(f"{sums_path}:{line_number}: malformed checksum entry")
        digest, filename = parts[0], parts[-1].lstrip("*")

        target = payload_dir / filename
        if not target.is_file():
            continue
        actual = hashlib.sha256(target.read_bytes()).hexdigest()
        if actual.lower() != digest.lower():
            raise BuildError(
                f"{target}: SHA-256 mismatch (expected {digest}, got {actual})"
            )
        verified += 1

    return verified


def verify_payload(payload_dir: Path, system: str | None = None) -> list[Path]:
    """Check that the payload contains every required binary.

    Returns the binary paths in :data:`BINARY_NAMES` order.
    """
    if not payload_dir.is_dir():
        raise BuildError(f"payload directory does not exist: {payload_dir}")

    binaries = []
    for name in BINARY_NAMES:
        path = payload_dir / binary_filename(name, system)
        if not path.is_file():
            raise BuildError(f"payload is missing {path.name}: {payload_dir}")
        binaries.append(path)
    return binaries


def set_xml_text(path: Path, tag: str, value: str) -> None:
    """Replace the single ``<tag>`` element in an XML file with ``value``.

    Parsing, rather than text matching, keeps tag names inside comments from
    being mistaken for the real element. Raises :class:`BuildError` when the
    element is missing or ambiguous, so a metadata change cannot silently stop
    the version stamping.
    """
    tree = ET.parse(path)
    matches = tree.getroot().findall(f".//{tag}")
    if len(matches) != 1:
        raise BuildError(
            f"{path}: expected exactly one <{tag}> element, found {len(matches)}"
        )

    matches[0].text = value
    tree.write(path, encoding="utf-8", xml_declaration=True)


def stage_project(
    project_root: Path,
    staging_dir: Path,
    version: str,
    release_date: str,
    payload_dir: Path,
    system: str | None = None,
) -> Path:
    """Copy metadata and payload into ``staging_dir`` and stamp the version.

    Returns the staging directory. The source project is never modified.
    """
    binaries = verify_payload(payload_dir, system)

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    shutil.copytree(project_root / "config", staging_dir / "config")
    shutil.copytree(project_root / "packages", staging_dir / "packages")

    set_xml_text(staging_dir / "config" / "config.xml", "Version", version)
    set_xml_text(
        staging_dir / "packages" / CORE_COMPONENT / "meta" / "package.xml",
        "Version",
        version,
    )
    set_xml_text(
        staging_dir / "packages" / CORE_COMPONENT / "meta" / "package.xml",
        "ReleaseDate",
        release_date,
    )

    bin_dir = staging_dir / "packages" / CORE_COMPONENT / "data" / "bin"
    bin_dir.mkdir(parents=True)
    for binary in binaries:
        shutil.copy2(binary, bin_dir / binary.name)

    doc_dir = (
        staging_dir
        / "packages"
        / CORE_COMPONENT
        / "data"
        / "share"
        / "doc"
        / "clorraine"
    )
    for name in DOCUMENT_NAMES:
        source = payload_dir / name
        if source.is_file():
            doc_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, doc_dir / name)

    return staging_dir


def find_binarycreator(qtifw_dir: Path | None = None) -> Path:
    """Locate ``binarycreator`` from an explicit QtIFW root or ``PATH``."""
    executable = (
        "binarycreator.exe" if platform.system() == "Windows" else "binarycreator"
    )
    candidates: list[Path] = []
    if qtifw_dir is not None:
        candidates.extend((qtifw_dir / "bin" / executable, qtifw_dir / executable))

    on_path = shutil.which("binarycreator")
    if on_path:
        candidates.append(Path(on_path))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise BuildError(
        "binarycreator was not found; install Qt Installer Framework 4.x "
        "or pass --qtifw <QtInstallerFramework root>"
    )


def run_binarycreator(
    binarycreator: Path, staging_dir: Path, output: Path
) -> None:
    """Invoke QtIFW to build the offline installer at ``output``."""
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(binarycreator),
        "--offline-only",
        "-c",
        str(staging_dir / "config" / "config.xml"),
        "-p",
        str(staging_dir / "packages"),
        str(output),
    ]
    print("+ " + " ".join(command))
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise BuildError(
            f"binarycreator failed with exit status {completed.returncode}"
        )


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse the command line for :func:`main`."""
    parser = argparse.ArgumentParser(
        description="Build a Clorraine installer from a release payload."
    )
    parser.add_argument("--version", required=True, help="Clorraine release version")
    parser.add_argument(
        "--payload",
        required=True,
        type=Path,
        help="directory containing clc, clorraine, and clorraine-lsp",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="installer path; defaults to build/out/<platform name>",
    )
    parser.add_argument(
        "--qtifw",
        type=Path,
        help="Qt Installer Framework root when binarycreator is not on PATH",
    )
    parser.add_argument(
        "--release-date",
        default=datetime.date.today().isoformat(),
        help="component release date in YYYY-MM-DD form (default: today)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Build the installer and report success or a build error."""
    arguments = parse_arguments(argv)
    try:
        verified = verify_checksums(arguments.payload.resolve())
        if verified:
            print(f"verified {verified} file(s) with SHA256SUMS")

        staging_dir = PROJECT_ROOT / "build" / "staging"
        stage_project(
            PROJECT_ROOT,
            staging_dir,
            arguments.version,
            arguments.release_date,
            arguments.payload.resolve(),
        )

        output = arguments.output
        if output is None:
            output = (
                PROJECT_ROOT
                / "build"
                / "out"
                / default_output_name(arguments.version)
            )
        output = output.resolve()

        binarycreator = find_binarycreator(arguments.qtifw)
        run_binarycreator(binarycreator, staging_dir, output)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
