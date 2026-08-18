from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .capture import (
    Archiver,
    CaptureResult,
    PollOffer,
    now_iso,
    publication_from_headers,
    repository_lock,
)
from .gitops import commit_state_update, ensure_clean
from .http import HttpClient, validate_profile_cdn_url
from .reconstruction import (
    GitProfileState,
    commit_reconstruction,
    discover_git_releases,
    import_git_reconstruction,
    inspect_git_profile_state,
)
from .studio import (
    load_release_state,
    official_families,
    record_release,
    release_evidence_url,
    validate_and_find_unseen,
)


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    timestamp: datetime
    kind: str
    value: GitProfileState | PollOffer

    def sort_key(self) -> tuple[datetime, int, str]:
        # If source timestamps are identical, preserve the release snapshot before
        # an OTA that may have been published immediately after it.
        order = 0 if self.kind == "studio-release" else 1
        if isinstance(self.value, GitProfileState):
            identity = self.value.revision
        else:
            identity = f"{self.value.family}|{self.value.resource.type}"
        return self.timestamp, order, identity


@dataclass(slots=True)
class SyncResult:
    checked_families: int
    new_studio_tags: list[str]
    changed_ota: list[CaptureResult]

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked_families": self.checked_families,
            "new_studio_tags": self.new_studio_tags,
            "changed_ota": [
                {
                    "family": result.family,
                    "version": result.resource.version,
                    "tag": result.tag,
                }
                for result in self.changed_ota
            ],
        }


def _timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timeline timestamp lacks timezone: {value}")
    return parsed


def _ota_event_time(client: HttpClient, offer: PollOffer, fallback: str) -> datetime:
    kind = "settings" if offer.resource.type == "slicer/settings/bbl" else "printer"
    validate_profile_cdn_url(
        offer.resource.url,
        expected_version=offer.resource.version,
        expected_kind=kind,
    )
    status, headers = client.head_profile(offer.resource.url)
    if 200 <= status < 300:
        publication_time, _ = publication_from_headers(headers)
        if publication_time:
            return _timestamp(publication_time)
    return _timestamp(fallback)


def sync_timeline(
    root: Path,
    source_repo: Path,
    client: HttpClient,
    *,
    commit: bool = False,
    pause: float = 0.2,
) -> SyncResult:
    root = root.resolve()
    source_repo = source_repo.resolve()
    release_state_path = root / "state" / "studio-releases.json"
    with repository_lock(root):
        if commit:
            ensure_clean(root)
        observed_at = now_iso()
        releases = discover_git_releases(source_repo)
        release_state = load_release_state(release_state_path)
        unseen_release_refs = validate_and_find_unseen(release_state, releases)
        unseen_releases = [
            inspect_git_profile_state(source_repo, release.revision, release=release)
            for release in unseen_release_refs
        ]

        archiver = Archiver(root, client, commit=commit, pause=pause)
        plan = archiver.plan_poll(official_families=official_families(releases))
        archiver.persist_poll_plan(plan)

        events = [
            TimelineEvent(_timestamp(release.release_time), "studio-release", release)
            for release in unseen_releases
        ]
        events.extend(
            TimelineEvent(_ota_event_time(client, offer, plan.generated_at), "ota", offer)
            for offer in plan.changed_offers
        )

        changed_ota: list[CaptureResult] = []
        captured_releases: list[str] = []
        for event in sorted(events, key=TimelineEvent.sort_key):
            if event.kind == "ota":
                offer = event.value
                if not isinstance(offer, PollOffer):
                    raise TypeError("OTA event does not contain a poll offer")
                changed_ota.append(archiver.capture_offer(plan, offer))
                continue

            release = event.value
            if not isinstance(release, GitProfileState):
                raise TypeError("Studio event does not contain a Git profile state")
            destination = root / "sources" / "git" / f"{release.version}-{release.commit[:12]}"
            if destination.exists():
                metadata = json.loads((destination / "metadata.json").read_text(encoding="utf-8"))
                if metadata.get("source_commit") != release.commit:
                    raise ValueError(f"Git source destination collision: {destination}")
                status = "equivalent-existing-source"
            else:
                destination = import_git_reconstruction(
                    root,
                    source_repo,
                    release.revision,
                    release_evidence_url(release.revision),
                    observed_at=observed_at,
                    state=release,
                )
                status = "captured"
            record_release(
                release_state_path,
                release_state,
                release,
                observed_at=observed_at,
                status=status,
                source_path=str(destination.relative_to(root)),
            )
            if commit and status == "captured":
                commit_reconstruction(
                    root,
                    destination,
                    extra_paths=[
                        release_state_path,
                        archiver.inventory_path,
                        archiver.seed_report_path,
                    ],
                )
            captured_releases.append(release.revision)

        if commit:
            commit_state_update(
                root,
                paths=[release_state_path, archiver.inventory_path, archiver.seed_report_path],
                message="archive: update capture state",
            )
        return SyncResult(len(plan.official_families), captured_releases, changed_ota)
