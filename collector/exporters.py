"""Review-only outputs; never accept a publication destination."""

import csv
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def safe_target(path):
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Refusing symlink output")
    path = path.resolve()
    if path.is_relative_to(ROOT) and not path.is_relative_to(ROOT / "data/staging"):
        raise ValueError("Repository review outputs must be under data/staging")
    protected = [
        ROOT / p
        for p in (
            "public",
            "src",
            "assets",
            "data/production",
            "data/national_budget",
            "data/national-budget",
            "data/geography",
            "data/historical_budget",
        )
    ]
    if any(
        path == p or path.is_relative_to(p) or p.is_relative_to(path) for p in protected
    ):
        raise ValueError(
            "Review output overlaps protected application or publication files"
        )
    return path


def write_json(path, value):
    path = safe_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing symlink output")
    path.write_text(
        json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False)
        + "\n"
    )


def write_csv(path, rows, columns):
    path = safe_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError("Refusing symlink output")

    def safe(value):
        if isinstance(value, (dict, list)):
            value = json.dumps(value, sort_keys=True)
        if isinstance(value, str) and value.lstrip().startswith(
            ("=", "+", "-", "@", "\t", "\r", "\n")
        ):
            return "'" + value
        return value

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({key: safe(row.get(key)) for key in columns} for row in rows)


def export_run(run, target):
    target = safe_target(target)
    target.mkdir(parents=True, exist_ok=True)
    records = run["records"]
    metadata = {
        "run_id": run["run_id"],
        "is_mock": run["artifact"]["is_mock"],
        "review_status": "pending",
        "coverage_status": run["quality"]["coverage_status"],
        "quality": run["quality"],
        "artifact": run["artifact"],
    }
    files = []
    for filename, kinds in [
        ("pangasinan_lgus.json", ("city", "municipality")),
        ("pangasinan_barangays.json", ("barangay",)),
        ("pangasinan_overview.json", ("province",)),
    ]:
        write_json(
            target / filename,
            {
                **metadata,
                "records": [r for r in records if r["data"]["classification"] in kinds],
            },
        )
        files.append(filename)
    rows = [
        {
            **r["data"],
            "is_mock": r["is_mock"],
            "review_status": r["review_status"],
            "artifact_sha256": r["artifact_sha256"],
        }
        for r in records
        if r["data"]["classification"] in ("city", "municipality")
    ]
    write_csv(
        target / "lgu_directory.csv",
        rows,
        [
            "psgc_code",
            "name",
            "classification",
            "parent_psgc",
            "population",
            "is_mock",
            "review_status",
            "artifact_sha256",
        ],
    )
    write_csv(target / "source_inventory.csv", [run["artifact"]], list(run["artifact"]))
    write_csv(
        target / "collection_log.csv",
        [{"run_id": run["run_id"], **run["quality"]}],
        ["run_id", "validation_status", "coverage_status", "errors"],
    )
    write_csv(
        target / "collection_gaps.csv",
        run["quality"]["gaps"],
        ["record_id", "field", "reason"],
    )
    write_json(target / "quality_report.json", run["quality"])
    write_json(target / "change_report.json", run.get("changes", {}))
    files += [
        "lgu_directory.csv",
        "source_inventory.csv",
        "collection_log.csv",
        "collection_gaps.csv",
        "quality_report.json",
        "change_report.json",
    ]
    manifest = {
        **metadata,
        "files": {
            name: hashlib.sha256((target / name).read_bytes()).hexdigest()
            for name in files
        },
    }
    write_json(target / "manifest.json", manifest)
    return manifest
