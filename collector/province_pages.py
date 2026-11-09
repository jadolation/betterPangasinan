"""Bounded official provincial page acquisition for the research backlog."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from collector.exporters import safe_target, write_json
from collector.practice import AGENT, pinned_fetch
from scripts.provincial_reference import PublicHTML

ORIGIN = "https://www.pangasinan.gov.ph"
PAGES = {
    "about": "/the-province/about-pangasinan/",
    "lgus": "/city-municipalities/",
    "directory": "/directory/",
    "history": "/history/",
    "disaster-services": "/department/provincial-disaster-risk-reduction-and-management-office/services/",
    "board": "/positions/board-member/",
}


def collect(target, fetch=pinned_fetch, sleep=time.sleep):
    target = safe_target(target)
    target.mkdir(parents=True, exist_ok=False)
    report = dict(
        review_status="pending",
        auto_publish=False,
        coverage_status="partial",
        sources=[],
        artifacts=[],
    )

    def capture(url, name):
        response = fetch(url, target / name)
        body = response.pop("body")
        (target / (name + ".raw")).write_bytes(body)
        response.update(
            artifact=name + ".raw",
            sha256=hashlib.sha256(body).hexdigest(),
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
        report["artifacts"].append(response)
        return response, body

    try:
        robots, body = capture(ORIGIN + "/robots.txt", "robots")
        if (
            robots["status"] != 200
            or robots.get("error")
            or robots["headers"].get("cf-mitigated") == "challenge"
            or "text/plain" not in robots["headers"].get("content-type", "")
        ):
            raise ValueError("robots_unavailable")
        policy = RobotFileParser()
        policy.parse(body.decode().splitlines())
        delay = max(2, policy.crawl_delay(AGENT) or 0)
        if delay > 30:
            raise ValueError("crawl_delay_deferred")
        for name, path in PAGES.items():
            url = ORIGIN + path
            row = dict(id=name, source_url=url, status="not_collected")
            report["sources"].append(row)
            for hop in range(3):
                if not policy.can_fetch(AGENT, url):
                    row["status"] = "robots_denied"
                    break
                sleep(delay)
                response, body = capture(url, f"{name}-{hop}")
                if response.get("error"):
                    row["status"] = "network_error"
                    break
                if response["headers"].get("cf-mitigated") == "challenge":
                    row["status"] = "access_challenge"
                    break
                if response["status"] in (301, 302, 303, 307, 308):
                    new = urljoin(url, response["headers"].get("location", ""))
                    parsed = urlsplit(new)
                    if (
                        parsed.scheme != "https"
                        or parsed.netloc != "www.pangasinan.gov.ph"
                        or parsed.query
                        or parsed.fragment
                        or new == url
                    ):
                        row["status"] = "redirect_denied"
                        break
                    url = new
                    continue
                row["status"] = f"http_{response['status']}"
                if response["status"] == 200 and "text/html" in response["headers"].get(
                    "content-type", ""
                ):
                    parser = PublicHTML()
                    parser.feed(body.decode("utf-8"))
                    write_json(
                        target / (name + ".json"),
                        dict(
                            source_url=url,
                            evidence=response,
                            text=parser.text,
                            rows=parser.rows,
                            links=sorted(set(parser.links)),
                            review_status="pending",
                        ),
                    )
                    row.update(status="extracted_for_review", effective_url=url)
                break
            else:
                row["status"] = "redirect_limit"
    except (ValueError, OSError) as error:
        report["error"] = type(error).__name__
    finally:
        write_json(target / "manifest.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--authorize-live", action="store_true", required=True)
    args = parser.parse_args()
    result = collect(args.target)
    print(json.dumps(result["sources"]))
