from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .archive import validate_zip
from .catalog import read_observations


def _hashes(path: Path) -> tuple[str, str, int]:
    sha256 = hashlib.sha256()
    md5 = hashlib.md5(usedforsecurity=False)
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            sha256.update(chunk)
            md5.update(chunk)
    return sha256.hexdigest(), md5.hexdigest(), size


def audit_repository(root: Path) -> dict[str, int]:
    root = root.resolve()
    observations = read_observations(root / "catalog" / "observations.jsonl")
    identities: set[tuple[Any, ...]] = set()
    for record in observations:
        identity = (
            record.get("compatibility_family"),
            record.get("resource_type"),
            record.get("pack_version"),
            record.get("cdn_url"),
            record.get("archive_sha256"),
        )
        if identity in identities:
            raise ValueError(f"duplicate observation identity: {identity}")
        identities.add(identity)

    verified = 0
    for metadata_path in sorted((root / "sources" / "ota").glob("*/*/*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_path") != str(metadata_path.parent.relative_to(root)):
            raise ValueError(f"incorrect OTA source path: {metadata_path}")
        if metadata.get("directly_verified") is not True:
            raise ValueError(f"unverified metadata in verified OTA source tree: {metadata_path}")
        archive = metadata_path.with_name("archive.zip")
        sha256, md5, size = _hashes(archive)
        if (sha256, md5, size) != (
            metadata.get("archive_sha256"),
            metadata.get("archive_md5"),
            metadata.get("archive_size"),
        ):
            raise ValueError(f"archive hash or size mismatch: {archive}")
        validation = validate_zip(archive, metadata["pack_version"])
        if validation.bbl_version != metadata.get("validation", {}).get("bbl_version"):
            raise ValueError(f"stored validation mismatch: {metadata_path}")
        identity = (
            metadata.get("compatibility_family"),
            metadata.get("resource_type"),
            metadata.get("pack_version"),
            metadata.get("cdn_url"),
            metadata.get("archive_sha256"),
        )
        if identity not in identities:
            raise ValueError(f"current verified pack absent from observation catalog: {metadata_path}")
        verified += 1

    reconstructions = 0
    reconstruction_by_revision: dict[str, Path] = {}
    for metadata_path in sorted((root / "sources" / "git").glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if metadata.get("source_path") != str(metadata_path.parent.relative_to(root)):
            raise ValueError(f"incorrect Git source path: {metadata_path}")
        if (
            metadata.get("provenance") != "reconstructed-git"
            or metadata.get("directly_verified") is not False
            or metadata.get("cdn_url") is not None
        ):
            raise ValueError(f"invalid Git reconstruction classification: {metadata_path}")
        if not metadata.get("source_commit") or not metadata.get("source_tree"):
            raise ValueError(f"incomplete Git reconstruction identity: {metadata_path}")
        revision = metadata.get("source_revision")
        if not isinstance(revision, str) or revision in reconstruction_by_revision:
            raise ValueError(f"invalid or duplicate Git source revision: {metadata_path}")
        reconstruction_by_revision[revision] = metadata_path
        reconstructions += 1

    tracked_studio_tags = 0
    release_state_path = root / "state" / "studio-releases.json"
    if release_state_path.exists():
        release_state = json.loads(release_state_path.read_text(encoding="utf-8"))
        if release_state.get("source") != "https://github.com/bambulab/BambuStudio":
            raise ValueError("Studio release tracker has an unexpected source")
        tags = release_state.get("tags")
        if not isinstance(tags, dict):
            raise ValueError("Studio release tracker has no tags object")
        for revision, record in tags.items():
            if not re.fullmatch(r"[vV]\d{2}\.\d{2}\.\d{2}\.\d{2}", revision):
                raise ValueError(f"invalid tracked Studio tag: {revision}")
            if not isinstance(record, dict) or not re.fullmatch(
                r"[0-9a-f]{40}", str(record.get("source_commit", ""))
            ):
                raise ValueError(f"invalid tracked Studio commit: {revision}")
            status = record.get("status")
            if status not in {"baseline-before-automation", "captured", "equivalent-existing-source"}:
                raise ValueError(f"invalid tracked Studio status: {revision}")
            if status in {"captured", "equivalent-existing-source"}:
                source_path = record.get("source_path")
                if not isinstance(source_path, str):
                    raise ValueError(f"tracked Studio capture is missing its source record: {revision}")
                metadata_path = root / source_path / "metadata.json"
                if not metadata_path.is_file():
                    raise ValueError(f"tracked Studio capture is missing its source record: {revision}")
                metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                if metadata.get("source_commit") != record.get("source_commit"):
                    raise ValueError(f"tracked Studio commit mismatch: {revision}")
                if status == "captured" and reconstruction_by_revision.get(revision) != metadata_path:
                    raise ValueError(f"tracked Studio revision mismatch: {revision}")
            tracked_studio_tags += 1
        missing = sorted(set(reconstruction_by_revision) - set(tags))
        if missing:
            raise ValueError(f"Git reconstructions absent from Studio release tracker: {', '.join(missing)}")

    for timeline_path in sorted((root / "timeline").glob("*.json")):
        metadata = json.loads(timeline_path.read_text(encoding="utf-8"))
        profile_manifest = root / "profiles" / timeline_path.stem / "BBL.json"
        profile_version = json.loads(profile_manifest.read_text(encoding="utf-8")).get("version")
        if profile_version != metadata.get("pack_version"):
            raise ValueError(f"timeline/profile version mismatch: {timeline_path}")
        source_path = metadata.get("source_path")
        if not isinstance(source_path, str) or not (root / source_path / "metadata.json").is_file():
            raise ValueError(f"timeline source is missing: {timeline_path}")

    return {
        "observations": len(observations),
        "verified_archives": verified,
        "git_reconstructions": reconstructions,
        "tracked_studio_tags": tracked_studio_tags,
    }
