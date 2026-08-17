from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from bambu_ota_archive.audit import audit_repository


class AuditTests(unittest.TestCase):
    def test_empty_repository_audits_cleanly(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            self.assertEqual(
                audit_repository(Path(raw)),
                {"observations": 0, "verified_archives": 0, "git_reconstructions": 0},
            )


if __name__ == "__main__":
    unittest.main()
