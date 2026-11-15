"""Unit tests for :mod:`tools.build_installer`."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from tools import build_installer


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

    def test_default_output_name_uses_platform_suffix(self) -> None:
        self.assertEqual(
            build_installer.default_output_name("1.1.2", "Linux", "x86_64"),
            "clorraine-1.1.2-linux-x86_64.run",
        )
        self.assertEqual(
            build_installer.default_output_name("1.1.2", "Darwin", "arm64"),
            "clorraine-1.1.2-macos-aarch64.app",
        )
        self.assertEqual(
            build_installer.default_output_name("1.1.2", "Windows", "AMD64"),
            "clorraine-1.1.2-windows-x86_64.exe",
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
            self.assertEqual([path.name for path in binaries], [
                "clc.exe", "clorraine.exe", "clorraine-lsp.exe"
            ])


class XmlStampingTest(unittest.TestCase):
    """Version stamping must be unambiguous."""

    def test_single_element_is_replaced(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text("<Package><Version>0</Version></Package>", encoding="utf-8")
            build_installer.set_xml_text(path, "Version", "1.1.2")
            self.assertIn("<Version>1.1.2</Version>", path.read_text(encoding="utf-8"))

    def test_missing_element_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text("<Package></Package>", encoding="utf-8")
            with self.assertRaises(build_installer.BuildError):
                build_installer.set_xml_text(path, "Version", "1.1.2")

    def test_duplicate_element_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text(
                "<Package><Version>0</Version><Version>1</Version></Package>",
                encoding="utf-8",
            )
            with self.assertRaises(build_installer.BuildError):
                build_installer.set_xml_text(path, "Version", "1.1.2")

    def test_tag_names_inside_comments_are_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata.xml"
            path.write_text(
                "<!-- replace <Version> in a staging copy -->\n"
                "<Package><Version>0</Version></Package>",
                encoding="utf-8",
            )
            build_installer.set_xml_text(path, "Version", "1.1.2")
            self.assertIn("<Version>1.1.2</Version>", path.read_text(encoding="utf-8"))


class StagingTest(unittest.TestCase):
    """Staging copies the payload and stamps a disposable metadata tree."""

    def test_stage_copies_payload_and_documents(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            meta = project / "packages" / build_installer.CORE_COMPONENT / "meta"
            meta.mkdir(parents=True)
            (project / "config").mkdir()
            (project / "config" / "config.xml").write_text(
                "<Installer><Version>0.0.0-dev</Version></Installer>", encoding="utf-8"
            )
            (meta / "package.xml").write_text(
                "<Package><Version>0.0.0-dev</Version>"
                "<ReleaseDate>1970-01-01</ReleaseDate></Package>",
                encoding="utf-8",
            )

            payload = root / "payload"
            payload.mkdir()
            for name in build_installer.BINARY_NAMES:
                (payload / name).write_text("binary", encoding="utf-8")
            (payload / "NOTICE").write_text("notice", encoding="utf-8")

            staging = build_installer.stage_project(
                project,
                root / "staging",
                "1.1.2",
                "2026-11-15",
                payload,
                system="Linux",
            )

            core = staging / "packages" / build_installer.CORE_COMPONENT
            self.assertTrue((core / "data" / "bin" / "clc").is_file())
            self.assertTrue(
                (core / "data" / "share" / "doc" / "clorraine" / "NOTICE").is_file()
            )
            config_xml = (staging / "config" / "config.xml").read_text(encoding="utf-8")
            self.assertIn("<Version>1.1.2</Version>", config_xml)
            package_xml = (core / "meta" / "package.xml").read_text(encoding="utf-8")
            self.assertIn("<Version>1.1.2</Version>", package_xml)
            self.assertIn("<ReleaseDate>2026-11-15</ReleaseDate>", package_xml)

    def test_stage_leaves_source_metadata_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            project = root / "project"
            meta = project / "packages" / build_installer.CORE_COMPONENT / "meta"
            meta.mkdir(parents=True)
            (project / "config").mkdir()
            (project / "config" / "config.xml").write_text(
                "<Installer><Version>0.0.0-dev</Version></Installer>", encoding="utf-8"
            )
            (meta / "package.xml").write_text(
                "<Package><Version>0.0.0-dev</Version>"
                "<ReleaseDate>1970-01-01</ReleaseDate></Package>",
                encoding="utf-8",
            )
            payload = root / "payload"
            payload.mkdir()
            for name in build_installer.BINARY_NAMES:
                (payload / name).write_text("binary", encoding="utf-8")

            build_installer.stage_project(
                project,
                root / "staging",
                "1.1.2",
                "2026-11-15",
                payload,
                system="Linux",
            )

            self.assertIn(
                "<Version>0.0.0-dev</Version>",
                (project / "config" / "config.xml").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
