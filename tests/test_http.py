from __future__ import annotations

import unittest
import urllib.request

from bambu_ota_archive.http import _ProfileRedirectHandler, validate_profile_cdn_url


class ProfileUrlTests(unittest.TestCase):
    def test_accepts_exact_settings_and_printer_paths(self) -> None:
        validate_profile_cdn_url(
            "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.04.00.10/ebf18539c1/02.04.00.10.zip",
            expected_version="02.04.00.10",
            expected_kind="settings",
        )
        validate_profile_cdn_url(
            "https://public-cdn.bblmw.com/upgrade/studio/printer/BBL/02.04.00.10/hash/02.04.00.10.zip",
            expected_version="02.04.00.10",
            expected_kind="printer",
        )

    def test_rejects_installer_plugin_firmware_and_non_cdn_urls(self) -> None:
        rejected = [
            "https://public-cdn.bblmw.com/upgrade/studio/software/02.08/app.exe",
            "https://public-cdn.bblmw.com/upgrade/studio/plugins/02.08/plugin.zip",
            "https://public-cdn.bblmw.com/upgrade/firmware/02.08/firmware.zip",
            "https://example.com/upgrade/studio/settings/BBL/02.04.00.10/hash/02.04.00.10.zip",
        ]
        for url in rejected:
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_profile_cdn_url(url)

    def test_rejects_version_kind_query_and_path_mismatches(self) -> None:
        base = "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.04.00.10/hash/02.04.00.10.zip"
        with self.assertRaises(ValueError):
            validate_profile_cdn_url(base, expected_version="02.04.00.09")
        with self.assertRaises(ValueError):
            validate_profile_cdn_url(base, expected_kind="printer")
        with self.assertRaises(ValueError):
            validate_profile_cdn_url(base + "?token=not-allowed")

    def test_redirect_handler_rejects_non_profile_destination_before_following(self) -> None:
        source = "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/02.04.00.10/hash/02.04.00.10.zip"
        handler = _ProfileRedirectHandler("02.04.00.10", "settings")
        request = urllib.request.Request(source)
        with self.assertRaises(ValueError):
            handler.redirect_request(
                request,
                None,
                302,
                "Found",
                {},
                "https://public-cdn.bblmw.com/upgrade/studio/software/app.exe",
            )


if __name__ == "__main__":
    unittest.main()
