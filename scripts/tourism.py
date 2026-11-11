"""Validate and publish the curated Pangasinan tourism guide.

Every attraction, food and commute route needs a cited source. Fares and fees
are volatile, so each one carries an as-of date and is shown as approximate.
Coordinates must fall inside the named city or municipality (200 m tolerance,
the same simplified-boundary review rule as the project-location audit).
Photos are self-hosted under assets/tourism/ with a free license and credit.
"""
import json
from datetime import date
from functools import lru_cache
from pathlib import Path

import jsonschema
from shapely import transform
from shapely.geometry import Point, shape

from scripts.national_budget.geographic_audit import _project

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = "data/tourism.json"
ALLOWED_LICENSES = {"CC0", "Public domain", "CC BY 2.0", "CC BY 3.0", "CC BY 4.0",
                    "CC BY-SA 2.0", "CC BY-SA 3.0", "CC BY-SA 4.0"}
BOUNDARY_TOLERANCE_M = 200
MAX_CHECK_AGE_DAYS = 366


@lru_cache(maxsize=4)
def _boundaries(root):
    geo = json.loads((Path(root) / "data/geography/municipalities.geojson").read_text())
    return {f["properties"]["id"]: transform(shape(f["geometry"]), _project) for f in geo["features"]}


def validate(data, root=ROOT, mode="production"):
    root = Path(root)
    schema = json.loads((root / "schemas/tourism.schema.json").read_text())
    try:
        jsonschema.validate(data, schema, format_checker=jsonschema.FormatChecker())
    except jsonschema.ValidationError as error:
        raise ValueError(f"Tourism schema: {error.message}") from error
    sources = {s["id"] for s in data["sources"]}
    if len(sources) != len(data["sources"]):
        raise ValueError("Duplicate tourism source ID")
    records = data["attractions"] + data["foods"]
    ids = [r["id"] for r in records]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate tourism record ID")
    attractions = {a["id"] for a in data["attractions"]}
    foods = {f["id"] for f in data["foods"]}
    lgus = {row["id"] for row in json.loads((root / "data/lgus.json").read_text())}
    boundaries = _boundaries(str(root))
    collected = date.fromisoformat(data["metadata"]["collected_at"][:10])

    def check_sources(ids, owner):
        if not ids or not set(ids) <= sources:
            raise ValueError(f"Unknown or missing tourism source: {owner}")

    for record in records:
        identifier = record["id"]
        check_sources(record["source_ids"], identifier)
        if record["is_mock"] != identifier.startswith("mock-"):
            raise ValueError(f"Mock ID/flag mismatch: {identifier}")
        if mode == "production" and (record["is_mock"] or record["publication_status"] != "approved"
                                     or record["verification_status"] == "unreviewed"):
            raise ValueError(f"Production rejects mock, unpublished or unreviewed record: {identifier}")
        if record["lgu_id"] not in lgus:
            raise ValueError(f"Unknown LGU: {identifier}")
        photo = record.get("photo")
        if photo:
            if photo["license"] not in ALLOWED_LICENSES:
                raise ValueError(f"Photo license not allowed: {identifier}")
            for key in ("file", "file_small"):
                if photo.get(key) and not (root / photo[key]).is_file():
                    raise ValueError(f"Missing photo file: {photo[key]}")
    for a in data["attractions"]:
        identifier = a["id"]
        if a.get("coordinate_source_id"):
            check_sources([a["coordinate_source_id"]], identifier)
        if not set(a["nearby_ids"]) <= attractions - {identifier} or not set(a["food_ids"]) <= foods:
            raise ValueError(f"Broken tourism cross-reference: {identifier}")
        point = transform(Point(a["coordinates"]["lon"], a["coordinates"]["lat"]), _project)
        if boundaries[a["lgu_id"]].distance(point) > BOUNDARY_TOLERANCE_M:
            raise ValueError(f"Coordinates outside named LGU: {identifier}")
        if a.get("entrance_fee_text") and not a.get("fee_as_of"):
            raise ValueError(f"Entrance fee needs an as-of date: {identifier}")
        for route in a["routes"]:
            check_sources(route["source_ids"], identifier)
            for leg in route["legs"]:
                if leg.get("fare_text") and not leg.get("fare_as_of"):
                    raise ValueError(f"Fare needs an as-of date: {identifier}")
        if (collected - date.fromisoformat(a["checked_on"])).days > MAX_CHECK_AGE_DAYS:
            raise ValueError(f"Tourism record check is stale: {identifier}")
    for f in data["foods"]:
        if not set(f["attraction_ids"]) <= attractions:
            raise ValueError(f"Broken tourism cross-reference: {f['id']}")


def publication_payload(root=ROOT):
    root = Path(root)
    data = json.loads((root / "data/production/tourism.json").read_text())
    validate(data, root)
    return {OUTPUT: data}
