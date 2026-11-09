"""Bounded authenticated schema probe; never publishes or follows redirects."""

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
from pathlib import Path
import socket
import ssl
from urllib.parse import quote, urlencode

from collector.exporters import safe_target, write_json
from collector.practice import public_addresses

HOST = "classification.psa.gov.ph"


def token_from_file(path):
    values = []
    for line in Path(path).read_text().splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and key.strip() == "PSA-TOKEN":
            values.append(value.strip().strip("\"'"))
    if len(values) != 1 or not values[0] or any(c.isspace() for c in values[0]):
        raise ValueError("Expected one non-empty PSA-TOKEN in credential file")
    return values[0]


def scrub(text, token):
    return text.replace(token, "[REDACTED]").replace(
        quote(token, safe=""), "[REDACTED]"
    )


def probe(target, token, page=1, page_size=1):
    target = safe_target(target)
    target.mkdir(parents=True, exist_ok=False)
    endpoint = "/psgc/Q2_2024/all"
    query = {"reg": "1", "prv": "55", "page_size": str(page_size), "page": str(page)}
    report = {
        "source_url": f"https://{HOST}{endpoint}?{urlencode(query)}",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "review_status": "pending",
        "coverage_status": "partial",
        "purpose": "authenticated_response_schema_probe",
        "auto_publish": False,
    }
    connection = http.client.HTTPSConnection(HOST, timeout=25)
    try:
        ip = public_addresses(HOST)[0]
        raw = socket.create_connection((ip, 443), timeout=25)
        connection.sock = ssl.create_default_context().wrap_socket(
            raw, server_hostname=HOST
        )
        if connection.sock.getpeername()[0] != ip:
            raise ValueError("peer_mismatch")
        connection.request(
            "GET",
            endpoint + "?" + urlencode({**query, "token": token}),
            headers={
                "Accept": "application/json",
                "User-Agent": "BetterPangasinan/0.1",
            },
        )
        response = connection.getresponse()
        body = response.read(2_000_001)
        if len(body) > 2_000_000:
            raise ValueError("response_too_large")
        report.update(
            status=response.status,
            content_type=response.getheader("Content-Type"),
            remote_ip=ip,
            response_sha256=hashlib.sha256(body).hexdigest(),
        )
        # Pagination and error responses may echo credentials; retain only sanitized evidence.
        clean = scrub(body.decode("utf-8"), token).encode()
        report["artifact_redacted"] = clean != body
        report["artifact_sha256"] = hashlib.sha256(clean).hexdigest()
        (target / "response.redacted.raw").write_bytes(clean)
    except Exception:
        report["error"] = "probe_failed_before_safe_completion"
    finally:
        connection.close()
        write_json(target / "manifest.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--authorize-live", action="store_true", required=True)
    args = parser.parse_args()
    result = probe(
        args.target, token_from_file(Path(__file__).resolve().parents[1] / ".env")
    )
    print({k: v for k, v in result.items() if k != "source_url"})
    raise SystemExit(0 if result.get("status") == 200 else 1)
