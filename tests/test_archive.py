from __future__ import annotations

import json
import stat
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path

from bambu_ota_archive.archive import UnsafeArchive, _validated_name, extract_zip_safely, validate_zip


def make_zip(path: Path, version: str = "02.04.00.10", extras: list[tuple[zipfile.ZipInfo | str, bytes]] | None = None) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BBL.json", json.dumps({"version": version}).encode())
        zf.writestr("machine/profile.json", b'{"untouched": true}\n')
        for name, data in extras or []:
            zf.writestr(name, data)


class ArchiveSafetyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def assert_unsafe(self, extras: list[tuple[zipfile.ZipInfo | str, bytes]], pattern: str) -> None:
        archive = self.root / "bad.zip"
        make_zip(archive, extras=extras)
        with self.assertRaisesRegex(UnsafeArchive, pattern):
            validate_zip(archive, "02.04.00.10")

    def test_valid_archive_preserves_bytes_and_paths(self) -> None:
        archive = self.root / "good.zip"
        make_zip(archive)
        destination = self.root / "contents"
        result = extract_zip_safely(archive, destination, "02.04.00.10")
        self.assertEqual(result.bbl_version, "02.04.00.10")
        self.assertEqual((destination / "machine/profile.json").read_bytes(), b'{"untouched": true}\n')

    def test_absolute_path(self) -> None:
        self.assert_unsafe([("/absolute", b"x")], "absolute")

    def test_traversal(self) -> None:
        self.assert_unsafe([("../escape", b"x")], "traversal")

    def test_backslash_path(self) -> None:
        self.assert_unsafe([("..\\escape", b"x")], "backslash")

    def test_nul_path(self) -> None:
        with self.assertRaisesRegex(UnsafeArchive, "NUL"):
            _validated_name("bad\x00name")

    def test_symlink(self) -> None:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        self.assert_unsafe([(info, b"target")], "symbolic")

    def test_hard_link_like_non_regular_entry(self) -> None:
        info = zipfile.ZipInfo("special")
        info.create_system = 3
        info.external_attr = (stat.S_IFIFO | 0o644) << 16
        self.assert_unsafe([(info, b"x")], "non-regular")

    def test_duplicate_path(self) -> None:
        archive = self.root / "duplicate.zip"
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            with zipfile.ZipFile(archive, "w") as zf:
                zf.writestr("BBL.json", json.dumps({"version": "02.04.00.10"}))
                zf.writestr("same", b"one")
                zf.writestr("same", b"two")
        with self.assertRaisesRegex(UnsafeArchive, "duplicate"):
            validate_zip(archive, "02.04.00.10")

    def test_case_collision(self) -> None:
        self.assert_unsafe([("Thing.json", b"1"), ("thing.json", b"2")], "case-colliding")

    def test_excessive_file_count(self) -> None:
        archive = self.root / "count.zip"
        make_zip(archive)
        with self.assertRaisesRegex(UnsafeArchive, "file count"):
            validate_zip(archive, "02.04.00.10", max_files=1)

    def test_excessive_expanded_size(self) -> None:
        archive = self.root / "size.zip"
        make_zip(archive)
        with self.assertRaisesRegex(UnsafeArchive, "expanded size"):
            validate_zip(archive, "02.04.00.10", max_expanded_bytes=1)

    def test_suspicious_compression_ratio(self) -> None:
        archive = self.root / "ratio.zip"
        make_zip(archive, extras=[("zeros", b"\x00" * 50_000)])
        with self.assertRaisesRegex(UnsafeArchive, "compression ratio"):
            validate_zip(archive, "02.04.00.10", max_compression_ratio=5)

    def test_crc_failure(self) -> None:
        archive = self.root / "crc.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_STORED) as zf:
            zf.writestr("BBL.json", b'{"version":"02.04.00.10"}')
            zf.writestr("payload", b"UNIQUE_PAYLOAD")
        data = archive.read_bytes().replace(b"UNIQUE_PAYLOAD", b"BROKEN_PAYLOAD", 1)
        archive.write_bytes(data)
        with self.assertRaisesRegex(UnsafeArchive, "CRC"):
            validate_zip(archive, "02.04.00.10")

    def test_truncated_archive(self) -> None:
        archive = self.root / "truncated.zip"
        make_zip(archive)
        archive.write_bytes(archive.read_bytes()[:-20])
        with self.assertRaisesRegex(UnsafeArchive, "truncated"):
            validate_zip(archive, "02.04.00.10")

    def test_bbl_version_mismatch(self) -> None:
        archive = self.root / "version.zip"
        make_zip(archive, version="02.04.00.09")
        with self.assertRaisesRegex(UnsafeArchive, "does not match"):
            validate_zip(archive, "02.04.00.10")


if __name__ == "__main__":
    unittest.main()

