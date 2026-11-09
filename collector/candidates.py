"""Offline, database-free application candidates from verified crawler captures."""

import argparse
import hashlib
import json
from pathlib import Path
import re

from jsonschema import Draft202012Validator, FormatChecker

from collector.exporters import safe_target, write_csv, write_json
from collector.psa_geography import validate

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_candidates(run, target):
    run = Path(run).resolve()
    target = safe_target(target)
    if target.exists() or target == run or run.is_relative_to(target):
        raise ValueError("Use a fresh output directory outside the input run")
    manifest = json.loads((run / "manifest.json").read_text())
    if manifest.get("errors"):
        raise ValueError("Failed acquisition cannot produce application candidates")
    for name, checksum in manifest["files"].items():
        path = (run / name).resolve()
        if not path.is_relative_to(run) or digest(path) != checksum:
            raise ValueError("Capture checksum mismatch")
    rows, sources, evidence = [], [], {}
    expected = None
    for page, source in enumerate(manifest["sources"], 1):
        name = f"page-{page}/response.redacted.raw"
        path = run / name
        if source.get("status") != 200 or digest(path) != source["artifact_sha256"]:
            raise ValueError("Unverified source artifact")
        body = json.loads(path.read_text())
        if expected is not None and expected != body["count"]:
            raise ValueError("Pagination count changed")
        expected = body["count"]
        sid = f"source-psa-api-page-{page}"
        sources.append(
            dict(
                id=sid,
                name=f"PSA PSGC Q2_2024 API page {page}",
                url=source["source_url"],
                accessed_date=source["retrieved_at"][:10],
                publisher="Philippine Statistics Authority",
                source_type="authenticated API capture",
                source_sha256=source["artifact_sha256"],
                is_mock=False,
                publication_status="draft",
                verification_status="unreviewed",
                availability="under_review",
            )
        )
        for index, row in enumerate(body["results"]):
            rows.append(row)
            evidence[row["code"]] = dict(
                source_ids=[sid],
                artifact=name,
                artifact_sha256=source["artifact_sha256"],
                json_pointer=f"/results/{index}",
                retrieved_at=source["retrieved_at"],
                release=row["version"],
                redacted=source["artifact_redacted"],
                original_values=row.copy(),
            )
    if not rows or len(rows) != expected or body.get("next") is not None:
        raise ValueError("Incomplete pagination")
    validate(rows)
    state = dict(
        is_mock=False,
        publication_status="draft",
        verification_status="unreviewed",
        availability="under_review",
    )
    lgus, statistics, barangays = [], [], []
    for row in rows:
        code = row["code"]
        if row["geographic_level"] == "Bgy":
            barangays.append(
                dict(
                    psgc=code,
                    name=row["area_name"],
                    parent_psgc=row["parent_psgc"],
                    release=row["version"],
                    evidence=evidence[code],
                    review_status="pending",
                )
            )
        if row["geographic_level"] not in ("City", "Mun"):
            continue
        populations = {}
        for pop in row["populations"]:
            if (
                pop["psgc"] != code
                or type(pop["year"]) is not int
                or pop["year"] in populations
            ):
                raise ValueError("Ambiguous population evidence")
            raw = pop["population"].strip()
            if not re.fullmatch(r"(?:[0-9]+|[0-9]{1,3}(?:,[0-9]{3})+)", raw):
                raise ValueError("Unrecognized population value")
            populations[pop["year"]] = int(raw.replace(",", ""))
            statistics.append(
                dict(
                    id=f"population-{code}-{pop['year']}",
                    name=f"{row['area_name']} population ({pop['year']})",
                    lgu_id="lgu-" + code,
                    source_ids=evidence[code]["source_ids"],
                    reporting_period=str(pop["year"]),
                    reference_period=str(pop["year"]),
                    value=populations[pop["year"]],
                    unit="persons",
                    definition="Population reported by the PSA API for the specified year.",
                    **state,
                )
            )
        lgus.append(
            dict(
                id="lgu-" + code,
                name=row["area_name"],
                psgc=code,
                classification="city"
                if row["geographic_level"] == "City"
                else "municipality",
                population=populations.get(2024),
                population_reference_date=None,
                psgc_release=None,
                source_ids=evidence[code]["source_ids"],
                collection_status="api_collected_pending_review",
                description="PSGC release Q2_2024; population year 2024 where supplied. Exact dates not supplied by API.",
                **state,
            )
        )
    common = json.loads((ROOT / "schemas/record.json").read_text())
    for name, records in [
        ("lgus", lgus),
        ("sources", sources),
        ("statistics", statistics),
    ]:
        schema = {
            "allOf": [common, json.loads((ROOT / f"schemas/{name}.json").read_text())]
        }
        validator = Draft202012Validator(schema, format_checker=FormatChecker())
        for record in records:
            validator.validate(record)
    files = {
        "lgus.json": lgus,
        "sources.json": sources,
        "statistics.json": statistics,
        "barangays.candidate.json": barangays,
        "provenance.json": evidence,
        "province_profile.candidate.json": next(
            r for r in rows if r["geographic_level"] == "Prov"
        ),
    }
    for name, value in files.items():
        write_json(target / name, value)
    write_csv(
        target / "lgu_directory.csv",
        lgus,
        ["id", "name", "psgc", "classification", "population", "publication_status"],
    )
    result = dict(
        review_status="pending",
        auto_publish=False,
        database_required=False,
        source_manifest_sha256=digest(run / "manifest.json"),
        counts=dict(
            lgus=len(lgus), barangays=len(barangays), statistics=len(statistics)
        ),
        gaps=[
            "Exact population reference dates and PSGC release date are not supplied by the API.",
            "Province profile requires capital, exact dates and human approval before application integration.",
            "Barangay candidate retains provenance; geographic application bundle integration remains separate.",
        ],
        files={p.name: digest(p) for p in target.iterdir() if p.is_file()},
    )
    write_json(target / "manifest.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_candidates(args.run, args.target)))
