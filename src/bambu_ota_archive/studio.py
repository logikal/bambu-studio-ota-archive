from __future__ import annotations

from pathlib import Path
from typing import Any
from urllib.parse import quote

from .catalog import read_json, write_json_atomic
from .discovery import discover_families_from_tags
from .reconstruction import GitProfileState, GitRelease

STUDIO_REPOSITORY = "https://github.com/bambulab/BambuStudio"


def release_evidence_url(revision: str) -> str:
    return f"{STUDIO_REPOSITORY}/tree/{quote(revision, safe='')}"


def load_release_state(path: Path) -> dict[str, Any]:
    state = read_json(path, {})
    if not isinstance(state, dict) or not isinstance(state.get("tags"), dict):
        raise ValueError(f"invalid Studio release state: {path}")
    return state


def validate_and_find_unseen(
    tracked: dict[str, Any], releases: list[GitRelease]
) -> list[GitRelease]:
    by_revision = {release.revision: release for release in releases}
    for revision, record in tracked["tags"].items():
        release = by_revision.get(revision)
        if release is None:
            continue
        expected = record.get("source_commit")
        if expected != release.commit:
            raise ValueError(
                f"official Studio tag moved: {revision} was {expected}, now {release.commit}"
            )
    return [release for release in releases if release.revision not in tracked["tags"]]


def official_families(releases: list[GitRelease]) -> list[str]:
    return discover_families_from_tags(release.revision for release in releases)


def record_release(
    path: Path,
    state: dict[str, Any],
    release: GitProfileState,
    *,
    observed_at: str,
    status: str,
    source_path: str | None,
) -> None:
    state["tags"][release.revision] = {
        "first_observed_at": observed_at,
        "profile_version": release.version,
        "source_bbl_json_blob": release.bbl_json_blob,
        "source_commit": release.commit,
        "source_commit_time": release.commit_time,
        "source_release_time": release.release_time,
        "source_path": source_path,
        "source_tree": release.tree,
        "status": status,
    }
    state["last_checked_at"] = observed_at
    write_json_atomic(path, state)
