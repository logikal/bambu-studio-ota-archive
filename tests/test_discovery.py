from __future__ import annotations

import json
import unittest
from urllib.parse import parse_qs, urlsplit

from bambu_ota_archive.discovery import (
    baseline_for_family,
    build_resource_url,
    discover_families_from_tags,
    parse_resources,
)


class DiscoveryTests(unittest.TestCase):
    def test_discovers_uppercase_lowercase_and_later_major_tags(self) -> None:
        tags = ["v02.00.01.50", "V02.00.03.54", "v02.08.00.50", "V03.01.00.01", "junk", "v1.9.0"]
        self.assertEqual(discover_families_from_tags(tags), ["02.00", "02.08", "03.01"])

    def test_baseline_and_combined_query_are_exact(self) -> None:
        self.assertEqual(baseline_for_family("02.04"), "02.04.00.00")
        query = parse_qs(urlsplit(build_resource_url("02.04")).query)
        self.assertEqual(
            query,
            {"slicer/settings/bbl": ["02.04.00.00"], "slicer/printer/bbl": ["02.04.00.00"]},
        )

    def test_latest_only_response_is_accepted_for_family_baseline(self) -> None:
        payload = {
            "software": {"url": "https://example.invalid/installer.exe"},
            "resources": [
                {
                    "type": "slicer/settings/bbl",
                    "version": "02.04.00.10",
                    "url": "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.04.00.10/hash/02.04.00.10.zip",
                    "description": "latest only",
                    "force_update": False,
                },
                {"type": "slicer/plugins/cloud", "version": "99", "url": "https://example.invalid/plugin.zip"},
            ],
        }
        resources = parse_resources(json.dumps(payload), "02.04")
        self.assertEqual([resource.version for resource in resources], ["02.04.00.10"])
        self.assertNotIn("installer", resources[0].url)

    def test_empty_resource_response(self) -> None:
        self.assertEqual(parse_resources('{"resources": [], "software": {"url": "ignored"}}', "02.07"), [])

    def test_rejects_cross_family_resource(self) -> None:
        payload = json.dumps(
            {
                "resources": [
                    {
                        "type": "slicer/settings/bbl",
                        "version": "02.05.00.01",
                        "url": "https://public-cdn.bblmw.com/x.zip",
                    }
                ]
            }
        )
        with self.assertRaisesRegex(ValueError, "does not match"):
            parse_resources(payload, "02.04")


if __name__ == "__main__":
    unittest.main()

