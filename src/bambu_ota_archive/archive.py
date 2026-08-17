from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .constants import MAX_COMPRESSION_RATIO, MAX_EXPANDED_BYTES, MAX_FILES


class UnsafeArchive(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ArchiveValidation:
    file_count: int
    expanded_size: int
    bbl_json_path: str
    bbl_version: str


def _validated_name(raw_name: str) -> PurePosixPath:
    if "\x00" in raw_name:
        raise UnsafeArchive("NUL character in member path")
    if "\\" in raw_name:
        raise UnsafeArchive("backslash in member path")
    path = PurePosixPath(raw_name)
    if path.is_absolute() or raw_name.startswith("/"):
        raise UnsafeArchive("absolute member path")
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise UnsafeArchive("empty, dot, or traversal path component")
    if path.parts[0].endswith(":"):
        raise UnsafeArchive("drive-qualified member path")
    return path


def validate_zip(
    archive: Path,
    expected_version: str,
    *,
    max_files: int = MAX_FILES,
    max_expanded_bytes: int = MAX_EXPANDED_BYTES,
    max_compression_ratio: float = MAX_COMPRESSION_RATIO,
) -> ArchiveValidation:
    try:
        with zipfile.ZipFile(archive) as zf:
            members = zf.infolist()
            if len(members) > max_files:
                raise UnsafeArchive("excessive file count")
            seen: set[str] = set()
            seen_casefolded: set[str] = set()
            expanded = 0
            bbl_candidates: list[zipfile.ZipInfo] = []
            for member in members:
                path = _validated_name(member.filename)
                normalized = path.as_posix().rstrip("/")
                if normalized in seen:
                    raise UnsafeArchive("duplicate member path")
                folded = normalized.casefold()
                if folded in seen_casefolded:
                    raise UnsafeArchive("case-colliding member paths")
                seen.add(normalized)
                seen_casefolded.add(folded)
                unix_mode = member.external_attr >> 16
                file_type = stat.S_IFMT(unix_mode)
                if file_type == stat.S_IFLNK:
                    raise UnsafeArchive("symbolic link member")
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise UnsafeArchive("non-regular member (including hard-link-like entries)")
                expanded += member.file_size
                if expanded > max_expanded_bytes:
                    raise UnsafeArchive("excessive expanded size")
                if member.file_size and member.compress_size == 0:
                    raise UnsafeArchive("invalid zero compressed size")
                if member.compress_size and member.file_size / member.compress_size > max_compression_ratio:
                    raise UnsafeArchive("suspicious compression ratio")
                if not member.is_dir() and path.name == "BBL.json":
                    bbl_candidates.append(member)
            if len(bbl_candidates) != 1:
                raise UnsafeArchive("archive must contain exactly one BBL.json")
            bad_member = zf.testzip()
            if bad_member is not None:
                raise UnsafeArchive(f"CRC failure in {bad_member}")
            with zf.open(bbl_candidates[0]) as stream:
                try:
                    bbl = json.load(stream)
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise UnsafeArchive("invalid BBL.json") from exc
            actual_version = bbl.get("version") if isinstance(bbl, dict) else None
            if actual_version != expected_version:
                raise UnsafeArchive(
                    f"BBL.json version {actual_version!r} does not match pack {expected_version!r}"
                )
            return ArchiveValidation(len(members), expanded, bbl_candidates[0].filename, actual_version)
    except (zipfile.BadZipFile, EOFError, OSError) as exc:
        raise UnsafeArchive("invalid, corrupt, or truncated ZIP archive") from exc


def extract_zip_safely(archive: Path, destination: Path, expected_version: str) -> ArchiveValidation:
    validation = validate_zip(archive, expected_version)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}-", dir=destination.parent))
    try:
        with zipfile.ZipFile(archive) as zf:
            for member in zf.infolist():
                relative = _validated_name(member.filename)
                target = temp.joinpath(*relative.parts)
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
        old = destination.with_name(f".{destination.name}.old-{os.getpid()}")
        if old.exists():
            shutil.rmtree(old)
        if destination.exists():
            destination.replace(old)
        temp.replace(destination)
        if old.exists():
            shutil.rmtree(old)
        return validation
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise

