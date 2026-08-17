from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Resource:
    type: str
    version: str
    url: str
    description: str
    force_update: bool

    def comparison_tuple(self) -> tuple[str, str, str, str, bool]:
        return (self.type, self.version, self.url, self.description, self.force_update)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Observation:
    provenance: str
    evidence: str
    compatibility_family: str
    api_query_version: str
    resource_type: str
    pack_version: str
    cdn_url: str | None
    description: str
    force_update: bool
    archive_sha256: str | None
    archive_md5: str | None
    archive_size: int | None
    cdn_headers: dict[str, str]
    first_observed_at: str
    retrieved_at: str | None
    publication_time: str | None
    publication_time_status: str
    directly_verified: bool
    same_version_repack: bool = False
    uncertainty: list[str] = field(default_factory=list)
    source_commit: str | None = None
    source_tree: str | None = None

    def identity(self) -> tuple[str, str, str, str, str]:
        return (
            self.compatibility_family,
            self.resource_type,
            self.pack_version,
            self.cdn_url or "",
            self.archive_sha256 or "",
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

