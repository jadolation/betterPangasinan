"""Validated, explicitly allowlisted supplemental static publication resources."""

import importlib
import json
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ADAPTERS = {
    "scripts.government_directory": {"data/government-leadership.json"},
    "scripts.geography_data": {"data/geography/manifest.json", "data/geography/barangays.json", "data/geography/municipalities.geojson"},
    "scripts.historical_budget.publish": {"data/historical-budget/manifest.json", "data/historical-budget/departments.json", "data/historical-budget/programs.json", "data/historical-budget/coverage.json", "data/budget-context.json", "data/budget-hearings.json"},
    "scripts.provincial_reference": {"data/provincial-reference.json"},
    "scripts.tourism": {"data/tourism.json"},
}


def publication_payloads(root, data, mode="production", data_dir=None):
    root = Path(root)
    directory = Path(data_dir) if data_dir else root / "data" / ("fixtures" if mode == "test" else "production")
    profile_path = directory / "province_profile.json"
    profile = None
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        schema = json.loads((root / "schemas/province_profile.json").read_text(encoding="utf-8"))
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(profile)
        records = [row for row in data["lgus"] if row.get("psgc", "").startswith("01055")]
        if (len(records) != profile["lgu_count"] or sum(row["classification"] == "city" for row in records) != profile["cities"]
                or sum(row["classification"] == "municipality" for row in records) != profile["municipalities"]
                or any(row.get("population") is None or row.get("population_reference_date") != profile["population_reference_date"] for row in records)
                or sum(row["population"] for row in records) != profile["population"]):
            raise ValueError("Province summary does not reconcile with published LGU registry")
        if not set(profile["source_ids"]) <= {source["id"] for source in data["sources"]}:
            raise ValueError("Missing province provenance")
    payloads = {"data/province-profile.json": {
        "status": ("preview" if mode == "preview" else "available") if profile else "unavailable", "profile": profile,
        "sources": [row for row in data["sources"] if profile and row["id"] in profile["source_ids"]],
    }}
    for module, allowed in ADAPTERS.items():
        # A test's isolated root need not contain optional collections. The real
        # repository's adapters are validated before any output is replaced.
        if not (root / (module.replace(".", "/") + ".py")).is_file():
            continue
        values = importlib.import_module(module).publication_payload(root)
        if not isinstance(values, dict) or set(values) != allowed:
            raise ValueError(f"Unexpected publication files from {module}")
        payloads.update(values)
    for value in payloads.values():
        json.dumps(value, allow_nan=False)
    return payloads
