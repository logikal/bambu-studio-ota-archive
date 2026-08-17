from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .constants import ALLOWED_RESOURCE_TYPES
from .models import Resource

CDN_URL_RE = re.compile(
    r"https://public-cdn\.bblmw\.com/upgrade/studio/(?:settings|printer)/BBL/"
    r"\d{2}\.\d{2}\.\d{2}\.\d{2}/[A-Za-z0-9._-]+/\d{2}\.\d{2}\.\d{2}\.\d{2}\.zip"
)

SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "cookie",
    "device_id",
    "ip",
    "refresh_token",
    "token",
    "username",
    "user_id",
}


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.casefold() in SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def extract_resources_from_log(text: str) -> list[dict[str, Any]]:
    """Extract only OTA resource metadata; never return unrelated log content."""
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for line in text.splitlines():
        marker = "request_resources, body="
        if marker in line:
            candidate = line.split(marker, 1)[1].strip()
            try:
                payload = json.loads(candidate)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                for item in payload.get("resources") or []:
                    if not isinstance(item, dict) or item.get("type") not in ALLOWED_RESOURCE_TYPES:
                        continue
                    subset = {
                        "type": item.get("type"),
                        "version": item.get("version"),
                        "url": item.get("url"),
                        "description": item.get("description") if isinstance(item.get("description"), str) else "",
                        "force_update": item.get("force_update") is True,
                    }
                    key = (str(subset["type"]), str(subset["version"]), str(subset["url"]))
                    if key not in seen:
                        seen.add(key)
                        results.append(redact_sensitive(subset))
        for url in CDN_URL_RE.findall(line):
            version = url.rsplit("/", 1)[-1].removesuffix(".zip")
            resource_type = "slicer/printer/bbl" if "/printer/" in url else "slicer/settings/bbl"
            key = (resource_type, version, url)
            if key not in seen:
                seen.add(key)
                results.append(
                    {
                        "type": resource_type,
                        "version": version,
                        "url": url,
                        "description": "",
                        "force_update": False,
                    }
                )
    return results


def extract_log_file(source: Path, destination: Path, evidence_identifier: str) -> int:
    resources = extract_resources_from_log(source.read_text(encoding="utf-8", errors="replace"))
    records = [{"evidence": evidence_identifier, "resource": resource} for resource in resources]
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(records, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return len(records)


def resource_from_evidence(record: dict[str, Any]) -> Resource:
    item = record["resource"] if "resource" in record else record
    return Resource(
        type=item["type"],
        version=item["version"],
        url=item["url"],
        description=item.get("description", ""),
        force_update=item.get("force_update") is True,
    )

