from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from bambu_ota_archive.reconstruction import import_git_reconstruction


class ReconstructionTests(unittest.TestCase):
    def test_git_state_is_separate_and_explicitly_unverified(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            base = Path(raw)
            source = base / "source"
            archive = base / "archive"
            (source / "resources/profiles/BBL/machine").mkdir(parents=True)
            (source / "resources/profiles/BBL.json").write_text('{"version":"02.00.00.42"}\n')
            (source / "resources/profiles/BBL/machine/test.json").write_text('{"x":1}\n')
            subprocess.run(["git", "init", "-q"], cwd=source, check=True)
            subprocess.run(["git", "add", "."], cwd=source, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=Test",
                    "-c",
                    "user.email=test@example.invalid",
                    "-c",
                    "commit.gpgsign=false",
                    "commit",
                    "-q",
                    "--no-gpg-sign",
                    "-m",
                    "profiles",
                ],
                cwd=source,
                check=True,
            )
            destination = import_git_reconstruction(
                archive, source, "HEAD", "https://github.com/bambulab/BambuStudio/commit/example"
            )
            self.assertTrue(str(destination.relative_to(archive)).startswith("sources/git/"))
            self.assertTrue((archive / "profiles/settings/BBL/machine/test.json").is_file())
            self.assertFalse((archive / "sources/ota").exists())
            metadata = json.loads((destination / "metadata.json").read_text())
            self.assertEqual(metadata["provenance"], "reconstructed-git")
            self.assertFalse(metadata["directly_verified"])
            self.assertIsNone(metadata["cdn_url"])
            self.assertTrue(metadata["source_commit"])
            self.assertTrue(metadata["source_tree"])
            self.assertTrue(metadata["source_bbl_json_blob"])
            self.assertEqual(metadata["source_revision"], "HEAD")


if __name__ == "__main__":
    unittest.main()
