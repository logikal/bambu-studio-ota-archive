from __future__ import annotations

import contextlib
import hashlib
import re
import tempfile
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Mapping
from urllib.parse import urlparse

from .constants import DEFAULT_USER_AGENT, MAX_ARCHIVE_BYTES


@dataclass(slots=True)
class Download:
    path: Path
    sha256: str
    md5: str
    size: int
    headers: dict[str, str]


class HttpClient:
    """Small, low-volume HTTP client with a transparent User-Agent."""

    def __init__(self, user_agent: str = DEFAULT_USER_AGENT, timeout: float = 45.0):
        self.user_agent = user_agent
        self.timeout = timeout

    def _request(self, url: str, *, method: str = "GET") -> urllib.request.Request:
        return urllib.request.Request(
            url,
            method=method,
            headers={"Accept": "application/json, application/zip;q=0.9, */*;q=0.1", "User-Agent": self.user_agent},
        )

    def get_json(self, url: str) -> tuple[bytes, Mapping[str, str]]:
        with urllib.request.urlopen(self._request(url), timeout=self.timeout) as response:
            return response.read(), response.headers

    def head(self, url: str) -> tuple[int, dict[str, str]]:
        try:
            with urllib.request.urlopen(self._request(url, method="HEAD"), timeout=self.timeout) as response:
                return response.status, _selected_headers(response.headers)
        except urllib.error.HTTPError as exc:
            return exc.code, _selected_headers(exc.headers)

    def download(self, url: str, destination_dir: Path, *, max_bytes: int = MAX_ARCHIVE_BYTES) -> Download:
        kind, version = validate_profile_cdn_url(url)
        profile_opener = urllib.request.build_opener(_ProfileRedirectHandler(version, kind))
        destination_dir.mkdir(parents=True, exist_ok=True)
        fd, raw_path = tempfile.mkstemp(prefix="bambu-ota-", suffix=".zip", dir=destination_dir)
        path = Path(raw_path)
        sha256 = hashlib.sha256()
        md5 = hashlib.md5(usedforsecurity=False)
        size = 0
        try:
            with contextlib.closing(open(fd, "wb", closefd=True)) as output:
                with profile_opener.open(self._request(url), timeout=self.timeout) as response:
                    validate_profile_cdn_url(
                        response.geturl(), expected_version=version, expected_kind=kind
                    )
                    headers = _selected_headers(response.headers)
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > max_bytes:
                        raise ValueError("archive exceeds configured download-size limit")
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("archive exceeds configured download-size limit")
                        sha256.update(chunk)
                        md5.update(chunk)
                        output.write(chunk)
            return Download(path, sha256.hexdigest(), md5.hexdigest(), size, headers)
        except Exception:
            path.unlink(missing_ok=True)
            raise


def _selected_headers(headers: Mapping[str, str]) -> dict[str, str]:
    wanted = {
        "last-modified",
        "etag",
        "content-length",
        "content-type",
        "x-amz-version-id",
        "x-oss-version-id",
        "x-bce-version-id",
        "x-goog-generation",
    }
    return {key.lower(): value for key, value in headers.items() if key.lower() in wanted}


def validate_profile_cdn_url(
    url: str, *, expected_version: str | None = None, expected_kind: str | None = None
) -> tuple[str, str]:
    parsed = urlparse(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname != "public-cdn.bblmw.com"
        or parsed.port is not None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"refusing non-approved CDN URL: {url}")
    parts = parsed.path.split("/")
    if len(parts) != 8 or parts[:3] != ["", "upgrade", "studio"]:
        raise ValueError(f"refusing non-profile CDN path: {url}")
    kind, vendor, version, object_component, filename = parts[3:]
    if kind not in {"settings", "printer"} or vendor != "BBL":
        raise ValueError(f"refusing installer, plugin, firmware, or non-BBL path: {url}")
    if expected_kind is not None and kind != expected_kind:
        raise ValueError(f"CDN path kind {kind!r} does not match resource kind {expected_kind!r}")
    if not re.fullmatch(r"\d{2}\.\d{2}\.\d{2}\.\d{2}", version):
        raise ValueError(f"invalid profile version path: {url}")
    if expected_version is not None and version != expected_version:
        raise ValueError(f"CDN path version {version!r} does not match resource {expected_version!r}")
    if filename != f"{version}.zip" or not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", object_component):
        raise ValueError(f"invalid profile archive path: {url}")
    return kind, version


class _ProfileRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, expected_version: str, expected_kind: str):
        super().__init__()
        self.expected_version = expected_version
        self.expected_kind = expected_kind

    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        validate_profile_cdn_url(
            newurl, expected_version=self.expected_version, expected_kind=self.expected_kind
        )
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def polite_pause(seconds: float = 0.2) -> None:
    if seconds > 0:
        time.sleep(seconds)
