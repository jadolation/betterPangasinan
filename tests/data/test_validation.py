import json
import shutil
from decimal import Decimal

import pytest
from jsonschema import ValidationError

import build


@pytest.fixture
def fixtures(tmp_path):
    directory = tmp_path / "data"
    shutil.copytree(build.ROOT / "data" / "fixtures", directory)
    return directory


def change(directory, dataset, key, value):
    path = directory / f"{dataset}.json"
    records = json.loads(path.read_text())
    records[0][key] = value
    path.write_text(json.dumps(records))


def test_empty_production_and_private_fixture_graph():
    assert all(not records for records in build.load_data(build.ROOT / "data" / "production").values())
    records = build.load_data(build.ROOT / "data" / "fixtures", "test")
    assert len(records["lgus"]) == 4
    assert records["projects"][0]["status"] == "ongoing"
    assert records["services"][0]["fees"] is None
    assert build.financial_summary(records["finances"])["total"] == Decimal("300.75")
    assert build.financial_summary(records["finances"])["values"] == [Decimal("100.25"), Decimal("200.50")]


def test_production_rejects_fixtures(fixtures):
    with pytest.raises(ValueError, match="Production rejects"):
        build.load_data(fixtures)


@pytest.mark.parametrize("dataset,key,value", [
    ("projects", "id", "../escape"),
    ("projects", "source_ids", []),
    ("projects", "source_ids", ["missing"]),
    ("projects", "entity_id", "missing"),
    ("projects", "lgu_id", "missing"),
    ("projects", "contract_id", "missing"),
    ("projects", "status", "made_up_status"),
    ("contracts", "procurement_id", "missing"),
    ("procurements", "project_id", "missing"),
    ("sources", "accessed_date", "2026-02-30"),
    ("sources", "url", "javascript:alert(1)"),
    ("finances", "category", "fabricated"),
    ("finances", "amount_type", "budget-ish"),
    ("finances", "amount", -1),
    ("finances", "amount", 0.001),
    ("finances", "amount", float("nan")),
    ("finances", "internal_notes", "private draft"),
    ("lgus", "psgc", "0123456789"),
    ("lgus", "psgc", "invented"),
    ("lgus", "verification_status", "verified"),
    ("geography", "geometry", {"type": "Point", "coordinates": [181, 0]}),
    ("geography", "geometry", {"type": "Point", "coordinates": [0, 91]}),
    ("geography", "geometry", {"type": "Polygon", "coordinates": [[[0, 0], [1, 1], [2, 2]]]}),
    ("geography", "geometry", {"type": "Polygon", "coordinates": []}),
])
def test_rejects_invalid_records(fixtures, dataset, key, value):
    change(fixtures, dataset, key, value)
    with pytest.raises((ValueError, ValidationError)):
        build.load_data(fixtures, "test")


def test_duplicate_identifiers(fixtures):
    change(fixtures, "projects", "id", "mock-entity")
    with pytest.raises(ValueError, match="Duplicate ID"):
        build.load_data(fixtures, "test")


def test_missing_required_and_optional_datasets(fixtures):
    (fixtures / "geography.json").unlink()
    assert build.load_data(fixtures, "test")["geography"] == []
    (fixtures / "sources.json").unlink()
    with pytest.raises(ValueError, match="Missing required"):
        build.load_data(fixtures, "test")


def test_malformed_dataset(fixtures):
    (fixtures / "projects.json").write_text("{}")
    with pytest.raises(ValueError, match="expected an array"):
        build.load_data(fixtures, "test")


@pytest.mark.parametrize("dimension,value", [("reporting_period", "2025"), ("unit", "count"), ("amount_type", "actual_expenditure"), ("is_mock", False)])
def test_rejects_mixed_financial_series(dimension, value):
    records = build.load_data(build.ROOT / "data" / "fixtures", "test")["finances"]
    records[0][dimension] = value
    with pytest.raises(ValueError, match="incompatible"):
        build.financial_summary(records)


def test_null_is_not_zero():
    records = build.load_data(build.ROOT / "data" / "fixtures", "test")["finances"]
    records[0]["amount"] = 0
    assert build.financial_summary(records)["total"] == Decimal("200.5")
    records[0]["amount"] = None
    assert build.financial_summary(records)["total"] is None
    assert build.financial_summary([])["total"] is None


def test_mixed_mock_real_graph(fixtures):
    change(fixtures, "sources", "id", "real-source")
    change(fixtures, "sources", "is_mock", False)
    change(fixtures, "entities", "source_ids", ["real-source"])
    with pytest.raises(ValueError, match="Mixed mock/real"):
        build.load_data(fixtures, "test")


def test_psgc_requires_reviewed_registry_membership(fixtures):
    # Matching ten digits alone must never manufacture an official identifier.
    change(fixtures, "lgus", "id", "real-lgu")
    change(fixtures, "lgus", "is_mock", False)
    change(fixtures, "lgus", "psgc", "0123456789")
    (fixtures / "psgc-registry.json").write_text(json.dumps([
        {"psgc": "0123456789", "lgu_id": "real-lgu", "reviewed": False, "source_id": "mock-source"}
    ]))
    with pytest.raises(ValueError, match="reviewed registry"):
        build.load_data(fixtures, "test")


@pytest.mark.parametrize("availability", ["available", "not_yet_collected", "not_located_in_reviewed_sources", "not_yet_due", "under_review", "source_inaccessible", "not_applicable"])
def test_explicit_availability_states(fixtures, availability):
    change(fixtures, "lgus", "availability", availability)
    assert build.load_data(fixtures, "test")["lgus"][0]["availability"] == availability
