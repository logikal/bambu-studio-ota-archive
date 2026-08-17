from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .models import Observation


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    with temp.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
        stream.write("\n")
    temp.replace(path)


def read_observations(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(f"invalid catalog JSON on line {line_number}") from exc
    return records


def append_observation(path: Path, observation: Observation) -> bool:
    identity = observation.identity()
    for record in read_observations(path):
        existing = (
            record.get("compatibility_family"),
            record.get("resource_type"),
            record.get("pack_version"),
            record.get("cdn_url") or "",
            record.get("archive_sha256") or "",
        )
        if existing == identity:
            return False
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(observation.to_dict(), sort_keys=True, ensure_ascii=False))
        stream.write("\n")
    return True


def is_same_version_repack(
    records: list[dict[str, Any]], family: str, resource_type: str, version: str, url: str, sha256: str
) -> bool:
    return any(
        record.get("compatibility_family") == family
        and record.get("resource_type") == resource_type
        and record.get("pack_version") == version
        and (record.get("cdn_url") != url or record.get("archive_sha256") != sha256)
        for record in records
        if record.get("archive_sha256")
    )

