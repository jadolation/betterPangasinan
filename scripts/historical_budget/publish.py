"""Offline publication contract. Approval is bound to current local inputs only.

An intentionally explicit prototype-review command is available for the user-
authorized collected snapshot, never run by collection or production builds:
python3 -m scripts.historical_budget.publish --review-prototype
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .collect import ROOT, digest, save

YEARS = [str(y) for y in range(2020, 2027)]
ALLOWLIST = frozenset({"data/historical-budget/manifest.json", "data/historical-budget/departments.json",
                      "data/historical-budget/programs.json", "data/historical-budget/coverage.json",
                      "data/budget-context.json", "data/budget-hearings.json"})


def safe_values(value):
    """Retain exact source integers past JavaScript's safe integer boundary."""
    if isinstance(value, int) and not isinstance(value, bool) and abs(value) > 9007199254740991:
        return str(value)
    if isinstance(value, list):
        return [safe_values(v) for v in value]
    if isinstance(value, dict):
        return {k: safe_values(v) for k, v in value.items()}
    return value


def load_inputs(root):
    folder = Path(root) / "data/historical_budget/approved"
    files = {"collection.json": json.loads((folder / "collection.json").read_text())}
    for path in sorted((folder / "inputs").glob("*.json")):
        files["inputs/" + path.name] = json.loads(path.read_text())
    return folder, files


def review_prototype(root):
    folder, files = load_inputs(root)
    save(folder / "review.json", {"status": "approved", "authorization": "user-requested real-data prototype",
         "reviewed_at": datetime.now(timezone.utc).isoformat(), "geography_verified": False,
         "input_hashes": {name: digest(value) for name, value in files.items()},
         "scope": "Source-backed name matches and explicitly distinct context; not a location or hearing-approval verification"})


def publication_payload(root):
    """Return exactly six allowlisted JSON paths, or fail closed on stale review."""
    folder, files = load_inputs(root)
    review = json.loads((folder / "review.json").read_text())
    if (review.get("status") != "approved" or review.get("geography_verified") is not False
            or not review.get("reviewed_at") or not review.get("authorization")
            or review.get("input_hashes") != {n: digest(v) for n, v in files.items()}):
        raise ValueError("Missing or stale historical-budget review; refresh requires explicit local review")
    entries = {}
    for name, entry in files.items():
        if name == "collection.json":
            continue
        if (urlparse(entry["url"]).netloc != "budget.bettergov.ph"
                or entry["payload_sha256"] != digest(entry.get("data"))):
            raise ValueError("Invalid source provenance")
        entries[entry["url"]] = entry
    collection = files["collection.json"]
    department_source = entries[collection["departments_url"]]
    body = department_source["data"]
    if body["meta"]["currency"] != "PHP" or body["meta"]["scale"] != "pesos" or body["meta"]["years"] != list(range(2020, 2027)):
        raise ValueError("Unexpected GAA units or fiscal years")
    departments = body["data"]
    expected = {str(d["id"]) for d in departments}
    if len(expected) != len(departments) or len(departments) != body["meta"]["total_items"]:
        raise ValueError("Department discovery count mismatch")
    province = [q for q in collection["queries"] if q["query"] == "Pangasinan"]
    if {q["department_id"] for q in province} != expected or len(province) != len(expected):
        raise ValueError("Province must attempt every discovered department")
    by_key = {}
    coverage = []
    for query in collection["queries"]:
        matched = None
        keys = set()
        error = query["error"]
        previous_cursor = None
        for index, url in enumerate(query["pages"]):
            parsed = urlparse(url)
            params = parse_qs(parsed.query)
            if (parsed.path != f"/api/v1/gaa/departments/{query['department_id']}/programs"
                    or params.get("q") != [query["query"]]
                    or params.get("cursor", [None]) != [previous_cursor]):
                raise ValueError("Invalid cursor chain or query provenance")
            entry = entries[url]
            if "error" in entry:
                error = entry["error"]
                continue
            page = entry["data"]
            meta = page["meta"]
            if meta.get("scale") != "pesos" or meta.get("currency") != "PHP":
                raise ValueError("Unexpected program scale")
            if index == 0:
                matched = meta.get("matched")
            elif matched != meta.get("matched"):
                error = "Matched count changed during pagination"
            if "next_cursor" not in page:
                error = "Missing cursor field; exhaustion unproven"
            previous_cursor = page.get("next_cursor")
            for source in page["data"]:
                if str(source["department_id"]) != query["department_id"]:
                    raise ValueError("Family department mismatch")
                key = "gaa:" + query["department_id"] + ":" + source["fam_key"]
                keys.add(key)
                years = {}
                for year in YEARS:
                    value = source.get("years", {}).get(year)
                    amount = value.get("amount") if value else None
                    if amount is not None and (not isinstance(amount, int) or isinstance(amount, bool)):
                        raise ValueError("GAA amounts must be integer PHP or null")
                    years[year] = {"amount": amount, "count": value.get("count") if value else None}
                row = {"key": key, "department_id": query["department_id"], "fam_key": source["fam_key"],
                       "agency_id": source["agency_id"], "name": source["name"], "years": years,
                       "ids_count": source.get("ids_count"), "queries": [], "sources": [], "geography": "name_match_unverified"}
                if key in by_key:
                    old = by_key[key]
                    if any(old[k] != row[k] for k in ("years", "name", "agency_id", "ids_count")):
                        raise ValueError("Conflicting family across queries; explicit reconciliation required: " + key)
                    row = old
                if query["query"] not in row["queries"]:
                    row["queries"].append(query["query"])
                if url not in row["sources"]:
                    row["sources"].append(url)
                by_key[key] = row
        complete = bool(query["exhausted"] and not error and previous_cursor is None and matched == len(keys))
        coverage.append({**query, "matched": matched, "fetched": len(keys), "complete": complete, "error": error})
    sources = [{k: e.get(k) for k in ("url", "retrieved_at", "status", "raw_sha256", "payload_sha256", "error")} for e in entries.values()]
    contexts = {}
    for name, url in collection["contexts"].items():
        entry = entries[url]
        contexts[name] = {"source": url, "retrieved_at": entry["retrieved_at"], "status": entry["status"],
                          "error": entry.get("error"), "response": entry.get("data")}
    hearing = contexts.pop("hearings")
    contexts.pop("openapi")
    hearing_rows = (hearing.get("response") or {}).get("data", [])
    hearing["coverage"] = {"query": "Pangasinan", "returned": len(hearing_rows), "limit": 100,
                            "complete": not hearing["error"] and len(hearing_rows) < 100,
                            "pagination": "No documented cursor or offset; completeness only below documented cap"}
    manifest = {"schema_version": 1, "dataset": "gaa", "stage": "enacted_appropriations", "years": YEARS,
                "currency": "PHP", "scale": "pesos", "programs": len(by_key), "departments": len(departments),
                "review": review, "sources": sources, "source_commit": None,
                "source_commit_note": "GAA/NEP APIs do not expose a source commit; response checksums retained instead.",
                "limitations": collection["limitations"], "complete": all(q["complete"] for q in coverage)}
    payload = {"data/historical-budget/manifest.json": manifest,
               "data/historical-budget/departments.json": {"meta": body["meta"], "data": departments},
               "data/historical-budget/programs.json": {"years": YEARS, "data": sorted(by_key.values(), key=lambda r: r["key"])},
               "data/historical-budget/coverage.json": {"data": coverage, "limitations": collection["limitations"]},
               "data/budget-context.json": {"datasets": contexts, "notice": "NEP FY2027 is a proposal, not spending. Regional and national figures are not Pangasinan totals. Budget-cycle Current New Appropriations are a narrower scope; stages and fiscal years must remain distinct."},
               "data/budget-hearings.json": {**hearing, "notice": "Machine-transcript topic index, not approved funding. Speaker names and figures may be wrong. Verify timestamped video before quoting; a commitment is not an appropriation or evidence of approval."}}
    assert set(payload) == ALLOWLIST
    return safe_values(payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--review-prototype", action="store_true")
    parser.add_argument("--output", type=Path, help="Optional preview directory; production adapter owns integration")
    args = parser.parse_args()
    if args.review_prototype:
        review_prototype(args.root)
    payload = publication_payload(args.root)
    if args.output:
        for name, value in payload.items():
            save(args.output / name, value)
    print(json.dumps({"paths": sorted(payload), "programs": payload["data/historical-budget/manifest.json"]["programs"]}))


if __name__ == "__main__":
    main()
