from __future__ import annotations

import json
import re
from collections.abc import Iterable
from urllib.parse import urlencode

from .constants import (
    ALLOWED_RESOURCE_TYPES,
    API_ENDPOINT,
    GITHUB_TAGS_ENDPOINT,
    MAIN_RESOURCE_TYPE,
    PRINTER_RESOURCE_TYPE,
)
from .http import HttpClient, polite_pause
from .models import Resource

TAG_RE = re.compile(r"^[vV](?P<major>\d{2})\.(?P<minor>\d{2})\.\d{2}\.\d{2}$")
VERSION_RE = re.compile(r"^(?P<major>\d{2})\.(?P<minor>\d{2})\.\d{2}\.\d{2}$")


def discover_families_from_tags(tags: Iterable[str]) -> list[str]:
    families: set[tuple[int, int]] = set()
    for tag in tags:
        match = TAG_RE.fullmatch(tag)
        if not match:
            continue
        major = int(match.group("major"))
        minor = int(match.group("minor"))
        if major >= 2:
            families.add((major, minor))
    return [f"{major:02d}.{minor:02d}" for major, minor in sorted(families)]


def baseline_for_family(family: str) -> str:
    if not re.fullmatch(r"\d{2}\.\d{2}", family):
        raise ValueError(f"invalid compatibility family: {family}")
    major, _ = (int(piece) for piece in family.split("."))
    if major < 2:
        raise ValueError("only Studio major version 2 and later are in scope")
    return f"{family}.00.00"


def discover_official_families(client: HttpClient, *, pause: float = 0.2) -> list[str]:
    tags: list[str] = []
    for page in range(1, 101):
        url = f"{GITHUB_TAGS_ENDPOINT}?{urlencode({'per_page': 100, 'page': page})}"
        body, _ = client.get_json(url)
        payload = json.loads(body)
        if not isinstance(payload, list):
            raise ValueError("GitHub tags response is not a list")
        if not payload:
            break
        tags.extend(item["name"] for item in payload if isinstance(item, dict) and isinstance(item.get("name"), str))
        if len(payload) < 100:
            break
        polite_pause(pause)
    else:
        raise RuntimeError("GitHub tag pagination exceeded safety bound")
    return discover_families_from_tags(tags)


def build_resource_url(family: str) -> str:
    baseline = baseline_for_family(family)
    # One request per family, containing exactly the two approved resource queries.
    query = urlencode([(MAIN_RESOURCE_TYPE, baseline), (PRINTER_RESOURCE_TYPE, baseline)])
    return f"{API_ENDPOINT}?{query}"


def parse_resources(payload: bytes | str, family: str) -> list[Resource]:
    data = json.loads(payload)
    if not isinstance(data, dict):
        raise ValueError("resource response is not an object")
    resources = data.get("resources")
    if resources is None:
        return []
    if not isinstance(resources, list):
        raise ValueError("resource response has a non-list resources field")
    accepted: list[Resource] = []
    for item in resources:
        if not isinstance(item, dict) or item.get("type") not in ALLOWED_RESOURCE_TYPES:
            continue
        version = item.get("version")
        url = item.get("url")
        if not isinstance(version, str) or not isinstance(url, str):
            raise ValueError("matching resource lacks version or URL")
        match = VERSION_RE.fullmatch(version)
        if not match or f"{match.group('major')}.{match.group('minor')}" != family:
            raise ValueError(f"resource {version} does not match requested family {family}")
        accepted.append(
            Resource(
                type=item["type"],
                version=version,
                url=url,
                description=item.get("description") if isinstance(item.get("description"), str) else "",
                force_update=item.get("force_update") is True,
            )
        )
    return accepted


def query_family(client: HttpClient, family: str) -> tuple[list[Resource], str]:
    url = build_resource_url(family)
    body, _ = client.get_json(url)
    return parse_resources(body, family), url

