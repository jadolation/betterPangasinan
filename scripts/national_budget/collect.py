"""Internal, snapshot-bound FY2027 API collection. Never approves publication."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
from pathlib import Path
import re
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


BASE = "https://budget.bettergov.ph/api/v1/hgab/2027"
HOSTS = {"budget.bettergov.ph"}
DATASETS = ("dpwh", "fmr", "hfep", "nia")
CONFIG = Path(__file__).resolve().parents[2] / "data" / "national_budget" / "config.json"


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def check_url(url):
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or parsed.hostname not in HOSTS
            or parsed.port not in (None, 443) or parsed.username or parsed.password):
        raise ValueError("Untrusted API URL: " + url)
    return url


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def transport(url, timeout):
    """Return HTTP errors as responses so their original bodies are retained."""
    opener = build_opener(SafeRedirect())
    try:
        response = opener.open(Request(check_url(url), headers={
            "Accept": "application/json", "User-Agent": "BetterPangasinan-budget-collector/1"
        }), timeout=timeout)
    except HTTPError as exc:
        response = exc
    with response:
        return response.status, dict(response.headers), response.read()


class CollectionError(ValueError):
    pass


def strict_json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise CollectionError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda value: (_ for _ in ()).throw(
                           CollectionError("Nonfinite JSON: " + value)))


def settings(path=None):
    value = strict_json(Path(path or CONFIG).read_bytes())
    if (value.get("api_base") != BASE or value.get("allowed_api_hosts") != sorted(HOSTS)
            or value.get("fiscal_year") != 2027 or value.get("datasets") != list(DATASETS)):
        raise CollectionError("Configuration cannot change trusted API, year or programs")
    for key, minimum, maximum in (("page_size", 1, 200), ("timeout_seconds", 20, 30),
                                  ("attempts", 1, 5), ("lgu_batch_limit", 1, 10)):
        if type(value.get(key)) is not int or not minimum <= value[key] <= maximum:
            raise CollectionError("Invalid bounded configuration: " + key)
    for key in ("province_query", "regression_query"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            raise CollectionError("Missing configured search query")
    return value


class Client:
    def __init__(self, output, transport=transport, sleep=time.sleep, attempts=None, config=None):
        self.config = settings(config)
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        (self.output / "responses").mkdir(exist_ok=True)
        self.transport, self.sleep = transport, sleep
        self.attempts = self.config["attempts"] if attempts is None else attempts
        self.requests = []
        self.snapshot = None
        self.cache = {}
        self.previous = None
        previous = self.output / "manifest.json"
        if previous.exists():
            old = strict_json(previous.read_bytes())
            self.previous = old
            self.snapshot = old.get("snapshot")
            self.requests = old.get("requests", [])
            retained = {digest for query in old.get("queries", [])
                        if query.get("complete") and not query.get("error")
                        for digest in query.get("response_ids", [])}
            retained.update(item["response_id"] for field in ("details", "district_details")
                            for item in old.get(field, []))
            for entry in self.requests:
                if entry.get("valid") and entry.get("status") == 200 and entry.get("sha256") in retained:
                    self.cache[entry["url"]] = entry["sha256"]
        self.records = {}
        for query in (self.previous or {}).get("queries", []):
            if query.get("dataset") in DATASETS:
                for row in query.get("rows", []):
                    key = (query["dataset"], row["id"])
                    if key in self.records and self.records[key] != row:
                        raise CollectionError("Conflicting retained record: " + row["id"])
                    self.records[key] = row

    def envelope(self, raw):
        try:
            env = strict_json(raw)
        except (ValueError, UnicodeError) as exc:
            raise CollectionError("Invalid JSON: " + str(exc)) from exc
        if not isinstance(env, dict) or not isinstance(env.get("meta"), dict):
            raise CollectionError("Missing metadata envelope")
        meta = env["meta"]
        required = ("dataset", "fiscal_year", "currency", "scale", "source_repo",
                    "source_commit", "built_at", "notice")
        if any(key not in meta or meta[key] in (None, "") for key in required):
            raise CollectionError("Missing required metadata")
        if any(not isinstance(meta[key], str) for key in required if key != "fiscal_year"):
            raise CollectionError("Invalid metadata types")
        try:
            built = datetime.fromisoformat(meta["built_at"].replace("Z", "+00:00"))
            if built.tzinfo is None:
                raise ValueError("Missing build timezone")
        except ValueError as exc:
            raise CollectionError("Invalid build timestamp") from exc
        if (meta["dataset"] != "hgab" or meta["fiscal_year"] != 2027
                or meta["currency"] != "PHP" or meta["scale"] != "pesos"):
            raise CollectionError("Unexpected dataset/year/currency/scale")
        if not isinstance(env.get("data"), dict) or not isinstance(env.get("disclaimers"), list):
            raise CollectionError("Missing data/disclaimers envelope")
        snapshot = {"source_commit": meta["source_commit"], "built_at": meta["built_at"]}
        if self.snapshot is not None and snapshot != self.snapshot:
            raise CollectionError("Source snapshot changed; use a new output batch")
        self.snapshot = snapshot
        return env

    def get(self, path="", params=None, fresh=False):
        url = check_url(BASE + path + (("?" + urlencode(params)) if params else ""))
        if not fresh and url in self.cache:
            digest = self.cache[url]
            raw = (self.output / "responses" / (digest + ".json")).read_bytes()
            if hashlib.sha256(raw).hexdigest() != digest:
                raise CollectionError("Cached response checksum mismatch")
            return self.envelope(raw), digest
        for attempt in range(self.attempts):
            entry = {"url": url, "retrieved_at": utcnow(), "attempt": attempt + 1,
                     "status": None, "sha256": None, "error": None, "valid": False}
            self.requests.append(entry)
            headers = {}
            try:
                status, headers, raw = self.transport(url, self.config["timeout_seconds"])
                entry["status"] = status
                digest = hashlib.sha256(raw).hexdigest()
                entry["sha256"] = digest
                (self.output / "responses" / (digest + ".json")).write_bytes(raw)
                if status != 200:
                    raise CollectionError("HTTP " + str(status))
                env = self.envelope(raw)
                entry["meta"] = env["meta"]
                entry["disclaimers"] = env["disclaimers"]
                entry["valid"] = True
                self.cache[url] = digest
                return env, digest
            except (ValueError, URLError, TimeoutError, socket.timeout, OSError) as exc:
                entry["error"] = str(exc)
                retry = entry["status"] in (None, 429, 500, 502, 503, 504)
                if not retry or attempt + 1 == self.attempts:
                    raise CollectionError(str(exc)) from exc
                delay = 2 ** attempt
                retry_after = next((v for k, v in headers.items() if k.lower() == "retry-after"), None)
                if retry_after is not None:
                    try:
                        delay = max(delay, float(retry_after))
                    except ValueError:
                        try:
                            delay = max(delay, (parsedate_to_datetime(retry_after)
                                                - datetime.now(timezone.utc)).total_seconds())
                        except (ValueError, TypeError):
                            pass
                if delay > 120:
                    raise CollectionError("Retry-After exceeds bounded wait; resume later") from exc
                entry["retry_delay_seconds"] = delay
                self.sleep(delay)


def integer(value):
    return type(value) is int and value >= 0


def reconcile(rows, sums):
    if not isinstance(sums, dict) or not any(key.endswith("_php") for key in sums):
        raise CollectionError("Missing whole-query sums")
    calculated = {}
    for key, expected in sums.items():
        if not key.endswith("_php"):
            continue
        values = [row.get(key) for row in rows if row.get(key) is not None]
        if any(type(value) is not int for value in values):
            raise CollectionError("Noninteger monetary amount: " + key)
        actual = sum(values) if values else None
        if expected != actual or (expected is not None and type(expected) is not int):
            raise CollectionError("Whole-query sum mismatch: " + key)
        calculated[key] = actual
    for version, expected in sums.get("rows_with_amount", {}).items():
        if expected != sum(row.get(version + "_php") is not None for row in rows):
            raise CollectionError("Known-amount row count mismatch: " + version)
    return calculated


def paginate(client, category, dataset, params=None):
    query = {"category": category, "dataset": dataset, "params": params or {},
             "complete": False, "total": None, "downloaded": 0, "unique": 0,
             "rows": [], "response_ids": [], "error": None, "meta": None,
             "disclaimers": [], "sums": None}
    directory = category == "districts"
    path = "/districts" if directory else "/datasets/" + dataset + "/projects"
    offset, seen, sums = 0, set(), None
    try:
        while True:
            env, digest = client.get(path, {**query["params"], "limit": client.config["page_size"], "offset": offset})
            query["response_ids"].append(digest)
            meta, data = env["meta"], env["data"]
            rows = data.get("districts" if directory else "rows")
            total = data.get("total")
            if not isinstance(rows, list) or not integer(total):
                raise CollectionError("Invalid rows/total")
            if (any(not integer(meta.get(key)) for key in ("total", "returned", "offset"))
                    or meta["total"] != total or meta["returned"] != len(rows) or meta["offset"] != offset):
                raise CollectionError("Metadata pagination mismatch")
            if len(rows) > client.config["page_size"] or (not rows and total != 0):
                raise CollectionError("Invalid returned page size")
            if query["total"] is None:
                query.update(total=total, meta=meta, disclaimers=env["disclaimers"])
                sums = data.get("sums")
                query["sums"] = sums
            elif total != query["total"] or (not directory and data.get("sums") != sums):
                raise CollectionError("Query total/sums changed")
            if not directory:
                if meta.get("dataset_key") != dataset or meta.get("house_stage") != ("hgab3" if dataset == "dpwh" else "hgab2"):
                    raise CollectionError("Unexpected program/House stage")
            for row in rows:
                if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
                    raise CollectionError("Missing row identity")
                identity = row["id"]
                if identity in seen:
                    raise CollectionError("Duplicate row ID: " + identity)
                seen.add(identity)
                key = (dataset, identity)
                if not directory and key in client.records and client.records[key] != row:
                    raise CollectionError("Conflicting record across queries: " + identity)
                if not directory:
                    client.records[key] = row
                query["rows"].append(row)
            query["downloaded"] = len(query["rows"])
            query["unique"] = len(seen)
            if "next_offset" not in data:
                raise CollectionError("Missing next_offset")
            next_offset = data["next_offset"]
            if next_offset is None:
                if len(seen) != total:
                    raise CollectionError("Incomplete final coverage")
                break
            if not integer(next_offset) or next_offset != offset + len(rows) or next_offset <= offset or next_offset >= total:
                raise CollectionError("Invalid/nonadvancing next_offset")
            offset = next_offset
        if not directory:
            query["reconciled_sums"] = reconcile(query["rows"], sums)
        query["complete"] = True
    except (CollectionError, OSError, ValueError) as exc:
        query["error"] = str(exc)
    query["downloaded"] = len(query["rows"])
    query["unique"] = len(seen)
    return query


def collect(output, offices=False, details=False, registry=None, lgu_offset=0, lgu_limit=None,
            transport=transport, sleep=time.sleep, config=None, detail_limit=10, detail_ids=None, detail_workers=1):
    client = Client(output, transport=transport, sleep=sleep, config=config)
    if type(detail_limit) is not int or not 1 <= detail_limit <= 50:
        raise CollectionError("Detail batches require a limit of 1..50")
    if type(detail_workers) is not int or not 1 <= detail_workers <= 3:
        raise CollectionError("Detail concurrency must be 1..3")
    lgu_limit = client.config["lgu_batch_limit"] if lgu_limit is None else lgu_limit
    manifest = {"batch_id": Path(output).name, "started_at": utcnow(), "complete": False,
                "snapshot": client.snapshot, "overview": None, "queries": [], "offices": [],
                "district_details": [], "details": [], "errors": [], "requests": client.requests,
                "configuration": client.config, "run_complete": False}
    if client.previous:
        manifest.update(deepcopy(client.previous))
        manifest.update(complete=False, requests=client.requests, configuration=client.config, run_complete=False)
    failures = manifest.setdefault("failures", {})
    # Older manifests have no operation keys; retain their unscoped errors conservatively.
    legacy_errors = manifest.get("errors", []) if "failures" not in (client.previous or {}) else []
    scope = "discovery"

    def query_key(query):
        return (query["category"], query["dataset"], json.dumps(query["params"], sort_keys=True))

    def merge_query(query):
        for index, previous in enumerate(manifest["queries"]):
            if query_key(previous) != query_key(query):
                continue
            if previous.get("lgu_psgc") and query.get("lgu_psgc") != previous["lgu_psgc"]:
                query.update(complete=False, error="Conflicting query LGU association")
            old_rows = {row["id"]: row for row in previous["rows"]}
            if any(row["id"] in old_rows and old_rows[row["id"]] != row for row in query["rows"]):
                query.update(complete=False, error="Conflicting retained query rows")
            if query["complete"] and not old_rows.keys() <= {row["id"] for row in query["rows"]}:
                query.update(complete=False, error="Retained query rows missing from rerun")
            if not query["complete"] or query.get("error"):
                # Keep successful evidence and associations, but never hide the failed rerun.
                retained = deepcopy(previous)
                retained.update(complete=False, error=query["error"], failed_attempt=query)
                manifest["queries"][index] = retained
            else:
                manifest["queries"][index] = query
            return
        manifest["queries"].append(query)

    def merge_record(field, record, identity):
        for previous in manifest[field]:
            if identity(previous) == identity(record):
                if previous != record:
                    raise CollectionError("Conflicting retained " + field + " record")
                return
        manifest[field].append(record)

    def save():
        manifest["errors"] = list(dict.fromkeys([*legacy_errors, *failures.values()]))
        manifest["complete"] = (manifest["run_complete"] and not manifest["errors"] and bool(manifest["queries"])
                                and all(query["complete"] and not query.get("error")
                                        for query in manifest["queries"]))
        manifest["snapshot"] = client.snapshot
        manifest["finished_at"] = utcnow()
        manifest["retrieved_at"] = manifest["finished_at"]
        target = Path(output) / "manifest.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
        temporary.replace(target)
    anchor_start = len(client.requests)
    try:
        # A failed live anchor must not replace any previously persisted evidence.
        manifest["overview"], manifest["overview_response_id"] = client.get(fresh=True)
    except (CollectionError, OSError, ValueError, KeyError, TypeError) as exc:
        manifest["complete"] = False
        manifest["errors"] = list(dict.fromkeys([*manifest.get("errors", []), str(exc)]))
        if client.previous:
            with (Path(output) / "failed-attempts.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"failed_at": utcnow(), "operation": "anchor", "error": str(exc),
                                      "requests": client.requests[anchor_start:]}) + "\n")
        else:
            failures["anchor"] = str(exc)
            save()
        return manifest
    failures.pop("anchor", None)
    try:
        directory = paginate(client, "districts", None)
        merge_query(directory)
        save()
        if not directory["complete"]:
            raise CollectionError("District discovery incomplete")
        discovered = {office["id"]: office for office in manifest["offices"]}
        for district in directory["rows"]:
            if district.get("jurisdiction") != "Pangasinan":
                continue
            scope = "district:" + district["id"]
            env, digest = client.get("/districts/" + quote(district["id"], safe=""), fresh=scope in failures)
            if env["data"].get("id") != district["id"]:
                raise CollectionError("District detail identity mismatch")
            for office in env["data"].get("offices", []):
                labels = {year["matched_label"] for year in office.get("years", [])
                          if year.get("fy") == 2027 and year.get("stage") == "hgab3"
                          and year.get("matched_label")}
                if len(labels) != 1:
                    raise CollectionError("Missing/ambiguous FY2027 published office label")
                record = {"id": office["id"], "name": office["name"],
                          "matched_label": labels.pop(), "district_ids": office["district_ids"],
                          "tier": office["tier"], "upstream": office}
                if record["id"] in discovered:
                    previous = discovered[record["id"]]
                    # This one field is relative to the district being viewed.
                    old = {k: v for k, v in previous["upstream"].items() if k != "co_served_districts"}
                    new = {k: v for k, v in office.items() if k != "co_served_districts"}
                    if old != new:
                        raise CollectionError("Inconsistent shared office detail")
                else:
                    discovered[record["id"]] = record
                    manifest["offices"].append(record)
            merge_record("district_details", {"response_id": digest, "envelope": env},
                         lambda item: item["envelope"]["data"]["id"])
            failures.pop(scope, None)
        manifest["offices"] = list(discovered.values())
        failures.pop("discovery", None)
        scope = "collection"
        for dataset in DATASETS:
            merge_query(paginate(client, "province", dataset, {"q": client.config["province_query"]}))
            save()
        merge_query(paginate(client, "regression", "dpwh", {"q": client.config["regression_query"]}))
        if offices:
            for office in manifest["offices"]:
                merge_query(paginate(client, "office", "dpwh", {"office": office["matched_label"]}))
                save()
        if registry:
            scope = "registry:" + json.dumps([str(registry), lgu_offset, lgu_limit])
            reviewed = strict_json(Path(registry).read_bytes())
            if (not isinstance(reviewed, dict) or reviewed.get("review_status") != "approved"
                    or not isinstance(reviewed.get("reviewer"), str) or not reviewed["reviewer"].strip()
                    or not isinstance(reviewed.get("reviewed_at"), str)
                    or not isinstance(reviewed.get("lgus"), list) or not all(isinstance(lgu, dict) for lgu in reviewed["lgus"])
                    or not isinstance(reviewed.get("release"), str) or not reviewed["release"].strip()
                    or not isinstance(reviewed.get("source_url"), str)):
                raise CollectionError("LGU registry requires explicit human review metadata")
            stamp = datetime.fromisoformat(reviewed["reviewed_at"].replace("Z", "+00:00"))
            source = urlsplit(reviewed.get("source_url", ""))
            if (not reviewed["reviewed_at"].endswith("Z") or stamp > datetime.now(timezone.utc)
                    or source.scheme != "https" or source.hostname not in ("psa.gov.ph", "www.psa.gov.ph")
                    or source.port not in (None, 443) or source.username or source.password):
                raise CollectionError("Reviewed registry needs a dated PSA release source")
            registry_codes = [lgu.get("psgc") for lgu in reviewed["lgus"]]
            if len(registry_codes) != len(set(registry_codes)):
                raise CollectionError("Duplicate registry PSGC")
            if not 1 <= lgu_limit <= 10 or lgu_offset < 0:
                raise CollectionError("LGU batches require limit 1..10 and nonnegative offset")
            for lgu in reviewed["lgus"][lgu_offset:lgu_offset + lgu_limit]:
                if not isinstance(lgu.get("psgc"), str) or not re.fullmatch(r"01055(?:0[1-9]|[1-3][0-9]|4[0-8])000", lgu["psgc"]) or not isinstance(lgu.get("name"), str) or not lgu["name"].strip():
                    raise CollectionError("Invalid reviewed LGU identity")
                for dataset in DATASETS:
                    query = paginate(client, "lgu", dataset, {"q": lgu["name"]})
                    query["lgu_psgc"] = lgu["psgc"]
                    merge_query(query)
                    save()
            failures.pop(scope, None)
        if details or detail_ids:
            scope = "detail-selection"
            requested = [tuple(value.split(":", 1)) for value in (detail_ids or [])]
            if any(key not in client.records for key in requested):
                raise CollectionError("Requested detail ID was not collected")
            collected = {(entry["dataset"], entry["id"]) for entry in manifest["details"]}
            targets = [(key, client.records[key]) for key in requested] if requested else [(key, row) for key, row in client.records.items() if key not in collected]
            if requested and len(targets) > detail_limit:
                raise CollectionError("Requested detail IDs exceed bounded detail batch")
            failures.pop(scope, None)
            manifest["detail_collection"] = {"available_records": len(client.records), "requested_records": min(len(targets), detail_limit),
                                              "all_project_details_requested": len(targets) <= detail_limit and not requested}
            def fetch_detail(target):
                (dataset, identity), row = target
                operation = "detail:" + dataset + ":" + identity
                env, digest = client.get("/datasets/" + dataset + "/projects/" + quote(identity, safe=""),
                                         fresh=operation in failures)
                if env["data"].get("id") != identity:
                    raise CollectionError("Project detail identity mismatch")
                if any(env["data"].get(key) != value for key, value in row.items()):
                    raise CollectionError("Project detail conflicts with listing: " + identity)
                return {"dataset": dataset, "id": identity, "response_id": digest, "envelope": env}

            # Finish each small wave before saving so request logs are not mutated
            # during serialization, and no more than three requests are in flight.
            selected = targets[:detail_limit]
            with ThreadPoolExecutor(max_workers=detail_workers) as pool:
                for offset in range(0, len(selected), detail_workers):
                    wave = selected[offset:offset + detail_workers]
                    futures = [pool.submit(fetch_detail, target) for target in wave]
                    for ((dataset, identity), _), future in zip(wave, futures):
                        scope = "detail:" + dataset + ":" + identity
                        merge_record("details", future.result(), lambda item: (item["dataset"], item["id"]))
                        failures.pop(scope, None)
                    save()
        failures.pop("collection", None)
        manifest["run_complete"] = True
    except (CollectionError, OSError, ValueError, KeyError, TypeError) as exc:
        failures[scope] = str(exc)
    finally:
        save()
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--offices", action="store_true")
    parser.add_argument("--details", action="store_true")
    parser.add_argument("--detail-limit", type=int, default=10, help="At most 50 details per controlled batch (default 10)")
    parser.add_argument("--detail-workers", type=int, default=1, help="Concurrent detail requests, bounded to 1..3")
    parser.add_argument("--detail-id", action="append", dest="detail_ids", help="Select a collected dataset:upstream_id; repeat within the detail limit")
    parser.add_argument("--config", type=Path, help="Bounded collection configuration (trusted API cannot change)")
    parser.add_argument("--registry", type=Path)
    parser.add_argument("--lgu-offset", type=int, default=0)
    parser.add_argument("--lgu-limit", type=int)
    args = parser.parse_args(argv)
    try:
        result = collect(**vars(args))
    except (OSError, ValueError) as exc:
        print("Collection failed: " + str(exc))
        return 1
    print(json.dumps({"complete": result["complete"], "snapshot": result["snapshot"],
                      "errors": result["errors"], "queries": [
                          {key: query[key] for key in ("category", "dataset", "total", "downloaded", "complete", "error")}
                          for query in result["queries"]]}, indent=2))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
