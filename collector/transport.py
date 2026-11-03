"""Deny-by-default source registry, bounded fixture parsing and HTTP test harness.

Live sockets remain disabled until deployment-level destination enforcement exists.
Injected HTTPX transports are for isolated contract tests, never a live-mode escape.
"""

from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from io import BytesIO
import ipaddress
from pathlib import Path
import re
import random
import socket
import time
from typing import Literal
from urllib.parse import unquote, urljoin, urlsplit
from xml.parsers import expat
import zipfile

import httpx
from pydantic import BaseModel, ConfigDict, Field
import yaml

ROOT = Path(__file__).resolve().parents[1]


class SourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    source_id: str = Field(pattern=r"^[a-z][a-z0-9_]+$")
    agency: str
    enabled: bool = False
    access_review: Literal["pending", "approved", "denied"] = "pending"
    redistribution_review: Literal["pending", "approved", "restricted", "denied"] = (
        "pending"
    )
    start_url: str | None = None
    allowed_hosts: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    format: Literal["xlsx"] = "xlsx"
    mapping_version: Literal["synthetic_psgc_v1"] = "synthetic_psgc_v1"
    timeout_seconds: int = Field(default=30, ge=1, le=120)
    retries: int = Field(default=3, ge=0, le=3)
    download_delay_seconds: int = Field(default=2, ge=1, le=60)
    max_download_bytes: int = Field(default=25_000_000, ge=1, le=25_000_000)
    source_title: str = "PSGC source pending release review"
    source_published_at: str | None = None
    reference_period: str | None = None
    release: str | None = None
    last_reviewed_at: str | None = None
    license_evidence: str | None = None
    auto_publish: Literal[False] = False
    requires_human_review: Literal[True] = True


def load_source(source_id: str, directory: Path | None = None) -> SourceConfig:
    if not re.fullmatch(r"[a-z][a-z0-9_]+", source_id):
        raise ValueError("Invalid source identifier")
    path = (directory or ROOT / "config/sources") / f"{source_id}.yaml"
    if path.stat().st_size > 100_000:
        raise ValueError("Source config size limit")
    source = SourceConfig.model_validate(yaml.safe_load(path.read_text()))
    if source.source_id != source_id:
        raise ValueError("Source identifier disagrees with registry filename")
    return source


def resolve(host: str) -> list[str]:
    return sorted(
        {
            str(entry[4][0])
            for entry in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
        }
    )


def validate_url(source: SourceConfig, url: str, resolver=resolve) -> list[str]:
    parsed = urlsplit(url)
    decoded = unquote(parsed.path)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in source.allowed_hosts
        or parsed.username
        or parsed.password
        or parsed.port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or "\\" in url
        or "%" in decoded
        or any(part in (".", "..") for part in decoded.split("/"))
        or decoded != parsed.path
        or not any(
            decoded.startswith(path) and path.startswith("/") and path.endswith("/")
            for path in source.allowed_paths
        )
    ):
        raise ValueError("URL_POLICY: destination is not approved")
    addresses = resolver(parsed.hostname)
    if not addresses or any(
        not ipaddress.ip_address(address).is_global for address in addresses
    ):
        raise ValueError("DNS_POLICY: destination is not public")
    return addresses


def inspect_xlsx(body: bytes, max_bytes: int = 25_000_000) -> None:
    if len(body) > max_bytes:
        raise ValueError("XLSX size limit")
    if not body.startswith(b"PK\x03\x04"):
        raise ValueError("XLSX_SIGNATURE: expected ZIP workbook")
    try:
        with zipfile.ZipFile(BytesIO(body)) as archive:
            entries = archive.infolist()
            names = [entry.filename for entry in entries]
            if len(entries) > 1000 or len(set(names)) != len(names):
                raise ValueError("XLSX entries limit or duplicate member")
            if not {"[Content_Types].xml", "xl/workbook.xml"}.issubset(names):
                raise ValueError("XLSX required members missing")
            if sum(entry.file_size for entry in entries) > 50_000_000:
                raise ValueError("XLSX expanded size limit")
            for entry in entries:
                name = entry.filename.lower()
                if (
                    entry.flag_bits & 1
                    or entry.file_size > 10_000_000
                    or entry.file_size > max(1, entry.compress_size) * 200
                    or name.startswith("/")
                    or ".." in name.split("/")
                    or "vbaproject" in name
                    or "externallinks/" in name
                    or name.endswith((".exe", ".bin"))
                ):
                    raise ValueError("XLSX unsafe archive member")
                if name.endswith((".xml", ".rels")):
                    parser = expat.ParserCreate()
                    parser.StartDoctypeDeclHandler = reject_xml_declaration
                    parser.EntityDeclHandler = reject_xml_declaration
                    parser.ExternalEntityRefHandler = reject_xml_declaration
                    parser.StartElementHandler = check_xml_attributes
                    try:
                        parser.Parse(archive.read(entry), True)
                    except expat.ExpatError as exc:
                        raise ValueError("XLSX malformed XML") from exc
    except (zipfile.BadZipFile, RuntimeError, OSError) as exc:
        raise ValueError("XLSX malformed archive") from exc


def reject_xml_declaration(*args):
    raise ValueError("XLSX unsafe XML declaration")


def check_xml_attributes(name: str, attributes: dict[str, str]) -> None:
    if any(
        key.lower() == "targetmode" and value.lower() == "external"
        for key, value in attributes.items()
    ):
        raise ValueError("XLSX unsafe XML external relationship")


@dataclass(frozen=True)
class Download:
    body: bytes
    url: str
    headers: dict
    attempts: list[dict]


def retry_delay(source: SourceConfig, header: str, attempt: int, now, jitter) -> float:
    delay = max(source.download_delay_seconds, 2**attempt) + min(
        1.0, max(0.0, jitter())
    )
    if header:
        try:
            if header.strip().isdigit():
                requested = float(header)
            else:
                date = parsedate_to_datetime(header)
                if date.tzinfo is None:
                    raise ValueError("Retry-After date lacks a timezone")
                requested = max(0.0, date.timestamp() - now())
        except (ValueError, TypeError, OverflowError):
            raise ValueError("RATE_LIMIT_DEFERRED: invalid Retry-After") from None
        if requested > 60:
            raise ValueError(
                "RATE_LIMIT_DEFERRED: Retry-After exceeds worker wait limit"
            )
        delay = max(source.download_delay_seconds, requested)
    return min(60.0, delay)


def download(
    source: SourceConfig,
    *,
    authorized: bool = False,
    transport=None,
    resolver=resolve,
    sleep=time.sleep,
    now=time.time,
    jitter=random.random,
) -> Download:
    if (
        not authorized
        or not source.enabled
        or source.access_review != "approved"
        or not source.start_url
    ):
        raise ValueError("LIVE_DENIED: source disabled, unreviewed or unauthorized")
    if not isinstance(transport, httpx.MockTransport):
        raise ValueError(
            "LIVE_DENIED: deployment network isolation and connection pinning not configured"
        )
    attempts = []
    url = source.start_url
    redirects = 0
    with httpx.Client(
        transport=transport,
        follow_redirects=False,
        timeout=source.timeout_seconds,
        trust_env=False,
        headers={"User-Agent": "BetterPangasinan/0.1 source-review"},
    ) as client:
        for attempt in range(source.retries + 1):
            validate_url(source, url, resolver)
            try:
                with client.stream("GET", url) as response:
                    attempts.append(
                        {
                            "attempt": attempt + 1,
                            "url": url,
                            "status": response.status_code,
                        }
                    )
                    if response.is_redirect:
                        redirects += 1
                        if redirects > 3:
                            raise ValueError("REDIRECT_LIMIT")
                        url = urljoin(url, response.headers.get("location", ""))
                        validate_url(source, url, resolver)
                        if attempt == source.retries:
                            raise ValueError("REDIRECT_LIMIT")
                        continue
                    if response.status_code != 200:
                        if (
                            response.status_code not in (429, 500, 502, 503, 504)
                            or attempt == source.retries
                        ):
                            raise ValueError(
                                f"HTTP_{response.status_code}; attempts={len(attempts)}"
                            )
                        sleep(
                            retry_delay(
                                source,
                                response.headers.get("retry-after", ""),
                                attempt,
                                now,
                                jitter,
                            )
                        )
                        continue
                    kind = (
                        response.headers.get("content-type", "")
                        .split(";")[0]
                        .strip()
                        .lower()
                    )
                    if kind not in (
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        "application/octet-stream",
                    ):
                        raise ValueError("CONTENT_TYPE: expected XLSX")
                    chunks, length = [], 0
                    for chunk in response.iter_bytes():
                        length += len(chunk)
                        if length > source.max_download_bytes:
                            raise ValueError("DOWNLOAD_SIZE_LIMIT")
                        chunks.append(chunk)
                    body = b"".join(chunks)
                    inspect_xlsx(body, source.max_download_bytes)
                    return Download(body, url, dict(response.headers), attempts)
            except httpx.TimeoutException as exc:
                attempts.append(
                    {"attempt": attempt + 1, "url": url, "error": "TIMEOUT"}
                )
                if attempt == source.retries:
                    raise ValueError(f"TIMEOUT; attempts={len(attempts)}") from exc
                sleep(retry_delay(source, "", attempt, now, jitter))
            except httpx.HTTPError as exc:
                raise ValueError(f"NETWORK_ERROR; attempts={len(attempts)}") from exc
    raise ValueError("DOWNLOAD_FAILED")
