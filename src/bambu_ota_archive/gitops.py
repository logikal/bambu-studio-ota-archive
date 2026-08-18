from __future__ import annotations

import os
import subprocess
from pathlib import Path


def _git(root: Path, *args: str, env: dict[str, str] | None = None) -> str:
    process = subprocess.run(
        ["git", "-c", "commit.gpgsign=false", "-c", "tag.gpgsign=false", *args],
        cwd=root,
        env={**os.environ, **(env or {})},
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return process.stdout.strip()


def ensure_clean(root: Path) -> None:
    if _git(root, "status", "--porcelain"):
        raise RuntimeError("working tree must be clean before a committing poll")


def commit_pack(
    root: Path,
    *,
    family: str,
    resource_kind: str,
    version: str,
    sha256: str,
    paths: list[Path],
    repack: bool,
    commit_date: str | None = None,
) -> tuple[str, str]:
    relative_paths = [str(path.relative_to(root)) for path in paths]
    _git(root, "add", "--", *relative_paths)
    if not _git(root, "diff", "--cached", "--name-only"):
        raise RuntimeError("capture produced no staged changes")
    suffix = " (same-version repack)" if repack else ""
    message = f"archive: {family} {resource_kind} {version}{suffix}"
    env = {}
    if commit_date:
        env = {"GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date}
    _git(root, "commit", "--no-gpg-sign", "-m", message, env=env)
    commit = _git(root, "rev-parse", "HEAD")
    tag = f"ota/{family}/{resource_kind}/{version}-{sha256[:12]}"
    annotation = "\n".join(
        [
            "Verified Bambu Studio global OTA profile archive",
            f"Compatibility family: {family}",
            f"Resource: {resource_kind}",
            f"Pack version: {version}",
            f"Archive SHA-256: {sha256}",
            f"Same-version repack: {'yes' if repack else 'no'}",
        ]
    )
    if not _git(root, "tag", "--list", tag):
        _git(root, "tag", "--no-sign", "-a", tag, "-m", annotation)
    return commit, tag


def commit_metadata_only(root: Path, catalog: Path, version: str, commit_date: str | None) -> str:
    _git(root, "add", "--", str(catalog.relative_to(root)))
    if not _git(root, "diff", "--cached", "--name-only"):
        raise RuntimeError("metadata-only import produced no staged change")
    env = {}
    if commit_date:
        env = {"GIT_AUTHOR_DATE": commit_date, "GIT_COMMITTER_DATE": commit_date}
    _git(root, "commit", "--no-gpg-sign", "-m", f"catalog: record unavailable OTA {version}", env=env)
    return _git(root, "rev-parse", "HEAD")


def commit_state_update(root: Path, *, paths: list[Path], message: str) -> str | None:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return None
    _git(root, "add", "--", *(str(path.relative_to(root)) for path in existing))
    if not _git(root, "diff", "--cached", "--name-only"):
        return None
    _git(root, "commit", "--no-gpg-sign", "-m", message)
    return _git(root, "rev-parse", "HEAD")
