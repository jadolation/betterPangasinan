"""Collect one documented PSA release into a fresh review-only crawler batch."""

import argparse
import hashlib
import json
from pathlib import Path
import time

from collector.exporters import safe_target, write_json, write_csv
from collector.psa_api import probe, token_from_file


def validate(rows):
    codes = {r["code"] for r in rows}
    if len(codes) != len(rows):
        raise ValueError("duplicate_codes")
    for row in rows:
        code = row["code"]
        if not isinstance(code, str) or len(code) != 10 or not code.isdigit():
            raise ValueError("invalid_code")
        if row["version"] != "Q2_2024" or row["reg"] != 1 or row["prv"] != 55:
            raise ValueError("unexpected_geography_or_release")
        level = row["geographic_level"]
        if level not in ("Prov", "City", "Mun", "Bgy"):
            raise ValueError("unknown_level")
        parent = (
            None
            if level == "Prov"
            else ("0105500000" if level in ("City", "Mun") else code[:7] + "000")
        )
        if parent and parent not in codes:
            raise ValueError("missing_parent")
        row["parent_psgc"] = parent
    return rows


def collect(target, token):
    target = safe_target(target)
    target.mkdir(parents=True, exist_ok=False)
    report = {
        "review_status": "pending",
        "coverage_status": "partial",
        "auto_publish": False,
        "release": "Q2_2024",
        "sources": [],
        "errors": [],
    }
    rows = []
    expected = None
    try:
        for page in range(1, 21):
            folder = target / f"page-{page}"
            evidence = probe(folder, token, page, 500)
            report["sources"].append(evidence)
            if evidence.get("status") != 200 or evidence.get("error"):
                raise ValueError("acquisition_failed")
            body = json.loads((folder / "response.redacted.raw").read_text())
            if (
                not isinstance(body.get("results"), list)
                or type(body.get("count")) is not int
            ):
                raise ValueError("unexpected_envelope")
            if expected is not None and expected != body["count"]:
                raise ValueError("count_changed")
            expected = body["count"]
            for index, source_row in enumerate(body["results"]):
                rows.append(
                    {
                        **source_row,
                        "evidence": {
                            "page": page,
                            "json_pointer": f"/results/{index}",
                            "artifact_sha256": evidence["artifact_sha256"],
                            "retrieved_at": evidence["retrieved_at"],
                            "source_url": evidence["source_url"],
                        },
                        "review_status": "pending",
                        "is_mock": False,
                    }
                )
            if body.get("next") is None:
                break
            if not body["results"]:
                raise ValueError("empty_continuation")
            time.sleep(2)
        else:
            raise ValueError("page_limit")
        if len(rows) != expected:
            raise ValueError("count_mismatch")
        validate(rows)
        for name, levels in [
            ("pangasinan_overview", ("Prov",)),
            ("pangasinan_lgus", ("City", "Mun")),
            ("pangasinan_barangays", ("Bgy",)),
        ]:
            selected = [r for r in rows if r["geographic_level"] in levels]
            write_json(
                target / (name + ".json"),
                {"review_status": "pending", "release": "Q2_2024", "records": selected},
            )
        write_csv(
            target / "lgu_directory.csv",
            [r for r in rows if r["geographic_level"] in ("City", "Mun")],
            [
                "code",
                "area_name",
                "parent_psgc",
                "version",
                "populations",
                "evidence",
                "review_status",
            ],
        )
        report["counts"] = {
            level: sum(r["geographic_level"] == level for r in rows)
            for level in ("Prov", "City", "Mun", "Bgy")
        }
        report["geography_coverage"] = "complete_for_api_query"
        report["population_years"] = sorted(
            {p["year"] for r in rows for p in r.get("populations", [])}
        )
    except (ValueError, KeyError, TypeError):
        report["errors"].append("acquisition_or_contract_validation_failed")
    report["files"] = {
        str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in target.rglob("*")
        if p.is_file()
    }
    write_json(target / "manifest.json", report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--authorize-live", action="store_true", required=True)
    args = parser.parse_args()
    report = collect(
        args.target, token_from_file(Path(__file__).resolve().parents[1] / ".env")
    )
    print(json.dumps({"counts": report.get("counts"), "errors": report["errors"]}))
    raise SystemExit(bool(report["errors"]))
