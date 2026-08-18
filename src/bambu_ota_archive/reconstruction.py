from __future__ import annotations

import json
import os
import re
import shutil
import stat
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath

from .catalog import write_json_atomic
from .discovery import TAG_RE


@dataclass(frozen=True, slots=True)
class GitRelease:
    revision: str
    commit: str
    commit_time: str
    release_time: str

    def sort_key(self) -> tuple[datetime, str]:
        return datetime.fromisoformat(self.release_time), self.revision


@dataclass(frozen=True, slots=True)
class GitProfileState:
    revision: str
    commit: str
    version: str
    tree: str
    bbl_json_blob: str
    commit_time: str
    release_time: str

    def sort_key(self) -> tuple[datetime, str]:
        return datetime.fromisoformat(self.release_time), self.revision


def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=not binary,
    )
    return result.stdout


def _safe_git_tar_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:") as tf:
        seen: set[str] = set()
        folded: set[str] = set()
        total = 0
        members = tf.getmembers()
        if len(members) > 100_000:
            raise ValueError("Git reconstruction has excessive file count")
        for member in members:
            path = PurePosixPath(member.name)
            if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
                raise ValueError("unsafe path in Git archive")
            normalized = path.as_posix().rstrip("/")
            if normalized in seen or normalized.casefold() in folded:
                raise ValueError("duplicate or case-colliding path in Git archive")
            seen.add(normalized)
            folded.add(normalized.casefold())
            if member.issym() or member.islnk():
                raise ValueError("links are forbidden in Git reconstruction archives")
            if not (member.isfile() or member.isdir()):
                raise ValueError("non-regular entry in Git reconstruction archive")
            total += member.size
            if total > 2 * 1024 * 1024 * 1024:
                raise ValueError("Git reconstruction exceeds expanded-size limit")
        for member in members:
            target = destination.joinpath(*PurePosixPath(member.name).parts)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                source = tf.extractfile(member)
                if source is None:
                    raise ValueError("unable to read Git archive member")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def inspect_git_profile_state(
    source_repo: Path,
    revision: str,
    *,
    release: GitRelease | None = None,
) -> GitProfileState:
    source_release = release or inspect_git_release(source_repo, revision)
    if source_release.revision != revision:
        raise ValueError("Git release revision does not match requested revision")
    commit = source_release.commit
    bbl_raw = _git(source_repo, "show", f"{commit}:resources/profiles/BBL.json", binary=True)
    bbl = json.loads(bbl_raw)
    version = bbl.get("version")
    if not isinstance(version, str) or not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", version):
        raise ValueError("source BBL.json has no valid version")
    tree = str(_git(source_repo, "rev-parse", f"{commit}:resources/profiles/BBL")).strip()
    bbl_blob = str(_git(source_repo, "rev-parse", f"{commit}:resources/profiles/BBL.json")).strip()
    return GitProfileState(
        revision,
        commit,
        version,
        tree,
        bbl_blob,
        source_release.commit_time,
        source_release.release_time,
    )


def inspect_git_release(source_repo: Path, revision: str) -> GitRelease:
    commit = str(_git(source_repo, "rev-parse", f"{revision}^{{commit}}")).strip()
    commit_time = str(_git(source_repo, "show", "-s", "--format=%cI", commit)).strip()
    release_time = str(
        _git(
            source_repo,
            "for-each-ref",
            "--format=%(creatordate:iso8601-strict)",
            f"refs/tags/{revision}",
        )
    ).strip()
    if not release_time:
        release_time = commit_time
    return GitRelease(revision, commit, commit_time, release_time)


def discover_git_releases(source_repo: Path) -> list[GitRelease]:
    revisions = str(
        _git(source_repo, "for-each-ref", "--format=%(refname:short)", "refs/tags")
    ).splitlines()
    releases = []
    for revision in revisions:
        match = TAG_RE.fullmatch(revision)
        if match and int(match.group("major")) >= 2:
            releases.append(inspect_git_release(source_repo, revision))
    return sorted(releases, key=GitRelease.sort_key)


def import_git_reconstruction(
    root: Path,
    source_repo: Path,
    revision: str,
    evidence: str,
    *,
    observed_at: str | None = None,
    state: GitProfileState | None = None,
) -> Path:
    automated_release = state is not None
    source = state or inspect_git_profile_state(source_repo, revision)
    if source.revision != revision:
        raise ValueError("Git profile state revision does not match requested revision")
    if not automated_release and int(source.version.split(".", 1)[0]) < 2:
        raise ValueError("only Studio 2.x-or-later reconstructions are in scope")
    destination = root / "sources" / "git" / f"{source.version}-{source.commit[:12]}"
    with tempfile.TemporaryDirectory(prefix="bambu-git-reconstruction-") as temp_raw:
        temp = Path(temp_raw)
        tar_path = temp / "profiles.tar"
        archive = subprocess.run(
            [
                "git",
                "archive",
                "--format=tar",
                "--output",
                str(tar_path),
                source.commit,
                "resources/profiles/BBL",
                "resources/profiles/BBL.json",
            ],
            cwd=source_repo,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        del archive
        expanded = temp / "expanded"
        expanded.mkdir()
        _safe_git_tar_extract(tar_path, expanded)
        staged = temp / "staged"
        profiles = staged / "profiles"
        shutil.copytree(expanded / "resources" / "profiles" / "BBL", profiles / "BBL")
        shutil.copyfile(expanded / "resources" / "profiles" / "BBL.json", profiles / "BBL.json")
        metadata = {
            "provenance": "reconstructed-git",
            "provenance_chain": ["reconstructed-git"],
            "evidence": evidence,
            "pack_version": source.version,
            "source_commit": source.commit,
            "source_tree": source.tree,
            "source_bbl_json_blob": source.bbl_json_blob,
            "source_revision": revision,
            "source_commit_time": source.commit_time,
            "source_release_time": source.release_time,
            "first_observed_at": observed_at,
            "cdn_url": None,
            "directly_verified": False,
            "uncertainty": [
                "Public Git content is not proof that an OTA archive was published.",
                "A live OTA archive may differ from this tree despite sharing the BBL.json version.",
            ],
        }
        metadata["source_path"] = str(destination.relative_to(root))
        write_json_atomic(staged / "metadata.json", metadata)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
        profile_root = root / "profiles" / "settings"
        extracted_profiles = destination / "profiles"
        if profile_root.exists():
            shutil.rmtree(profile_root)
        profile_root.parent.mkdir(parents=True, exist_ok=True)
        extracted_profiles.replace(profile_root)
        write_json_atomic(root / "timeline" / "settings.json", metadata)
    return destination


def commit_reconstruction(
    root: Path,
    destination: Path,
    *,
    extra_paths: list[Path] | None = None,
) -> str:
    metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
    paths = [
        str(destination.relative_to(root)),
        "profiles/settings",
        "timeline/settings.json",
        *(str(path.relative_to(root)) for path in (extra_paths or [])),
    ]
    subprocess.run(
        [
            "git",
            "add",
            "--",
            *paths,
        ],
        cwd=root,
        check=True,
    )
    timeline_time = metadata.get("source_release_time") or metadata["source_commit_time"]
    env = {**os.environ, "GIT_AUTHOR_DATE": timeline_time, "GIT_COMMITTER_DATE": timeline_time}
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            f"history: settings {metadata['pack_version']} (reconstructed Git)",
        ],
        cwd=root,
        env=env,
        check=True,
    )
    tag = f"reconstructed-git/{metadata['pack_version']}-{metadata['source_commit'][:12]}"
    subprocess.run(
        [
            "git",
            "-c",
            "tag.gpgsign=false",
            "tag",
            "--no-sign",
            "-a",
            tag,
            "-m",
            "\n".join(
                [
                    "Bambu Studio profile state reconstructed from public Git",
                    "Not a verified OTA archive",
                    f"Pack version: {metadata['pack_version']}",
                    f"Source commit: {metadata['source_commit']}",
                ]
            ),
        ],
        cwd=root,
        check=True,
    )
    return str(_git(root, "rev-parse", "HEAD")).strip()
