from __future__ import annotations

import email.utils
import fcntl
import json
import shutil
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from .archive import extract_zip_safely
from .catalog import (
    append_observation,
    is_same_version_repack,
    read_json,
    read_observations,
    write_json_atomic,
)
from .constants import MAIN_RESOURCE_TYPE
from .discovery import baseline_for_family, discover_official_families, query_family
from .gitops import commit_pack, ensure_clean
from .http import HttpClient, polite_pause, validate_profile_cdn_url
from .models import Observation, Resource


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def resource_kind(resource_type: str) -> str:
    if resource_type == "slicer/settings/bbl":
        return "settings"
    if resource_type == "slicer/printer/bbl":
        return "printer"
    raise ValueError(f"unsupported resource type: {resource_type}")


def publication_from_headers(headers: dict[str, str]) -> tuple[str | None, str]:
    value = headers.get("last-modified")
    if not value:
        return None, "unknown"
    parsed = email.utils.parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"), "estimated-from-cdn-last-modified"


@dataclass(slots=True)
class CaptureResult:
    family: str
    resource: Resource
    changed: bool
    sha256: str | None = None
    tag: str | None = None


@contextmanager
def repository_lock(root: Path) -> Iterator[None]:
    path = root / "state" / "run.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError("another archive run is active") from exc
        yield


class Archiver:
    def __init__(self, root: Path, client: HttpClient, *, commit: bool = False, pause: float = 0.2):
        self.root = root.resolve()
        self.client = client
        self.commit = commit
        self.pause = pause
        self.catalog_path = self.root / "catalog" / "observations.jsonl"
        self.state_path = self.root / "state" / "last_seen.json"
        self.inventory_path = self.root / "catalog" / "current-inventory.json"
        self.seed_path = self.root / "evidence" / "known-global-seed.json"
        self.seed_report_path = self.root / "catalog" / "seed-verification.json"

    def ota_source_root(self, family: str, kind: str, version: str, sha256: str) -> Path:
        return self.root / "sources" / "ota" / family / kind / f"{version}-{sha256[:12]}"

    def poll(self, *, families: list[str] | None = None) -> list[CaptureResult]:
        with repository_lock(self.root):
            if self.commit:
                ensure_clean(self.root)
            official = discover_official_families(self.client, pause=self.pause)
            selected = official if families is None else families
            unknown = sorted(set(selected) - set(official))
            if unknown:
                raise ValueError(f"refusing unpublished families: {', '.join(unknown)}")
            state = read_json(self.state_path, {})
            first_live_run = not self.inventory_path.exists()
            inventory: dict[str, Any] = {
                "generated_at": now_iso(),
                "source": "global-api",
                "official_families": official,
                "families": {},
            }
            offered: list[tuple[str, Resource, str]] = []
            results: list[CaptureResult] = []
            for index, family in enumerate(selected):
                resources, query_url = query_family(self.client, family)
                inventory["families"][family] = {
                    "api_query_version": baseline_for_family(family),
                    "query_url": query_url,
                    "resources": [resource.to_dict() for resource in resources],
                }
                offered.extend((family, resource, query_url) for resource in resources)
                if index + 1 < len(selected):
                    polite_pause(self.pause)

            changed_offers = [
                (family, resource, query_url)
                for family, resource, query_url in offered
                if state.get(f"{family}|{resource.type}", {}).get("tuple")
                != list(resource.comparison_tuple())
            ]
            if changed_offers or not self.inventory_path.exists():
                write_json_atomic(self.inventory_path, inventory)
            if first_live_run and self.seed_path.exists():
                write_json_atomic(self.seed_report_path, compare_seed_inventory(read_json(self.seed_path, {}), inventory))

            for family, resource, query_url in offered:
                key = f"{family}|{resource.type}"
                current_tuple = list(resource.comparison_tuple())
                if state.get(key, {}).get("tuple") == current_tuple:
                    results.append(CaptureResult(family, resource, False))
                    continue
                result = self.capture_resource(
                    family,
                    resource,
                    provenance="observed-api",
                    evidence=query_url,
                    observed_at=inventory["generated_at"],
                    do_commit=False,
                )
                state[key] = {"tuple": current_tuple, "observed_at": inventory["generated_at"]}
                write_json_atomic(self.state_path, state)
                if self.commit:
                    kind = resource_kind(resource.type)
                    source_root = self.ota_source_root(family, kind, resource.version, result.sha256 or "")
                    metadata = read_json(source_root / "metadata.json", {})
                    _, result.tag = commit_pack(
                        self.root,
                        family=family,
                        resource_kind=resource_kind(resource.type),
                        version=resource.version,
                        sha256=result.sha256 or "",
                        paths=[
                            source_root,
                            self.root / "profiles" / kind,
                            self.root / "timeline" / f"{kind}.json",
                            self.catalog_path,
                            self.state_path,
                            self.inventory_path,
                            self.seed_report_path,
                        ],
                        repack=metadata.get("same_version_repack") is True,
                        commit_date=metadata.get("publication_time"),
                    )
                results.append(result)
            return results

    def capture_resource(
        self,
        family: str,
        resource: Resource,
        *,
        provenance: str,
        evidence: str,
        observed_at: str,
        publication_time: str | None = None,
        uncertainty: list[str] | None = None,
        do_commit: bool | None = None,
    ) -> CaptureResult:
        kind = resource_kind(resource.type)
        validate_profile_cdn_url(resource.url, expected_version=resource.version, expected_kind=kind)
        records = read_observations(self.catalog_path)
        with tempfile.TemporaryDirectory(prefix="bambu-ota-capture-") as raw_temp:
            download = self.client.download(resource.url, Path(raw_temp))
            repack = is_same_version_repack(
                records, family, resource.type, resource.version, resource.url, download.sha256
            )
            source_root = self.ota_source_root(family, kind, resource.version, download.sha256)
            source_root.mkdir(parents=True, exist_ok=True)
            archive_path = source_root / "archive.zip"
            archive_temp = source_root / ".archive.zip.tmp"
            shutil.copyfile(download.path, archive_temp)
            archive_temp.replace(archive_path)
            profile_root = self.root / "profiles" / kind
            validation = extract_zip_safely(download.path, profile_root, resource.version)
            retrieved_at = now_iso()
            header_publication, header_status = publication_from_headers(download.headers)
            effective_publication = publication_time or header_publication
            publication_status = "confirmed-evidence" if publication_time else header_status
            observation = Observation(
                provenance=provenance,
                evidence=evidence,
                compatibility_family=family,
                api_query_version=baseline_for_family(family),
                resource_type=resource.type,
                pack_version=resource.version,
                cdn_url=resource.url,
                description=resource.description,
                force_update=resource.force_update,
                archive_sha256=download.sha256,
                archive_md5=download.md5,
                archive_size=download.size,
                cdn_headers=download.headers,
                first_observed_at=observed_at,
                retrieved_at=retrieved_at,
                publication_time=effective_publication,
                publication_time_status=publication_status,
                directly_verified=True,
                provenance_chain=list(dict.fromkeys([provenance, "retrieved-cdn"])),
                same_version_repack=repack,
                uncertainty=uncertainty or [],
            )
            metadata = observation.to_dict() | {
                "source_path": str(source_root.relative_to(self.root)),
                "validation": {
                    "file_count": validation.file_count,
                    "expanded_size": validation.expanded_size,
                    "bbl_json_path": validation.bbl_json_path,
                    "bbl_version": validation.bbl_version,
                }
            }
            write_json_atomic(source_root / "metadata.json", metadata)
            write_json_atomic(self.root / "timeline" / f"{kind}.json", metadata)
            # Description/force changes can require a fresh verified download while the
            # catalog identity (family/type/version/URL/SHA-256) remains the same.
            append_observation(self.catalog_path, observation)
            tag = None
            should_commit = self.commit if do_commit is None else do_commit
            if should_commit:
                _, tag = commit_pack(
                    self.root,
                    family=family,
                    resource_kind=kind,
                    version=resource.version,
                    sha256=download.sha256,
                    paths=[
                        source_root,
                        profile_root,
                        self.root / "timeline" / f"{kind}.json",
                        self.catalog_path,
                    ],
                    repack=repack,
                    commit_date=effective_publication,
                )
            return CaptureResult(family, resource, True, download.sha256, tag)

    def import_metadata_only(self, record: dict[str, Any]) -> bool:
        family = record["compatibility_family"]
        observation = Observation(
            provenance="metadata-only",
            evidence=record["evidence"],
            compatibility_family=family,
            api_query_version=record.get("api_query_version", baseline_for_family(family)),
            resource_type=record["resource_type"],
            pack_version=record["pack_version"],
            cdn_url=record.get("cdn_url"),
            description=record.get("description", ""),
            force_update=record.get("force_update") is True,
            archive_sha256=None,
            archive_md5=None,
            archive_size=None,
            cdn_headers=record.get("cdn_headers", {}),
            first_observed_at=record["first_observed_at"],
            retrieved_at=None,
            publication_time=record.get("publication_time"),
            publication_time_status=record.get("publication_time_status", "unknown"),
            directly_verified=False,
            provenance_chain=["metadata-only"],
            uncertainty=record.get("uncertainty", ["archive bytes were not available"]),
        )
        return append_observation(self.catalog_path, observation)


def compare_seed_inventory(seed: dict[str, Any], inventory: dict[str, Any]) -> dict[str, Any]:
    comparisons: dict[str, Any] = {}
    all_match = True
    for family, expected in seed.get("families", {}).items():
        offered = inventory.get("families", {}).get(family, {}).get("resources", [])
        settings = [item for item in offered if item.get("type") == MAIN_RESOURCE_TYPE]
        actual = None
        if settings:
            actual = {"version": settings[0].get("version"), "url": settings[0].get("url")}
        match = actual == expected
        all_match &= match
        comparisons[family] = {"expected": expected, "actual": actual, "match": match}
    return {
        "checked_at": inventory.get("generated_at"),
        "seed_as_of": seed.get("as_of"),
        "all_match": all_match,
        "comparisons": comparisons,
        "note": "The user-supplied seed was used only for this first-live-run comparison.",
    }
