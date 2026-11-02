"""Collect deliberately scoped, resumable snapshots. Never approves a refresh.

Run: python3 -m scripts.historical_budget.collect
Optional batches: --queries-file queries.json --batch-start 0 --batch-size 2
The queries file is an explicit JSON array of search strings, not an automatic
expansion of the 48-LGU registry. Pangasinan is always searched first.
"""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

BASE = "https://budget.bettergov.ph"
ROOT = Path(__file__).resolve().parents[2]


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, indent=2) + "\n", encoding="utf-8")


class Collector:
    def __init__(self, root=ROOT):
        self.folder = Path(root) / "data/historical_budget"

    def get(self, path, params=None):
        url = BASE + path + (("?" + urlencode(params)) if params else "")
        key = hashlib.sha256(url.encode()).hexdigest()
        target = self.folder / "approved/inputs" / (key + ".json")
        if target.exists():
            cached = json.loads(target.read_text())
            if "error" not in cached:
                return cached
        entry = {"url": url, "retrieved_at": datetime.now(timezone.utc).isoformat()}
        for attempt in range(3):
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"})
                with urlopen(request, timeout=90) as response:
                    raw = response.read()
                    entry.update(status=response.status, data=json.loads(raw), raw_sha256=hashlib.sha256(raw).hexdigest())
                    entry.pop("error", None)
                raw_path = self.folder / "raw" / (key + ".json")
                raw_path.parent.mkdir(parents=True, exist_ok=True)
                raw_path.write_bytes(raw)
                break
            except HTTPError as error:
                entry.update(status=error.code, error=str(error))
                if error.code < 500:
                    break
            except (URLError, TimeoutError, ValueError) as error:
                entry.update(status=None, error=str(error))
            if attempt < 2:
                time.sleep(1 + attempt)
        entry["payload_sha256"] = digest(entry.get("data"))
        save(target, entry)
        return entry

    def programs(self, department, query):
        cursor = None
        seen = set()
        pages = []
        error = None
        while True:
            params = {"q": query, "limit": 500}
            if cursor:
                params["cursor"] = cursor
            page = self.get(f"/api/v1/gaa/departments/{department}/programs", params)
            pages.append(page["url"])
            if "error" in page:
                error = page["error"]
                break
            body = page["data"]
            if not isinstance(body.get("data"), list) or "next_cursor" not in body:
                error = "Unexpected list or missing pagination field"
                break
            cursor = body["next_cursor"]
            if not cursor:
                break
            if cursor in seen:
                error = "Repeated cursor; collection incomplete"
                break
            seen.add(cursor)
        return {"department_id": department, "query": query, "pages": pages, "error": error, "exhausted": error is None}

    def run(self, queries):
        departments = self.get("/api/v1/gaa/departments")
        if "error" in departments:
            raise ValueError("Department discovery failed; no assumed department count")
        rows = departments["data"]["data"]
        jobs = [(str(d["id"]), q) for q in queries for d in rows]
        # Four concurrent departments; cursor pages within a department stay serial.
        with ThreadPoolExecutor(max_workers=4) as pool:
            coverage = list(pool.map(lambda job: self.programs(*job), jobs))
        contexts = {}
        for name, path in {
            "nep_overview": "/api/v1/nep/2027",
            "nep_departments": "/api/v1/nep/2027/departments",
            "nep_dpwh": "/api/v1/nep/2027/departments/18",
            "nep_regions": "/api/v1/nep/2027/rollups/region",
            "budget_cycle_overview": "/api/v1/budget-cycle",
            "budget_cycle_dpwh": "/api/v1/budget-cycle/departments/18",
            "openapi": "/api/v1/openapi.json",
        }.items():
            contexts[name] = self.get(path)["url"]
        contexts["hearings"] = self.get("/api/v1/hearings/search", {"q": "Pangasinan", "limit": 100})["url"]
        save(self.folder / "approved/collection.json", {
            "departments_url": departments["url"], "queries": coverage, "contexts": contexts,
            "limitations": ["Name matches are not verified geography; shared and outside-province names remain.",
                             "Optional LGU queries not automatically run; province-name coverage is not all provincial funding.",
                             "Hearing search has a documented limit of 100 and no documented offset.",
                             "GAA source zero can mean no source row; it is not proof of a funded project."]})
        print(f"Collected {len(coverage)} department/query combinations; {sum(bool(q['error']) for q in coverage)} errors")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--queries-file", type=Path)
    parser.add_argument("--lgu-registry", type=Path, help="Explicit optional starter registry, e.g. pangasinan_lgu_registry_staging.json; names are query leads only")
    parser.add_argument("--batch-start", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=0)
    args = parser.parse_args()
    queries = ["Pangasinan"]
    if args.queries_file or args.lgu_registry:
        if args.queries_file and args.lgu_registry:
            parser.error("choose queries-file or lgu-registry, not both")
        if args.lgu_registry:
            registry = json.loads(args.lgu_registry.read_text())
            values = [row["name"].removeprefix("City of ") for row in registry["lgus"]]
        else:
            values = json.loads(args.queries_file.read_text())
        if not isinstance(values, list) or not all(isinstance(v, str) and v.strip() for v in values):
            parser.error("queries-file must contain an array of nonempty strings")
        if args.batch_size < 1 or args.batch_start < 0:
            parser.error("optional queries require explicit positive --batch-size and nonnegative --batch-start")
        queries += values[args.batch_start:args.batch_start + args.batch_size]
    collector = Collector(args.root)
    previous = collector.folder / "approved/collection.json"
    if previous.exists():
        queries += [q["query"] for q in json.loads(previous.read_text())["queries"]]
    collector.run(list(dict.fromkeys(queries)))


if __name__ == "__main__":
    main()
