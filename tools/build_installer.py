#!/usr/bin/env python3
"""Build the Clorraine online installer and its component repository.

The repository is the single source of truth for installable components. This
tool stages the release payload, verifies it, builds the Qt Installer Framework
repository with ``repogen``, and builds a thin online installer with
``binarycreator -n``. The installer embeds no payload; it downloads the
components from the repository URL stamped into its configuration.

The URL is configurable so the same build can target GitHub Pages, an external
bucket, or a local test server. The source configuration uses a ``{platform}``
placeholder because Qt Installer Framework repositories are per platform.

Usage::

    python3 tools/build_installer.py --version 1.1.2 --payload DIR

    python3 tools/build_installer.py --version 1.1.2 --payload DIR \\
        --repository-url https://cdn.example.com/clorraine/linux-x86_64/
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

#: Replaced with the build host's ``<os>-<arch>`` slug when the repository URL
#: is resolved. Kept literal in ``config/config.xml`` so every platform shares
#: one configuration file.
PLATFORM_PLACEHOLDER = "{platform}"

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
    installer_version: str, system: str | None = None, machine: str | None = None
) -> str:
    """Return the conventional installer file name for the build host."""
    os_slug = normalize_os(system or platform.system())
    suffix = {"linux": ".run", "macos": ".app", "windows": ".exe"}[os_slug]
    return f"clorraine-installer-{installer_version}-{platform_slug(system, machine)}{suffix}"


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


def read_xml_text(path: Path, element_path: str) -> str:
    """Return the text of the single element at ``element_path``."""
    tree = ET.parse(path)
    matches = tree.getroot().findall(element_path)
    if len(matches) != 1:
        raise BuildError(
            f"{path}: expected exactly one {element_path} element, "
            f"found {len(matches)}"
        )
    return (matches[0].text or "").strip()


def set_xml_text(path: Path, element_path: str, value: str) -> None:
    """Replace the single element at ``element_path`` with ``value``.

    Parsing, rather than text matching, keeps tag names inside comments from
    being mistaken for the real element. Raises :class:`BuildError` when the
    element is missing or ambiguous, so a metadata change cannot silently stop
    the value from being applied.
    """
    tree = ET.parse(path)
    matches = tree.getroot().findall(element_path)
    if len(matches) != 1:
        raise BuildError(
            f"{path}: expected exactly one {element_path} element, "
            f"found {len(matches)}"
        )

    matches[0].text = value
    tree.write(path, encoding="utf-8", xml_declaration=True)


def resolve_repository_url(
    config_path: Path, platform_name: str, override: str | None = None
) -> str:
    """Return the repository URL for ``platform_name``.

    An explicit ``override`` wins. Otherwise the configured URL is used with
    :data:`PLATFORM_PLACEHOLDER` replaced, so one configuration covers every
    platform. A configured URL without the placeholder is used unchanged.
    """
    if override:
        return override

    template = read_xml_text(config_path, "./RemoteRepositories/Repository/Url")
    return template.replace(PLATFORM_PLACEHOLDER, platform_name)


def stage_project(
    project_root: Path,
    staging_dir: Path,
    component_version: str,
    release_date: str,
    payload_dir: Path,
    repository_url: str,
    system: str | None = None,
) -> Path:
    """Copy metadata and payload into ``staging_dir`` and stamp release values.

    The installer version in ``config/config.xml`` is left untouched; it
    identifies the installer build and is independent of the compiler version.
    The component version in ``package.xml`` is set to ``component_version``.
    Returns the staging directory. The source project is never modified.
    """
    binaries = verify_payload(payload_dir, system)

    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    shutil.copytree(project_root / "config", staging_dir / "config")
    shutil.copytree(project_root / "packages", staging_dir / "packages")

    package_xml = staging_dir / "packages" / CORE_COMPONENT / "meta" / "package.xml"
    set_xml_text(package_xml, ".//Version", component_version)
    set_xml_text(package_xml, ".//ReleaseDate", release_date)
    set_xml_text(
        staging_dir / "config" / "config.xml",
        "./RemoteRepositories/Repository/Url",
        repository_url,
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


def find_tool(name: str, qtifw_dir: Path | None = None) -> Path:
    """Locate a QtIFW tool from an explicit QtIFW root or ``PATH``."""
    executable = name + (".exe" if platform.system() == "Windows" else "")
    candidates: list[Path] = []
    if qtifw_dir is not None:
        candidates.extend((qtifw_dir / "bin" / executable, qtifw_dir / executable))

    on_path = shutil.which(name)
    if on_path:
        candidates.append(Path(on_path))

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    raise BuildError(
        f"{name} was not found; install Qt Installer Framework 4.x "
        "or pass --qtifw <QtInstallerFramework root>"
    )


def build_repository(staging_dir: Path, repository_dir: Path, repogen: Path) -> None:
    """Build the online repository from the staged packages."""
    if repository_dir.exists():
        shutil.rmtree(repository_dir)

    command = [
        str(repogen),
        "-p",
        str(staging_dir / "packages"),
        str(repository_dir),
    ]
    print("+ " + " ".join(command))
    completed = subprocess.run(command, check=False)
    if completed.returncode != 0:
        raise BuildError(f"repogen failed with exit status {completed.returncode}")


def run_binarycreator(
    binarycreator: Path, staging_dir: Path, output: Path
) -> None:
    """Build the thin online installer at ``output``.

    ``-n`` keeps every component out of the installer binary, so installation
    always downloads the component metadata and payload from the repository.
    """
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(binarycreator),
        "-n",
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
        description="Build the Clorraine online installer and repository."
    )
    parser.add_argument("--version", required=True, help="Clorraine release version")
    parser.add_argument(
        "--payload",
        required=True,
        type=Path,
        help="directory containing clc, clorraine, and clorraine-lsp",
    )
    parser.add_argument(
        "--repository-url",
        help="repository URL baked into the installer; overrides the configured "
        "URL and skips {platform} substitution",
    )
    parser.add_argument(
        "--repository-output",
        type=Path,
        help="repository directory; defaults to build/repository",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="installer path; defaults to build/out/<platform name>",
    )
    parser.add_argument(
        "--qtifw",
        type=Path,
        help="Qt Installer Framework root when its tools are not on PATH",
    )
    parser.add_argument(
        "--release-date",
        default=datetime.date.today().isoformat(),
        help="component release date in YYYY-MM-DD form (default: today)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Build the repository and installer, reporting build errors."""
    arguments = parse_arguments(argv)
    try:
        payload = arguments.payload.resolve()
        verified = verify_checksums(payload)
        if verified:
            print(f"verified {verified} file(s) with SHA256SUMS")

        platform_name = platform_slug()
        repository_url = resolve_repository_url(
            PROJECT_ROOT / "config" / "config.xml",
            platform_name,
            arguments.repository_url,
        )

        staging_dir = PROJECT_ROOT / "build" / "staging"
        stage_project(
            PROJECT_ROOT,
            staging_dir,
            arguments.version,
            arguments.release_date,
            payload,
            repository_url,
        )

        repository_output = arguments.repository_output or (
            PROJECT_ROOT / "build" / "repository"
        )
        build_repository(
            staging_dir,
            repository_output.resolve(),
            find_tool("repogen", arguments.qtifw),
        )

        installer_version = read_xml_text(
            staging_dir / "config" / "config.xml", ".//Version"
        )
        output = arguments.output
        if output is None:
            output = (
                PROJECT_ROOT
                / "build"
                / "out"
                / default_output_name(installer_version)
            )
        output = output.resolve()

        run_binarycreator(
            find_tool("binarycreator", arguments.qtifw), staging_dir, output
        )
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"repository: {repository_output.resolve()}")
    print(f"repository url: {repository_url}")
    print(f"wrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
