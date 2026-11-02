"""Repeatably map the user-reviewed PSA starter into the existing static graph."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
PSA_ID = "source-psa-psgc-20250731"
PROVINCE_ID = "source-pangasinan-province-reference"
AUTHORIZATION = "User reviewed the supplied data and authorized its display on 2026-11-01. Original collection labels are retained; no independent live-source verification is inferred."


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def normalize(starter, checksum, accessed_date):
    metadata, rows = starter["metadata"], starter["lgus"]
    if metadata["province_psgc"] != "0105500000" or len(rows) != 48:
        raise ValueError("Expected the supplied Pangasinan 48-LGU registry")
    source_url = metadata["url"]
    source = urlsplit(source_url)
    if source.scheme != "https" or source.hostname not in ("psa.gov.ph", "www.psa.gov.ph") or source.username or source.password:
        raise ValueError("Registry must identify its PSA HTTPS source")
    seen, names, lgus, registry = set(), set(), [], []
    state = {"is_mock": False, "publication_status": "approved", "verification_status": "reviewed", "availability": "available"}
    for row in rows:
        code = row["psgc"]
        if not isinstance(code, str) or not re.fullmatch(r"01055(?:0[1-9]|[1-3][0-9]|4[0-8])000", code) or code in seen:
            raise ValueError("Duplicate or malformed municipal PSGC")
        if not isinstance(row["name"], str) or not row["name"].strip() or row["name"] in names:
            raise ValueError("Duplicate or missing LGU name")
        if row["classification"] not in ("city", "municipality") or type(row["population_2024"]) is not int or row["population_2024"] < 0:
            raise ValueError("Invalid classification/population")
        if row["population_reference_date"] != metadata["population_reference_date"] or row["psgc_release"] != metadata["administrative_listing_as_of"] or row["source_url"] != source_url:
            raise ValueError("Inconsistent registry dates or source URL")
        seen.add(code); names.add(row["name"])
        identifier = "lgu-" + code
        lgus.append({"id": identifier, "name": row["name"], "psgc": code, "classification": row["classification"],
                     "population": row["population_2024"], "population_reference_date": row["population_reference_date"],
                     "psgc_release": row["psgc_release"], "reporting_period": row["population_reference_date"][:4],
                     "source_ids": [PSA_ID], "collection_status": row.get("review_status", "not_supplied"),
                     "source_sha256": checksum, "description": AUTHORIZATION, **state})
        registry.append({"psgc": code, "lgu_id": identifier, "reviewed": True, "source_id": PSA_ID,
                         "release": row["psgc_release"], "review_note": AUTHORIZATION})
    cities = sum(row["classification"] == "city" for row in lgus)
    population = sum(row["population"] for row in lgus)
    if cities != 4 or len(lgus) - cities != 44 or population != 3_188_540:
        raise ValueError("Supplied city/municipality counts or population checksum disagree")
    sources = [
        {"id": PSA_ID, "name": "PSA Pangasinan PSGC listing and supplied 2024 population transcription", "url": source_url,
         "publisher": "Philippine Statistics Authority", "source_type": "user-reviewed official-source transcription",
         "source_sha256": checksum, "accessed_date": accessed_date, "reporting_period": "2024",
         "description": f"Population reference {metadata['population_reference_date']}; administrative listing {metadata['administrative_listing_as_of']}. Original starter review label: {metadata.get('review_status')}. {AUTHORIZATION}", **state},
        {"id": PROVINCE_ID, "name": "Provincial Government of Pangasinan reference information", "url": "https://www.pangasinan.gov.ph/",
         "publisher": "Provincial Government of Pangasinan", "source_type": "official provincial reference supplied with integration specification",
         "accessed_date": accessed_date, "description": "Capital and reported barangay count supplied in the reviewed integration specification; not a live directory retrieval. " + AUTHORIZATION, **state},
    ]
    profile = {"id": "province-pangasinan", "name": "Pangasinan", "psgc": metadata["province_psgc"], "capital": "Lingayen",
               "population": population, "population_reference_date": metadata["population_reference_date"],
               "administrative_listing_as_of": metadata["administrative_listing_as_of"],
               "cities": cities, "municipalities": len(lgus) - cities, "lgu_count": len(lgus), "barangays_reported": 1364,
               "barangay_count_note": "Reported provincial reference count; collected barangay coverage is reported independently by the geographic dataset.",
               "source_ids": [PSA_ID, PROVINCE_ID], "source_sha256": checksum, "review_note": AUTHORIZATION, **state}
    statistics = [{"id": "population-" + row["psgc"] + "-2024", "name": row["name"] + " population (2024)",
                   "lgu_id": row["id"], "source_ids": [PSA_ID], "reporting_period": "2024", "reference_period": row["population_reference_date"],
                   "value": row["population"], "unit": "persons", "definition": "Population in the supplied PSA registry at its recorded reference date.",
                   "source_sha256": checksum, **state} for row in lgus]
    return {"lgus": lgus, "sources": sources, "psgc-registry": registry, "province_profile": profile, "statistics": statistics}


def publish(bundle, directory):
    directory = Path(directory)
    if not (directory / "entities.json").exists():
        write_json(directory / "entities.json", [])
    for name in ("lgus", "sources", "psgc-registry", "statistics"):
        path = directory / (name + ".json")
        previous = read_json(path) if path.exists() else []
        incoming = bundle[name]
        key = "psgc" if name == "psgc-registry" else "id"
        ids = {row[key] for row in incoming}
        if name == "lgus" and any(row.get("psgc") in {item["psgc"] for item in incoming} and row["id"] not in ids for row in previous):
            raise ValueError("Conflicting existing ID for an imported PSGC")
        write_json(path, [row for row in previous if row[key] not in ids] + incoming)
    write_json(directory / "province_profile.json", bundle["province_profile"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Normalized staging bundle")
    parser.add_argument("--publish", type=Path, help="Explicitly write the user-reviewed records to this dataset directory")
    args = parser.parse_args()
    raw = args.input.read_bytes()
    bundle = normalize(json.loads(raw), hashlib.sha256(raw).hexdigest(), datetime.now(timezone.utc).date().isoformat())
    write_json(args.output, bundle)
    if args.publish:
        publish(bundle, args.publish)
    print("Normalized 48 LGUs: 4 cities, 44 municipalities, 3,188,540 persons (2024 reference).")


if __name__ == "__main__":
    main()
