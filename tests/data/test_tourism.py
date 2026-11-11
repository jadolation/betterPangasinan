"""Tourism guide publication contract: provenance, geography, photo licensing."""
import copy
import json
from datetime import date
from pathlib import Path

import pytest
from pyproj import Transformer
from shapely import transform
from shapely.geometry import Point, shape

from scripts.tourism import ALLOWED_LICENSES, publication_payload, validate

ROOT = Path(__file__).resolve().parents[2]
_to_utm = Transformer.from_crs("EPSG:4326", "EPSG:32651", always_xy=True)


def _project(coords):
    x, y = _to_utm.transform(coords[:, 0], coords[:, 1])
    coords[:, 0], coords[:, 1] = x, y
    return coords


def bundle():
    return copy.deepcopy(publication_payload(ROOT)["data/tourism.json"])


def test_payload_contract():
    payload = publication_payload(ROOT)
    assert set(payload) == {"data/tourism.json"}
    data = payload["data/tourism.json"]
    assert set(data) == {"schema_version", "metadata", "sources", "attractions", "foods"}
    assert data["attractions"] and data["foods"]
    assert any(a["id"] == "hundred-islands-national-park" for a in data["attractions"])


def test_ids_unique_and_sources_resolve():
    data = bundle()
    source_ids = {s["id"] for s in data["sources"]}
    ids = [r["id"] for r in data["attractions"] + data["foods"]]
    assert len(ids) == len(set(ids))
    for record in data["attractions"] + data["foods"]:
        assert record["source_ids"] and set(record["source_ids"]) <= source_ids
        for route in record.get("routes", []):
            assert route["source_ids"] and set(route["source_ids"]) <= source_ids


def test_cross_references_resolve():
    data = bundle()
    lgus = {row["id"] for row in json.loads((ROOT / "data/lgus.json").read_text())}
    attractions = {a["id"] for a in data["attractions"]}
    foods = {f["id"] for f in data["foods"]}
    for a in data["attractions"]:
        assert a["lgu_id"] in lgus
        assert set(a["nearby_ids"]) <= attractions - {a["id"]}
        assert set(a["food_ids"]) <= foods
    for f in data["foods"]:
        assert f["lgu_id"] in lgus
        assert set(f["attraction_ids"]) <= attractions


def test_coordinates_inside_named_lgu():
    data = bundle()
    geo = json.loads((ROOT / "data/geography/municipalities.geojson").read_text())
    shapes = {f["properties"]["id"]: transform(shape(f["geometry"]), _project) for f in geo["features"]}
    for a in data["attractions"]:
        point = transform(Point(a["coordinates"]["lon"], a["coordinates"]["lat"]), _project)
        assert shapes[a["lgu_id"]].distance(point) <= 200, a["id"]


def test_photos_self_hosted_and_licensed():
    data = bundle()
    for record in data["attractions"] + [f for f in data["foods"] if f.get("photo")]:
        photo = record["photo"]
        assert photo["license"] in ALLOWED_LICENSES, record["id"]
        assert photo["alt"].strip()
        for key in ("author", "license_url", "source_url"):
            assert photo[key].strip(), (record["id"], key)
        assert photo["file"].startswith("assets/tourism/")
        assert (ROOT / photo["file"]).is_file(), photo["file"]


def test_commute_legs_and_fares_dated():
    data = bundle()
    for a in data["attractions"]:
        assert a["routes"], a["id"]
        for route in a["routes"]:
            assert route["legs"]
            for leg in route["legs"]:
                assert leg["mode"] and leg["from"] and leg["to"]
                if leg.get("fare_text"):
                    assert leg.get("fare_as_of"), (a["id"], leg)
        if a.get("entrance_fee_text"):
            assert a.get("fee_as_of"), a["id"]


def test_checked_recently():
    data = bundle()
    built = date.fromisoformat(data["metadata"]["collected_at"][:10])
    for a in data["attractions"]:
        assert (built - date.fromisoformat(a["checked_on"])).days <= 366, a["id"]


@pytest.mark.parametrize("mutation", ["mock", "unapproved", "unreviewed", "source", "lgu", "license", "fare", "outside"])
def test_rejects_invalid_publication(mutation):
    data = bundle()
    target = data["attractions"][0]
    if mutation == "mock":
        target["is_mock"] = True
    elif mutation == "unapproved":
        target["publication_status"] = "draft"
    elif mutation == "unreviewed":
        target["verification_status"] = "unreviewed"
    elif mutation == "source":
        target["source_ids"] = ["missing-source"]
    elif mutation == "lgu":
        target["lgu_id"] = "lgu-0000000000"
    elif mutation == "license":
        target["photo"]["license"] = "All rights reserved"
    elif mutation == "fare":
        leg = target["routes"][0]["legs"][0]
        leg["fare_text"] = "PHP 100"
        leg.pop("fare_as_of", None)
    else:
        target["coordinates"] = {"lat": 14.5995, "lon": 120.9842}  # Manila
    with pytest.raises(ValueError):
        validate(data, ROOT)
