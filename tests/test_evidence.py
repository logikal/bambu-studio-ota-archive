from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from bambu_ota_archive.capture import Archiver
from bambu_ota_archive.catalog import read_observations
from bambu_ota_archive.evidence import extract_resources_from_log, redact_sensitive


class EvidenceTests(unittest.TestCase):
    def test_extracts_only_allowed_metadata_and_drops_unrelated_sensitive_log_data(self) -> None:
        payload = {
            "resources": [
                {
                    "type": "slicer/settings/bbl",
                    "version": "02.01.00.01",
                    "url": "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.01.00.01/hash/02.01.00.01.zip",
                    "description": "profiles",
                    "force_update": False,
                    "token": "secret",
                },
                {"type": "slicer/plugins/cloud", "version": "x", "url": "https://example.invalid/plugin.zip"},
            ],
            "software": {"url": "https://example.invalid/installer.exe"},
            "device_id": "private-device",
        }
        log = (
            "username=person ip=192.0.2.5 cookie=secret\n"
            "[BBL Updater]: request_resources, body=" + json.dumps(payload) + "\n"
        )
        extracted = extract_resources_from_log(log)
        self.assertEqual(len(extracted), 1)
        encoded = json.dumps(extracted)
        self.assertNotIn("private-device", encoded)
        self.assertNotIn("installer", encoded)
        self.assertNotIn("plugin", encoded)
        self.assertNotIn("person", encoded)
        self.assertNotIn("192.0.2.5", encoded)
        self.assertNotIn("secret", encoded)

    def test_redacts_nested_sensitive_fields(self) -> None:
        self.assertEqual(redact_sensitive({"token": "x", "nested": {"user_id": 1}}), {"token": "[REDACTED]", "nested": {"user_id": "[REDACTED]"}})

    def test_metadata_only_historical_record(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            archiver = Archiver(root, client=object())
            added = archiver.import_metadata_only(
                {
                    "compatibility_family": "02.00",
                    "resource_type": "slicer/settings/bbl",
                    "pack_version": "02.00.00.01",
                    "cdn_url": "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.00.00.01/hash/02.00.00.01.zip",
                    "evidence": "https://example.test/historical-log",
                    "first_observed_at": "2025-03-01T00:00:00Z",
                }
            )
            self.assertTrue(added)
            record = read_observations(root / "catalog/observations.jsonl")[0]
            self.assertEqual(record["provenance"], "metadata-only")
            self.assertFalse(record["directly_verified"])
            self.assertIsNone(record["archive_sha256"])


if __name__ == "__main__":
    unittest.main()

