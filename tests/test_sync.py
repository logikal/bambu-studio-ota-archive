from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from bambu_ota_archive.http import Download
from bambu_ota_archive.models import Resource
from bambu_ota_archive.reconstruction import discover_git_releases
from bambu_ota_archive.sync import sync_timeline


def commit_profiles(source: Path, tag: str, version: str, marker: str, timestamp: str) -> str:
    profiles = source / "resources/profiles"
    (profiles / "BBL/machine").mkdir(parents=True, exist_ok=True)
    (profiles / "BBL.json").write_text(json.dumps({"version": version}) + "\n")
    (profiles / "BBL/machine/test.json").write_text(json.dumps({"marker": marker}) + "\n")
    subprocess.run(["git", "add", "."], cwd=source, check=True)
    env = {**os.environ, "GIT_AUTHOR_DATE": timestamp, "GIT_COMMITTER_DATE": timestamp}
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
            tag,
        ],
        cwd=source,
        env=env,
        check=True,
    )
    subprocess.run(["git", "tag", tag], cwd=source, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=source,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.strip()


def profile_zip(path: Path, version: str, marker: str) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BBL.json", json.dumps({"version": version}))
        archive.writestr("BBL/machine/test.json", json.dumps({"marker": marker}))


class SyncClient:
    def __init__(self, archive: Path, last_modified: str):
        self.archive = archive
        self.last_modified = last_modified
        self.downloads = 0

    def head_profile(self, _url: str) -> tuple[int, dict[str, str]]:
        return 200, {"last-modified": self.last_modified}

    def download(self, _url: str, destination: Path) -> Download:
        self.downloads += 1
        target = destination / "archive.zip"
        shutil.copyfile(self.archive, target)
        data = target.read_bytes()
        return Download(
            target,
            hashlib.sha256(data).hexdigest(),
            hashlib.md5(data, usedforsecurity=False).hexdigest(),
            len(data),
            {"last-modified": self.last_modified},
        )


class TimelineSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.archive = self.base / "archive"
        self.source.mkdir()
        self.archive.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.source, check=True)
        self.old_commit = commit_profiles(
            self.source,
            "v02.00.00.01",
            "02.00.00.01",
            "release-old",
            "2026-01-01T00:00:00Z",
        )
        self.new_commit = commit_profiles(
            self.source,
            "v02.00.01.00",
            "02.00.00.03",
            "release-new",
            "2026-01-03T00:00:00Z",
        )
        old = discover_git_releases(self.source)[0]
        (self.archive / "state").mkdir()
        (self.archive / "state/studio-releases.json").write_text(
            json.dumps(
                {
                    "baseline_as_of": "2026-01-01T01:00:00Z",
                    "source": "https://github.com/bambulab/BambuStudio",
                    "tags": {
                        old.revision: {
                            "source_commit": old.commit,
                            "status": "baseline-before-automation",
                        }
                    },
                }
            )
            + "\n"
        )
        self.ota_archive = self.base / "ota.zip"
        profile_zip(self.ota_archive, "02.00.00.02", "ota-middle")
        self.url = (
            "https://public-cdn.bblmw.com/upgrade/studio/settings/BBL/"
            "02.00.00.02/example/02.00.00.02.zip"
        )
        self.offer = Resource("slicer/settings/bbl", "02.00.00.02", self.url, "fix", False)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def run_sync(self, client: SyncClient, *, commit: bool = False):
        def query(_client: object, family: str):
            self.assertEqual(family, "02.00")
            return [self.offer], "https://api.bambulab.com/global?02.00"

        with patch("bambu_ota_archive.capture.query_family", side_effect=query):
            return sync_timeline(
                self.archive,
                self.source,
                client,
                commit=commit,
                pause=0,
            )

    def test_ota_then_studio_release_are_interleaved_by_source_time(self) -> None:
        client = SyncClient(self.ota_archive, "Fri, 02 Jan 2026 00:00:00 GMT")
        result = self.run_sync(client)
        marker = json.loads((self.archive / "profiles/settings/BBL/machine/test.json").read_text())
        self.assertEqual(marker["marker"], "release-new")
        self.assertEqual(result.new_studio_tags, ["v02.00.01.00"])
        self.assertEqual([item.resource.version for item in result.changed_ota], ["02.00.00.02"])
        state = json.loads((self.archive / "state/studio-releases.json").read_text())
        self.assertEqual(state["tags"]["v02.00.01.00"]["status"], "captured")

        second = self.run_sync(client)
        self.assertEqual(second.new_studio_tags, [])
        self.assertEqual(second.changed_ota, [])
        self.assertEqual(client.downloads, 1)

    def test_later_ota_remains_checked_out_after_studio_release(self) -> None:
        client = SyncClient(self.ota_archive, "Sun, 04 Jan 2026 00:00:00 GMT")
        self.run_sync(client)
        marker = json.loads((self.archive / "profiles/settings/BBL/machine/test.json").read_text())
        self.assertEqual(marker["marker"], "ota-middle")

    def test_commit_history_uses_the_same_interleaved_order(self) -> None:
        (self.archive / "catalog").mkdir()
        (self.archive / "catalog/seed-verification.json").write_text("{}\n")
        (self.archive / ".gitignore").write_text("state/run.lock\n")
        subprocess.run(["git", "init", "-q"], cwd=self.archive, check=True)
        subprocess.run(["git", "add", "."], cwd=self.archive, check=True)
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
                "bootstrap",
            ],
            cwd=self.archive,
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.archive, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.archive, check=True)
        client = SyncClient(self.ota_archive, "Fri, 02 Jan 2026 00:00:00 GMT")
        self.run_sync(client, commit=True)
        subjects = subprocess.run(
            ["git", "log", "--reverse", "--format=%s"],
            cwd=self.archive,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        self.assertEqual(
            subjects[-2:],
            [
                "archive: 02.00 settings 02.00.00.02",
                "history: settings 02.00.00.03 (reconstructed Git)",
            ],
        )


if __name__ == "__main__":
    unittest.main()
