"""Real reviewed PSA transcription import never implies fresh PSA verification."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from collector.models import GeographicUnit
from collector.persistence import Store
from collector.pipeline import collect, extract_psgc

SOURCE = Path(__file__).resolve().parents[2] / "pangasinan_lgu_registry_staging.json"


def test_observed_real_transcription_extracts_without_approving():
    result = extract_psgc(SOURCE.read_bytes())
    assert len(result["rows"]) == 49
    assert result["metadata"]["is_mock"] is False
    assert result["metadata"]["source_kind"] == "user_reviewed_transcription"
    assert result["metadata"]["independently_verified"] is False
    assert result["metadata"]["release"] == "2025-07-31"
    assert result["metadata"]["reference_period"] == "2024-07-01"
    province = next(
        r for r in result["rows"] if r["data"]["classification"] == "province"
    )
    assert province["data"]["population"] == 3188540
    assert "population_derivation" in province["evidence"]
    assert "capital" not in province["data"]
    assert "barangays_reported" not in province["data"]


def test_real_import_is_traceable_idempotent_and_partial(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    first = collect(SOURCE, tmp_path / "raw", store)
    second = collect(SOURCE, tmp_path / "raw", store)
    assert first["stage"]["new_versions"] == 49
    assert second["stage"]["new_versions"] == 0
    assert not second["changes"]["changed"]
    assert (
        first["artifact"]["sha256"] == hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    )
    assert first["quality"]["counts"] == {"province": 1, "city": 4, "municipality": 44}
    assert first["quality"]["validation_status"] == "incomplete"
    assert first["quality"]["coverage_status"] == "partial"
    assert any(g["field"] == "barangays" for g in first["quality"]["gaps"])
    assert all(
        not r["is_mock"] and r["review_status"] == "pending" for r in first["records"]
    )
    assert all(
        r["source_kind"] == "user_reviewed_transcription" for r in first["records"]
    )
    assert all(not r["independently_verified"] for r in first["records"])
    assert all(
        r["source_url"].startswith("https://psa.gov.ph/") for r in first["records"]
    )
    assert all(r["source_retrieved_at"] is None for r in first["records"])
    assert (
        first["records"][1]["raw_values"] == json.loads(SOURCE.read_text())["lgus"][0]
    )


@pytest.mark.parametrize(
    "change", ["integer_code", "duplicate", "period", "mock", "invalid_date"]
)
def test_invalid_real_transcriptions_do_not_create_versions(tmp_path, change):
    data = deepcopy(json.loads(SOURCE.read_text()))
    if change == "integer_code":
        data["lgus"][0]["psgc"] = 105503000
    if change == "duplicate":
        data["lgus"][1]["psgc"] = data["lgus"][0]["psgc"]
    if change == "period":
        data["lgus"][0]["population_reference_date"] = "2020-01-01"
    if change == "mock":
        data["lgus"][0]["is_mock"] = True
    if change == "invalid_date":
        data["metadata"]["administrative_listing_as_of"] = "not-a-date"
        for row in data["lgus"]:
            row["psgc_release"] = "not-a-date"
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data))
    run = collect(path, tmp_path / "raw", Store(tmp_path / "staging.sqlite"))
    assert run["quality"]["validation_status"] == "invalid"
    assert run["stage"]["new_versions"] == 0


@pytest.mark.parametrize(
    "body",
    [
        b"<html>Cloudflare challenge</html>",
        b"PK\x03\x04not a mapped official workbook",
        b"{}",
        b'{"metadata":{},"metadata":{}}',
    ],
)
def test_unknown_layouts_rejected_without_guessing(body):
    with pytest.raises(ValueError):
        extract_psgc(body)


def test_geographic_unit_requires_actual_code_shape():
    with pytest.raises(ValueError):
        GeographicUnit(
            psgc_code="TEST_CITY",
            name="x",
            classification="city",
            parent_psgc=None,
            release="2025-07-31",
        )


def test_mixed_mock_and_real_records_cannot_validate(tmp_path):
    from collector.pipeline import validate_records

    run = collect(SOURCE, tmp_path / "raw", Store(tmp_path / "staging.sqlite"))
    run["records"][0]["is_mock"] = True
    report = validate_records(run["records"])
    assert report["validation_status"] == "invalid"
    assert any(error["code"] == "mixed_mock_and_real" for error in report["errors"])
