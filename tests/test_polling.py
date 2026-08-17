from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bambu_ota_archive.capture import Archiver, compare_seed_inventory
from bambu_ota_archive.catalog import read_observations
from bambu_ota_archive.http import Download
from bambu_ota_archive.models import Resource


def profile_zip(path: Path, version: str, marker: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("BBL.json", json.dumps({"version": version}))
        zf.writestr("profile.json", marker)


class FakeClient:
    def __init__(self, archives: dict[str, Path]):
        self.archives = archives

    def download(self, url: str, destination: Path) -> Download:
        source = self.archives[url]
        target = destination / "archive.zip"
        shutil.copyfile(source, target)
        data = target.read_bytes()
        return Download(
            target,
            hashlib.sha256(data).hexdigest(),
            hashlib.md5(data, usedforsecurity=False).hexdigest(),
            len(data),
            {"last-modified": "Wed, 01 Jan 2025 00:00:00 GMT", "etag": '"test"'},
        )


def resource(family: str, revision: str, url: str, description: str = "profiles") -> Resource:
    return Resource("slicer/settings/bbl", f"{family}.00.{revision}", url, description, False)


class PollingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.archive_a = self.root / "a.zip"
        self.archive_b = self.root / "b.zip"
        self.archive_new = self.root / "new.zip"
        profile_zip(self.archive_a, "02.00.00.01", "first")
        profile_zip(self.archive_b, "02.00.00.01", "repack")
        profile_zip(self.archive_new, "02.01.00.01", "new-family")
        self.url_a = "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.00.00.01/a/02.00.00.01.zip"
        self.url_b = "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.00.00.01/b/02.00.00.01.zip"
        self.url_new = "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.01.00.01/c/02.01.00.01.zip"
        self.client = FakeClient({self.url_a: self.archive_a, self.url_b: self.archive_b, self.url_new: self.archive_new})

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_poll(self, families: list[str], mapping: dict[str, list[Resource]]) -> tuple[list, list[str]]:
        queried: list[str] = []

        def query(_client: object, family: str):
            queried.append(family)
            return mapping.get(family, []), f"https://api.bambulab.com/global?family={family}"

        with patch("bambu_ota_archive.capture.discover_official_families", return_value=families), patch(
            "bambu_ota_archive.capture.query_family", side_effect=query
        ):
            results = Archiver(self.root, self.client, pause=0).poll()
        return results, queried

    def test_new_pack_then_idempotent_poll(self) -> None:
        offered = resource("02.00", "01", self.url_a)
        first, _ = self.run_poll(["02.00"], {"02.00": [offered]})
        second, _ = self.run_poll(["02.00"], {"02.00": [offered]})
        self.assertEqual([result.changed for result in first], [True])
        self.assertEqual([result.changed for result in second], [False])
        self.assertEqual(len(read_observations(self.root / "catalog/observations.jsonl")), 1)

    def test_same_version_url_and_bytes_change_is_repack(self) -> None:
        self.run_poll(["02.00"], {"02.00": [resource("02.00", "01", self.url_a)]})
        self.run_poll(["02.00"], {"02.00": [resource("02.00", "01", self.url_b)]})
        records = read_observations(self.root / "catalog/observations.jsonl")
        self.assertEqual(len(records), 2)
        self.assertFalse(records[0]["same_version_repack"])
        self.assertTrue(records[1]["same_version_repack"])
        self.assertNotEqual(records[0]["archive_sha256"], records[1]["archive_sha256"])

    def test_description_only_change_redownloads_without_duplicate_catalog_identity(self) -> None:
        self.run_poll(["02.00"], {"02.00": [resource("02.00", "01", self.url_a, "first")]})
        results, _ = self.run_poll(
            ["02.00"], {"02.00": [resource("02.00", "01", self.url_a, "description changed")]}
        )
        self.assertTrue(results[0].changed)
        self.assertEqual(len(read_observations(self.root / "catalog/observations.jsonl")), 1)
        metadata = json.loads((self.root / "timeline/settings.json").read_text())
        self.assertEqual(metadata["description"], "description changed")

    def test_successive_packs_replace_one_diffable_profile_tree(self) -> None:
        self.run_poll(["02.00"], {"02.00": [resource("02.00", "01", self.url_a)]})
        self.run_poll(["02.00", "02.01"], {"02.01": [resource("02.01", "01", self.url_new)]})
        self.assertEqual((self.root / "profiles/settings/profile.json").read_text(), "new-family")
        sources = sorted((self.root / "sources/ota").glob("*/*/*/archive.zip"))
        self.assertEqual(len(sources), 2)

    def test_new_family_is_captured_and_old_family_continues_polling(self) -> None:
        self.run_poll(["02.00"], {"02.00": [resource("02.00", "01", self.url_a)]})
        results, queried = self.run_poll(
            ["02.00", "02.01"],
            {
                "02.00": [resource("02.00", "01", self.url_a)],
                "02.01": [resource("02.01", "01", self.url_new)],
            },
        )
        self.assertEqual(queried, ["02.00", "02.01"])
        self.assertEqual([(result.family, result.changed) for result in results], [("02.00", False), ("02.01", True)])

    def test_empty_family_is_polled_without_catalog_record(self) -> None:
        results, queried = self.run_poll(["02.00", "02.01"], {"02.00": [], "02.01": []})
        self.assertEqual(results, [])
        self.assertEqual(queried, ["02.00", "02.01"])
        inventory = json.loads((self.root / "catalog/current-inventory.json").read_text())
        self.assertEqual(inventory["families"]["02.00"]["resources"], [])

    def test_historical_exact_archive_import(self) -> None:
        archiver = Archiver(self.root, self.client)
        result = archiver.capture_resource(
            "02.00",
            resource("02.00", "01", self.url_a),
            provenance="observed-log",
            evidence="https://github.com/example/issue/1",
            observed_at="2025-03-01T00:00:00Z",
        )
        self.assertTrue(result.changed)
        record = read_observations(self.root / "catalog/observations.jsonl")[0]
        self.assertEqual(record["provenance"], "observed-log")
        self.assertTrue(record["directly_verified"])

    def test_seed_inventory_verification(self) -> None:
        expected = {"families": {"02.00": {"version": "02.00.00.01", "url": self.url_a}, "02.01": None}}
        inventory = {
            "generated_at": "2026-08-17T00:00:00Z",
            "families": {
                "02.00": {"resources": [resource("02.00", "01", self.url_a).to_dict()]},
                "02.01": {"resources": []},
            },
        }
        report = compare_seed_inventory(expected, inventory)
        self.assertTrue(report["all_match"])


if __name__ == "__main__":
    unittest.main()
