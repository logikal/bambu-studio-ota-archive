from __future__ import annotations

import json
import shutil
import stat
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .catalog import write_json_atomic


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


def import_git_reconstruction(root: Path, source_repo: Path, revision: str, evidence: str) -> Path:
    commit = str(_git(source_repo, "rev-parse", f"{revision}^{{commit}}" )).strip()
    bbl_raw = _git(source_repo, "show", f"{commit}:resources/profiles/BBL.json", binary=True)
    bbl = json.loads(bbl_raw)
    version = bbl.get("version")
    if not isinstance(version, str) or not version.startswith("0"):
        raise ValueError("source BBL.json has no valid version")
    major = int(version.split(".", 1)[0])
    if major < 2:
        raise ValueError("only Studio 2.x-or-later reconstructions are in scope")
    tree = str(_git(source_repo, "rev-parse", f"{commit}:resources/profiles/BBL")).strip()
    commit_time = str(_git(source_repo, "show", "-s", "--format=%cI", commit)).strip()
    destination = root / "reconstructions" / "git" / f"{version}-{commit[:12]}"
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
                commit,
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
        contents = staged / "contents"
        shutil.copytree(expanded / "resources" / "profiles" / "BBL", contents)
        shutil.copyfile(expanded / "resources" / "profiles" / "BBL.json", contents / "BBL.json")
        metadata = {
            "provenance": "reconstructed-git",
            "evidence": evidence,
            "pack_version": version,
            "source_commit": commit,
            "source_tree": tree,
            "source_commit_time": commit_time,
            "cdn_url": None,
            "directly_verified": False,
            "uncertainty": [
                "Public Git content is not proof that an OTA archive was published.",
                "A live OTA archive may differ from this tree despite sharing the BBL.json version.",
            ],
        }
        write_json_atomic(staged / "metadata.json", metadata)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.rmtree(destination)
        staged.replace(destination)
    return destination


def commit_reconstruction(root: Path, destination: Path) -> str:
    subprocess.run(["git", "add", "--", str(destination.relative_to(root))], cwd=root, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-gpg-sign",
            "-m",
            f"reconstruct: Git profile state {destination.name}",
        ],
        cwd=root,
        check=True,
    )
    return str(_git(root, "rev-parse", "HEAD")).strip()

