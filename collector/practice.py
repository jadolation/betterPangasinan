"""Bounded P0 live smoke collection; leaves disabled PSGC and publication untouched."""

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from uuid import uuid4

from collector.exporters import safe_target, write_json
from collector.transport import load_source
from scripts.national_budget.collect import settings, strict_json
from scripts.provincial_reference import PAGES, PublicHTML

AGENT = "BetterPangasinan-practice/0.1 public-source-review"
HOSTS = {"psa.gov.ph", "www.pangasinan.gov.ph", "budget.bettergov.ph"}


def public_addresses(host, resolver=socket.getaddrinfo):
    addresses = {str(row[4][0]) for row in resolver(host, 443, type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip).is_global for ip in addresses):
        raise ValueError("Destination DNS must contain only public addresses")
    return sorted(addresses, key=lambda ip: (ipaddress.ip_address(ip).version, ip))


def pinned_fetch(url, target):
    parsed = urlsplit(url)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in HOSTS
        or parsed.port not in (None, 443)
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise ValueError("Practice destination is not allowlisted")
    host = parsed.hostname
    ip = public_addresses(host)[0]
    pinned = f"[{ip}]" if ":" in ip else ip
    body_path, headers_path = (
        target.with_suffix(".body"),
        target.with_suffix(".headers"),
    )
    try:
        result = subprocess.run(
            [
                "curl",
                "--disable",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--proto",
                "=https",
                "--resolve",
                f"{host}:443:{pinned}",
                "--connect-timeout",
                "10",
                "--max-time",
                "25",
                "--max-filesize",
                "2000000",
                "--max-redirs",
                "0",
                "--user-agent",
                AGENT,
                "--dump-header",
                str(headers_path),
                "--output",
                str(body_path),
                "--write-out",
                "%{json}",
                url,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        metadata = json.loads(result.stdout) if result.stdout else {}
        peer = metadata.get("remote_ip")
        if peer and ipaddress.ip_address(peer) != ipaddress.ip_address(ip):
            raise ValueError(
                "Actual connection destination differs from pinned public IP"
            )
        headers = {}
        for line in (
            headers_path.read_text(errors="replace").splitlines()
            if headers_path.exists()
            else []
        ):
            if ":" in line:
                name, value = line.split(":", 1)
                if name.lower() in {
                    "content-type",
                    "location",
                    "retry-after",
                    "cf-mitigated",
                    "etag",
                    "last-modified",
                    "date",
                }:
                    headers[name.lower()] = value.strip()
        return {
            "url": url,
            "status": metadata.get("http_code", 0),
            "headers": headers,
            "remote_ip": peer,
            "pinned_ip": ip,
            "body": body_path.read_bytes() if body_path.exists() else b"",
            "error": f"CURL_{result.returncode}: {result.stderr.strip()}"
            if result.returncode
            else None,
        }
    finally:
        # Response cookies are not needed as evidence; retain only allowlisted headers.
        headers_path.unlink(missing_ok=True)
        body_path.unlink(missing_ok=True)


def practice(target, *, authorized=False, fetch=pinned_fetch, sleep=time.sleep):
    if not authorized:
        raise ValueError("Explicit live practice authorization required")
    target = safe_target(target)
    target.mkdir(parents=True, exist_ok=True)
    if any(target.iterdir()):
        raise ValueError("Practice output must be a fresh directory")
    registry = load_source("psa_psgc")
    budget = settings()
    plan = [
        ("psa_psgc", "https://psa.gov.ph/classification/psgc"),
        ("province_about", PAGES["about"]),
        ("budget_overview", budget["api_base"]),
    ]
    report = {
        "run_id": str(uuid4()),
        "started_at": datetime.now(timezone.utc).isoformat(),
        "is_mock": False,
        "auto_publish": False,
        "coverage_status": "partial",
        "review_status": "pending",
        "scope": "Three P0 sources only; one page per enabled source; no crawling or publication",
        "configuration": {"psa_psgc": registry.model_dump(), "national_budget": budget},
        "requests": 0,
        "sources": [],
        "artifacts": [],
    }

    def request(url, name):
        report["requests"] += 1
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            response = fetch(url, target / name)
        except (OSError, ValueError, subprocess.TimeoutExpired) as error:
            response = {
                "url": url,
                "status": 0,
                "headers": {},
                "body": b"",
                "error": str(error),
            }
        body = response.pop("body")
        checksum = hashlib.sha256(body).hexdigest()
        path = target / (name + ".raw")
        path.write_bytes(body)
        evidence = {
            **response,
            "retrieved_at": stamp,
            "sha256": checksum,
            "bytes": len(body),
            "artifact": path.name,
            "license_status": "pending",
            "review_status": "pending",
        }
        report["artifacts"].append(evidence)
        return evidence, body

    def failure(evidence):
        if evidence["error"]:
            return "network_error"
        if evidence["headers"].get("cf-mitigated") == "challenge":
            return "access_challenge"
        if evidence["status"] != 200:
            return f"http_{evidence['status']}"
        return None

    for source_id, url in plan:
        row = {
            "source_id": source_id,
            "source_url": url,
            "review_status": "pending",
            "redistribution_review": "pending",
            "is_mock": False,
        }
        report["sources"].append(row)
        origin = "https://" + urlsplit(url).netloc
        robots, body = request(origin + "/robots.txt", source_id + "-robots")
        row["robots_artifact"] = robots["artifact"]
        if source_id == "psa_psgc":
            row.update(
                status="disabled_in_current_configuration",
                reason="No approved endpoint, official mapping or access review; configuration preserved",
                robots_observation=failure(robots),
            )
            continue
        issue = failure(robots)
        if issue:
            row["status"] = "robots_unavailable" if issue.startswith("http_") else issue
            continue
        if "text/plain" not in robots["headers"].get("content-type", "").lower():
            row["status"] = "robots_unrecognized_content"
            continue
        rules = RobotFileParser()
        rules.parse(body.decode("utf-8", errors="replace").splitlines())
        if not rules.can_fetch(AGENT, url):
            row["status"] = "robots_denied"
            continue
        delay = max(2, rules.crawl_delay(AGENT) or 0)
        if delay > 60:
            row["status"] = "robots_delay_deferred"
            continue
        sleep(delay)
        evidence, body = request(url, source_id + "-page")
        if evidence["status"] in (301, 302, 303, 307, 308):
            destination = urljoin(url, evidence["headers"].get("location", ""))
            expected = "https://www.pangasinan.gov.ph/the-province/about-pangasinan/"
            if (
                source_id != "province_about"
                or destination != expected
                or not rules.can_fetch(AGENT, destination)
            ):
                row["status"] = "redirect_denied"
                continue
            sleep(delay)
            evidence, body = request(destination, source_id + "-canonical")
            row["effective_url"] = destination
        row["page_artifact"] = evidence["artifact"]
        issue = failure(evidence)
        if issue:
            row["status"] = issue
            continue
        try:
            if source_id == "budget_overview":
                parsed = strict_json(body)
                if (
                    not isinstance(parsed, dict)
                    or not isinstance(parsed.get("meta"), dict)
                    or not isinstance(parsed.get("data"), dict)
                ):
                    raise ValueError("Budget API envelope changed")
                write_json(target / (source_id + "-extracted.json"), parsed)
                row["dataset_count"] = len(parsed["data"].get("datasets", []))
            else:
                if "text/html" not in evidence["headers"].get("content-type", ""):
                    raise ValueError("Expected provincial HTML")
                parser = PublicHTML()
                parser.feed(body.decode("utf-8"))
                if not parser.text:
                    raise ValueError("No provincial text extracted")
                write_json(
                    target / (source_id + "-extracted.json"),
                    {
                        "source_url": url,
                        "retrieved_at": evidence["retrieved_at"],
                        "artifact_sha256": evidence["sha256"],
                        "review_status": "pending",
                        "is_mock": False,
                        "text": parser.text,
                        "rows": parser.rows,
                        "links": sorted(set(parser.links)),
                    },
                )
                row["text_fragments"] = len(parser.text)
            row["status"] = "collected_for_review"
        except (ValueError, UnicodeError) as error:
            row.update(status="extraction_failed", error=str(error))
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["files"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.iterdir()
        if p.is_file()
    }
    write_json(target / "manifest.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--authorize-live-practice", action="store_true")
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    result = practice(args.target, authorized=args.authorize_live_practice)
    print(json.dumps(result, sort_keys=True))
    return int(
        any(
            r["status"] != "collected_for_review"
            for r in result["sources"]
            if r["source_id"] != "psa_psgc"
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
