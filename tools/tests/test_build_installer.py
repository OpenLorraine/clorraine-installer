"""Unit tests for :mod:`tools.build_installer`."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools import build_installer


def create_project(
    root: Path,
    config_version: str = "1.0.0",
    repository_url: str = "https://example.test/{platform}/",
) -> Path:
    """Create a minimal installer project for staging tests."""
    project = root / "project"
    meta = project / "packages" / build_installer.CORE_COMPONENT / "meta"
    meta.mkdir(parents=True)
    (project / "config").mkdir()
    (project / "config" / "config.xml").write_text(
        "<Installer>"
        f"<Version>{config_version}</Version>"
        "<RemoteRepositories><Repository>"
        f"<Url>{repository_url}</Url>"
        "</Repository></RemoteRepositories>"
        "</Installer>",
        encoding="utf-8",
    )
    (meta / "package.xml").write_text(
        "<Package><Version>0.0.0-dev</Version>"
        "<ReleaseDate>1970-01-01</ReleaseDate></Package>",
        encoding="utf-8",
    )
    return project


def create_payload(root: Path, system: str = "Linux") -> Path:
    """Create a payload directory with the required binaries."""
    payload = root / "payload"
    payload.mkdir()
    for name in build_installer.BINARY_NAMES:
        filename = build_installer.binary_filename(name, system)
        (payload / filename).write_text("binary", encoding="utf-8")
    return payload


def write_checksum_entry(directory: Path, name: str) -> str:
    """Create ``name`` in ``directory`` and return its SHA-256 digest."""
    content = f"payload for {name}".encode()
    (directory / name).write_bytes(content)
    return hashlib.sha256(content).hexdigest()


class PlatformNamingTest(unittest.TestCase):
    """Platform names become stable installer file names."""

    def test_platform_slug_covers_supported_systems(self) -> None:
        self.assertEqual(
            build_installer.platform_slug("Linux", "x86_64"), "linux-x86_64"
        )
        self.assertEqual(
            build_installer.platform_slug("Darwin", "arm64"), "macos-aarch64"
        )
        self.assertEqual(
            build_installer.platform_slug("Windows", "AMD64"), "windows-x86_64"
        )

    def test_platform_slug_rejects_unknown_values(self) -> None:
        with self.assertRaises(build_installer.BuildError):
            build_installer.platform_slug("Plan9", "x86_64")
        with self.assertRaises(build_installer.BuildError):
            build_installer.platform_slug("Linux", "riscv64")

    def test_binary_filename_adds_exe_only_on_windows(self) -> None:
        self.assertEqual(build_installer.binary_filename("clc", "Linux"), "clc")
        self.assertEqual(build_installer.binary_filename("clc", "Windows"), "clc.exe")

    def test_default_output_name_uses_installer_version(self) -> None:
        self.assertEqual(
            build_installer.default_output_name("1.0.0", "Linux", "x86_64"),
            "clorraine-installer-1.0.0-linux-x86_64.run",
        )
        self.assertEqual(
            build_installer.default_output_name("1.0.0", "Darwin", "arm64"),
            "clorraine-installer-1.0.0-macos-aarch64.app",
        )
        self.assertEqual(
            build_installer.default_output_name("1.0.0", "Windows", "AMD64"),
            "clorraine-installer-1.0.0-windows-x86_64.exe",
        )


class ChecksumTest(unittest.TestCase):
    """Payload integrity checks reject tampered or malformed manifests."""

    def test_missing_manifest_is_not_an_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(build_installer.verify_checksums(Path(directory)), 0)

    def test_matching_manifest_verifies_payload_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            digest = write_checksum_entry(payload, "clc")
            (payload / "SHA256SUMS").write_text(
                f"{digest}  clc\n# archive not in payload\n", encoding="utf-8"
            )
            self.assertEqual(build_installer.verify_checksums(payload), 1)

    def test_tampered_payload_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            digest = write_checksum_entry(payload, "clc")
            (payload / "clc").write_text("tampered", encoding="utf-8")
            (payload / "SHA256SUMS").write_text(f"{digest}  clc\n", encoding="utf-8")
            with self.assertRaises(build_installer.BuildError):
                build_installer.verify_checksums(payload)

    def test_malformed_manifest_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            (payload / "SHA256SUMS").write_text("not-a-digest\n", encoding="utf-8")
            with self.assertRaises(build_installer.BuildError):
                build_installer.verify_checksums(payload)


class PayloadTest(unittest.TestCase):
    """The payload must provide all three core executables."""

    def test_missing_binary_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            for name in ("clc", "clorraine"):
                (payload / name).write_text("", encoding="utf-8")
            with self.assertRaises(build_installer.BuildError):
                build_installer.verify_payload(payload, "Linux")

    def test_windows_payload_requires_exe_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            payload = Path(directory)
            for name in build_installer.BINARY_NAMES:
                (payload / f"{name}.exe").write_text("", encoding="utf-8")
            binaries = build_installer.verify_payload(payload, "Windows")
            self.assertEqual(
                [path.name for path in binaries],
                ["clc.exe", "clorraine.exe", "clorraine-lsp.exe"],
            )


class XmlTextTest(unittest.TestCase):
    """Metadata reads and writes must be unambiguous."""

    def test_single_element_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text("<Package><Version>0</Version></Package>", encoding="utf-8")
            build_installer.set_xml_text(path, ".//Version", "1.1.2")
            self.assertEqual(
                build_installer.read_xml_text(path, ".//Version"), "1.1.2"
            )

    def test_missing_element_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text("<Package></Package>", encoding="utf-8")
            with self.assertRaises(build_installer.BuildError):
                build_installer.set_xml_text(path, ".//Version", "1.1.2")

    def test_duplicate_element_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text(
                "<Package><Version>0</Version><Version>1</Version></Package>",
                encoding="utf-8",
            )
            with self.assertRaises(build_installer.BuildError):
                build_installer.set_xml_text(path, ".//Version", "1.1.2")

    def test_tag_names_inside_comments_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text(
                "<!-- replace <Version> in a staging copy -->\n"
                "<Package><Version>0</Version></Package>",
                encoding="utf-8",
            )
            build_installer.set_xml_text(path, ".//Version", "1.1.2")
            self.assertEqual(
                build_installer.read_xml_text(path, ".//Version"), "1.1.2"
            )


class RepositoryUrlTest(unittest.TestCase):
    """The repository location is configurable per build."""

    def test_platform_placeholder_is_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = create_project(
                Path(directory), repository_url="https://cdn.test/{platform}/"
            )
            url = build_installer.resolve_repository_url(
                project / "config" / "config.xml", "linux-x86_64"
            )
            self.assertEqual(url, "https://cdn.test/linux-x86_64/")

    def test_override_wins_over_configuration(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = create_project(Path(directory))
            url = build_installer.resolve_repository_url(
                project / "config" / "config.xml",
                "linux-x86_64",
                "http://127.0.0.1:8000/",
            )
            self.assertEqual(url, "http://127.0.0.1:8000/")

    def test_url_without_placeholder_is_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project = create_project(
                Path(directory), repository_url="https://cdn.test/stable/"
            )
            url = build_installer.resolve_repository_url(
                project / "config" / "config.xml", "linux-x86_64"
            )
            self.assertEqual(url, "https://cdn.test/stable/")


class StagingTest(unittest.TestCase):
    """Staging copies the payload and stamps disposable metadata."""

    def test_stage_copies_payload_and_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = create_project(root)
            payload = create_payload(root)
            (payload / "NOTICE").write_text("notice", encoding="utf-8")

            staging = build_installer.stage_project(
                project,
                root / "staging",
                "1.1.2",
                "2026-11-15",
                payload,
                "https://cdn.test/linux-x86_64/",
                system="Linux",
            )

            core = staging / "packages" / build_installer.CORE_COMPONENT
            self.assertTrue((core / "data" / "bin" / "clc").is_file())
            self.assertTrue(
                (core / "data" / "share" / "doc" / "clorraine" / "NOTICE").is_file()
            )
            package_xml = core / "meta" / "package.xml"
            self.assertEqual(
                build_installer.read_xml_text(package_xml, ".//Version"), "1.1.2"
            )
            self.assertEqual(
                build_installer.read_xml_text(package_xml, ".//ReleaseDate"),
                "2026-11-15",
            )
            config_xml = staging / "config" / "config.xml"
            self.assertEqual(
                build_installer.read_xml_text(config_xml, ".//Version"), "1.0.0"
            )
            self.assertEqual(
                build_installer.read_xml_text(
                    config_xml, "./RemoteRepositories/Repository/Url"
                ),
                "https://cdn.test/linux-x86_64/",
            )

    def test_stage_leaves_source_metadata_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = create_project(root)
            payload = create_payload(root)

            build_installer.stage_project(
                project,
                root / "staging",
                "1.1.2",
                "2026-11-15",
                payload,
                "https://cdn.test/linux-x86_64/",
                system="Linux",
            )

            config_xml = project / "config" / "config.xml"
            self.assertEqual(
                build_installer.read_xml_text(config_xml, ".//Version"), "1.0.0"
            )
            self.assertEqual(
                build_installer.read_xml_text(
                    config_xml, "./RemoteRepositories/Repository/Url"
                ),
                "https://example.test/{platform}/",
            )


if __name__ == "__main__":
    unittest.main()
