from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.national_budget.geographic_audit import (
    GEOJSON_PATH, SUMMARY_PATH, _pair, publication_payload, validate_publication_payload,
)
from scripts.national_budget.pipeline import public_file_hash

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def boundary_root(tmp_path):
    folder = tmp_path / "data/geography"
    folder.mkdir(parents=True)
    # One polygon with a hole and a disconnected MultiPolygon island.
    polygon = [[[120, 15], [121, 15], [121, 16], [120, 16], [120, 15]],
               [[120.4, 15.4], [120.6, 15.4], [120.6, 15.6], [120.4, 15.6], [120.4, 15.4]]]
    island = [[[121.2, 15], [121.3, 15], [121.3, 15.1], [121.2, 15.1], [121.2, 15]]]
    (folder / "municipalities.geojson").write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "City of Alaminos", "psgc": "0105503000"},
         "geometry": {"type": "MultiPolygon", "coordinates": [polygon, island]}},
        {"type": "Feature", "properties": {"name": "Urdaneta City", "psgc": "0105546000"},
         "geometry": {"type": "Polygon", "coordinates": [
             [[121.5, 15], [122, 15], [122, 16], [121.5, 16], [121.5, 15]]]}}]}))
    return tmp_path


def project(start=(120.2, 15.2), end=(120.3, 15.3), dataset="fmr"):
    segment = {"id": "source-segment", "start_latitude": start[1], "start_longitude": start[0],
               "end_latitude": end[1], "end_longitude": end[0]}
    source = {"segments": [segment], "coordinates_raw": "START: exact 15.2000, 120.2000",
              "normalization_rules": ["source_rule"], "source": {"pdf_page": 12}}
    return {"id": "fmr:test", "upstream_id": "test", "title": "Road, Alaminos, Pangasinan",
            "dataset": dataset, "fiscal_year": 2027, "house_stage": "hgab2", "snapshot_id": "snapshot",
            "geographic_review_status": "pending", "lgu_associations": [],
            "upstream": {"lat": 15.5, "lon": 120.5, "nep_php": None, "house_php": 100,
                         "bridge_group": "house_only", "pdf_url": {"nep": None}},
            "detail_evidence": [{"response_id": "receipt", "envelope": {"data": {"record": {"house": source}}}}]}


def result(root, p):
    payload = publication_payload(root, [p], {"snapshot_id": "snapshot"})
    return payload[SUMMARY_PATH]["projects"][0], payload[GEOJSON_PATH]["features"]


def test_submarine_original_coordinate_not_corrected(boundary_root):
    row, features = result(boundary_root, project((120, -6)))
    assert row["segments"][0]["start"] == [120, -6]
    assert features[0]["geometry"]["coordinates"] == [120, -6]
    assert "outside_province" in row["location_flags"]
    assert "endpoint_distance_over_200km_review" in row["location_flags"]
    assert not any("offshore" in flag for flag in row["location_flags"])


def test_local_and_mindanao_original_line(boundary_root):
    row, features = result(boundary_root, project(end=(125, 6)))
    assert features[-1]["geometry"] == {"type": "LineString", "coordinates": [[120.2, 15.2], [125, 6]]}
    assert row["segments"][0]["distance_km"] > 200


@pytest.mark.parametrize("pair,status", [((120, 15.2), "inside_province"),
    ((120.5, 15.5), "outside_province"), ((121.25, 15.05), "inside_province"),
    ((119.999, 15.2), "near_province_boundary"), ((119.99, 15.2), "outside_province")])
def test_holes_multipolygon_boundary_tolerance(boundary_root, pair, status):
    row, features = result(boundary_root, project(pair))
    assert features[0]["properties"]["geographic_position"] == status
    assert row["segments"][0]["start_status"] == status


@pytest.mark.parametrize("bad", [None, "15.2", "malformed", 91, True])
def test_invalid_pair_keeps_valid_partner(boundary_root, bad):
    p = project()
    s = p["detail_evidence"][0]["envelope"]["data"]["record"]["house"]["segments"][0]
    s["start_latitude"] = bad
    row, features = result(boundary_root, p)
    assert row["segments"][0]["start"] is None
    assert row["segments"][0]["end"] == [120.3, 15.3]
    assert len(features) == 1 and features[0]["properties"]["endpoint"] == "end"
    json.dumps(row, allow_nan=False)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_numeric_validation_and_public_json_rejection(boundary_root, bad):
    assert _pair(bad, 120) is None
    p = project()
    p["upstream"]["lat"] = bad
    # Exact current-builder byte binding cannot be fabricated for invalid JSON.
    with pytest.raises(ValueError, match="JSON compliant"):
        result(boundary_root, p)


def test_version_dedup_preserves_all_source_evidence(boundary_root):
    p = project()
    record = p["detail_evidence"][0]["envelope"]["data"]["record"]
    record["nep"] = deepcopy(record["house"])
    record["nep"]["segments"][0]["id"] = "nep-other-id"
    row, features = result(boundary_root, p)
    assert len(row["segments"]) == 1 and len(features) == 3
    s = row["segments"][0]
    assert s["source_versions"] == ["nep", "house"]
    assert len(s["evidence"]) == 2 and "duplicate_segment" in s["flags"]
    assert s["evidence"][0]["source_record"]["coordinates_raw"] == record["nep"]["coordinates_raw"]
    record["nep"]["segments"][0]["start_latitude"] = 15.25
    row, features = result(boundary_root, p)
    assert len(row["segments"]) == 2 and len(features) == 6
    assert "repeated_point" in row["location_flags"]


def test_identical_endpoints_and_unpaired_named_point(boundary_root):
    p = project(end=(120.2, 15.2))
    source = p["detail_evidence"][0]["envelope"]["data"]["record"]["house"]
    source["points"] = [{"id": "orphan", "latitude": 15.1, "longitude": 120.1, "role": "start"}]
    row, features = result(boundary_root, p)
    assert "identical_endpoints" in row["location_flags"]
    assert row["segments"][0]["distance_km"] == 0
    assert row["display_status"] == "needs_review"
    assert features[-1]["properties"]["endpoint"] == "point"


def test_namesake_not_claim_and_office_not_evidence(boundary_root):
    p = project((125, 6), (125.1, 6.1))
    p["title"] = "Road, Brgy. New Pangasinan, Koronadal City, South Cotabato"
    row, _ = result(boundary_root, p)
    assert row["display_status"] == "name_match_elsewhere"
    assert row["stated_province"] is None
    assert "stated_province_coordinate_mismatch" not in row["location_flags"]
    p["title"] = "Pangasinan road"
    p["upstream"]["office"] = "South Cotabato DEO"
    row, _ = result(boundary_root, p)
    assert row["stated_province"] is None
    assert "name_match_elsewhere" not in row["location_flags"]


def test_fmr_never_falls_back_to_centroid_other_programs_api_point(boundary_root):
    p = project()
    p["detail_evidence"] = []
    row, features = result(boundary_root, p)
    assert row["display_status"] == "unavailable" and not features
    p["dataset"] = "dpwh"
    p["upstream"].update(lat=15.2, lon=120.2)
    row, features = result(boundary_root, p)
    assert row["display_status"] == "plausible"
    assert row["coordinate_basis"] == "api_published_point"
    assert features[0]["properties"]["role"] == "api_published_point"
    p["upstream"].update(lat=None, lon=None)
    row, features = result(boundary_root, p)
    assert row["display_status"] == "unavailable" and not features


def test_source_binding_and_stale_validation(boundary_root):
    p = project()
    original = deepcopy(p)
    manifest = {"snapshot_id": "snapshot"}
    payload = publication_payload(boundary_root, [p], manifest)
    assert p == original
    assert set(payload) == {GEOJSON_PATH, SUMMARY_PATH}
    summary = payload[SUMMARY_PATH]
    assert summary["source_hashes"]["projects"] == public_file_hash([p])
    assert summary["files"]["projects.geojson"] == public_file_hash(payload[GEOJSON_PATH])
    assert validate_publication_payload(boundary_root, [p], manifest, payload)
    p["upstream"]["house_php"] = 101
    with pytest.raises(ValueError, match="Stale"):
        validate_publication_payload(boundary_root, [p], manifest, payload)
    with pytest.raises(ValueError):
        validate_publication_payload(boundary_root, [original], {"snapshot_id": "changed"}, payload)
    path = boundary_root / "data/geography/municipalities.geojson"
    path.write_text(path.read_text() + "\n")
    with pytest.raises(ValueError):
        validate_publication_payload(boundary_root, [original], manifest, payload)


def test_duplicate_project_ids_rejected(boundary_root):
    with pytest.raises(ValueError, match="Duplicate project IDs"):
        publication_payload(boundary_root, [project(), project()], {"snapshot_id": "snapshot"})


@pytest.mark.parametrize("start,expected_status,municipality_result", [
    ((120.2, 15.2), "plausible", "covered"),
    ((121.25, 15.05), "plausible", "covered"),
    ((119.999, 15.2), "needs_review", "within_tolerance"),
    ((121.7, 15.2), "suspicious", "excluded"),
    ((120.5, 15.5), "suspicious", "excluded"),
])
def test_named_municipality_polygon_multi_hole_and_tolerance(boundary_root, start, expected_status, municipality_result):
    p = project(start)
    original = deepcopy(p)
    row, features = result(boundary_root, p)
    assert row["display_status"] == expected_status
    assert row["segments"][0]["municipality_checks"]["start"] == {"0105503000": municipality_result}
    assert ("municipality_mismatch" in row["location_flags"]) == (municipality_result == "excluded")
    assert features[0]["geometry"]["coordinates"] == list(start)
    assert row["source_fields"]["lgu_associations"] == p["lgu_associations"] == []
    assert p == original


def test_municipality_mismatch_inside_province_and_multiple_named_lgus(boundary_root):
    p = project((121.7, 15.2))
    row, features = result(boundary_root, p)
    assert row["segments"][0]["start_status"] == "inside_province"
    assert row["display_status"] == "suspicious"
    assert "municipality_mismatch" in row["location_flags"]
    assert "outside_province" not in row["location_flags"]
    p["title"] = "Road, Alaminos and Urdaneta, Pangasinan"
    row, _ = result(boundary_root, p)
    assert row["display_status"] == "plausible"
    assert "municipality_mismatch" not in row["location_flags"]
    assert row["segments"][0]["municipality_checks"]["start"] == {
        "0105503000": "excluded", "0105546000": "covered"}


@pytest.mark.parametrize("dataset", ["fmr", "dpwh", "hfep", "nia"])
def test_no_explicit_place_is_needs_review_not_plausible(boundary_root, dataset):
    p = project(dataset=dataset)
    p["title"] = "Road selected by a Pangasinan query"
    p["upstream"].update(lat=15.2, lon=120.2)
    row, _ = result(boundary_root, p)
    assert row["display_status"] == "needs_review"
    p["upstream"].update(lat=6, lon=125)
    if dataset == "fmr":
        p["detail_evidence"][0]["envelope"]["data"]["record"]["house"]["segments"] = [
            {"start_latitude": 6, "start_longitude": 125, "end_latitude": 6.1, "end_longitude": 125.1}]
    row, _ = result(boundary_root, p)
    assert row["display_status"] == "outside_pangasinan"


def test_missing_optional_boundaries_retains_source_locations(tmp_path):
    p = project()
    before = deepcopy(p)
    payload = publication_payload(tmp_path, [p], {"snapshot_id": "snapshot"})
    assert set(payload) == {GEOJSON_PATH, SUMMARY_PATH}
    summary = payload[SUMMARY_PATH]
    assert summary["status"] == payload[GEOJSON_PATH]["status"] == "unavailable"
    assert summary["unavailable_reason"] == "municipality_boundaries_unavailable"
    assert summary["source_hashes"]["municipalities"] is None
    assert summary["counts"]["projects"] == 1
    assert summary["counts"]["by_status"] == {"needs_review": 1}
    assert summary["projects"][0]["segments"][0]["start"] == [120.2, 15.2]
    assert payload[GEOJSON_PATH]["features"][0]["properties"]["status"] == "needs_review"
    assert len(payload[GEOJSON_PATH]["features"]) == 3
    assert summary["files"]["projects.geojson"] == public_file_hash(payload[GEOJSON_PATH])
    assert validate_publication_payload(tmp_path, [p], {"snapshot_id": "snapshot"}, payload)
    assert p == before


def test_unavailable_manifest_does_not_read_boundary(boundary_root, monkeypatch):
    def no_read(*args, **kwargs):
        raise AssertionError("Unavailable source must not read boundaries")
    monkeypatch.setattr(Path, "read_bytes", no_read)
    p = project()
    p["detail_evidence"] = []
    payload = publication_payload(boundary_root, [p], {"status": "unavailable", "snapshot_id": None})
    assert payload[SUMMARY_PATH]["status"] == "unavailable"
    assert payload[SUMMARY_PATH]["unavailable_reason"] == "source_manifest_unavailable"
    assert payload[SUMMARY_PATH]["counts"]["by_status"] == {"unavailable": 1}
    assert payload[GEOJSON_PATH]["features"] == []


def test_malformed_present_boundary_and_snapshot_still_fail_closed(boundary_root):
    path = boundary_root / "data/geography/municipalities.geojson"
    path.write_text('{"features": []}')
    with pytest.raises(ValueError, match="Empty municipality"):
        result(boundary_root, project())
    with pytest.raises(ValueError, match="snapshot differs"):
        publication_payload(boundary_root, [project()], {"snapshot_id": "wrong"})


def test_stated_barangay_preserves_unambiguous_source_mentions_only(boundary_root):
    p = project()
    p["title"] = "Construction of Brgy. Gueteb FMR, Brgy. Gueteb, Alaminos, Pangasinan"
    row, _ = result(boundary_root, p)
    assert row["stated_barangays"] == [{"name": "Gueteb", "raw": "Brgy. Gueteb", "source_path": "project_or_source_title"}]
    source = p["detail_evidence"][0]["envelope"]["data"]["record"]["house"]
    source["barangay"] = "Exact source name"
    row, _ = result(boundary_root, p)
    assert row["stated_barangays"][0] == {"name": "Exact source name", "raw": "Exact source name",
        "source_path": "detail_evidence.envelope.data.record.house.barangay"}
    assert all("psgc" not in item for item in row["stated_barangays"])
    p["title"] = "Road, Brgy. Nama and Brgy. Palacpalac, Alaminos, Pangasinan"
    source.pop("barangay")
    row, _ = result(boundary_root, p)
    assert row["stated_barangays"] == []


def test_all_approved_data_money_stages_and_original_provenance():
    path = ROOT / "data/national-budget/2027/projects.json"
    raw = path.read_bytes()
    projects = json.loads(raw)
    manifest = json.loads((path.parent / "manifest.json").read_text())
    before = deepcopy(projects)
    payload = publication_payload(ROOT, projects, manifest)
    summary = payload[SUMMARY_PATH]
    assert len(projects) == summary["counts"]["projects"] == 732
    assert summary["counts"]["by_program"] == {"dpwh": 696, "fmr": 32, "hfep": 4}
    assert summary["source_hashes"]["projects"] == hashlib.sha256(raw).hexdigest()
    assert sum(summary["counts"]["by_status"].values()) == 732
    assert len({r["id"] for r in summary["projects"]}) == 732
    assert set(summary["counts"]["by_status"]) <= {
        "plausible", "suspicious", "outside_pangasinan", "name_match_elsewhere", "unavailable", "needs_review"}
    for original, row in zip(projects, summary["projects"]):
        assert row["house_stage"] == original["house_stage"]
        assert row["nep_php"] == original["upstream"]["nep_php"]
        assert row["house_php"] == original["upstream"]["house_php"]
        assert row["geographic_review_status"] == "pending"
    assert projects == before and path.read_bytes() == raw
    assert all(r["segments"] for r in summary["projects"] if r["dataset"] == "fmr")
    json.dumps(payload, allow_nan=False)


@pytest.fixture
def reviewed_project():
    return next(p for p in json.loads((ROOT / "data/national-budget/2027/projects.json").read_text())
                if p["id"] == "dpwh:house-reading:6548")


def reviewed_result(p):
    return publication_payload(ROOT, [p], {"snapshot_id": p["snapshot_id"]})


def test_reviewed_title_comparison_provenance_and_no_duplicate_point(reviewed_project):
    p = reviewed_project
    before = deepcopy(p)
    payload = reviewed_result(p)
    row = payload[SUMMARY_PATH]["projects"][0]
    features = payload[GEOJSON_PATH]["features"]
    assert len(row["segments"]) == 1 and len(features) == 3
    segment = row["segments"][0]
    assert segment["start"] == [119.92525, 6.38299]
    assert segment["end"] == [119.92648, 16.38329]
    assert 1105 < segment["distance_km"] < 1107
    assert "endpoint_distance_over_200km_review" in segment["flags"]
    assert row["display_status"] == "suspicious"
    assert segment["geometry_kind"] == "title_coordinate_comparison"
    assert segment["endpoint_roles_verified"] is False
    assert [f["properties"]["role"] for f in features] == [
        "titleCoordinateFirst", "titleCoordinateSecond", "title_coordinate_comparison"]
    assert all(f["properties"]["geometry_kind"] == "title_coordinate_comparison" for f in features)
    evidence = segment["evidence"][0]
    assert evidence["record_sha256"] == p["record_sha256"]
    assert evidence["snapshot_id"] == p["snapshot_id"]
    assert evidence["raw_tokens"] == ["6.38299", "119.92525", "16.38329", "119.92648"]
    assert [p["title"][start:end] for start, end in evidence["token_spans"]] == evidence["raw_tokens"]
    assert {copy["source_version"] for copy in evidence["title_copies"]} >= {"second", "third"}
    assert row["house_stage"] == "hgab3" and row["house_php"] == 350000000
    assert row["nep_php"] is None and row["geographic_review_status"] == "pending"
    assert p == before
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("change", ["title", "ambiguous", "malformed", "unrelated", "api", "snapshot",
                                    "record", "reading", "detail_api", "unsupported"])
def test_reviewed_interpretation_fails_closed_preserving_api(reviewed_project, change):
    p = reviewed_project
    if change == "title":
        p["title"] += " revised"
    elif change == "ambiguous":
        p["title"] = p["title"].replace("6.38299, 119.92525", "119.92525, 6.38299")
    elif change == "malformed":
        p["title"] = p["title"].replace("16.38329", "NaN")
    elif change == "unrelated":
        p["title"] = "Bridge K6+38299 to K16+38329, 119.92525 + 119.92648"
    elif change == "api":
        p["upstream"]["lat"] = 16.38299
    elif change == "snapshot":
        p["snapshot_id"] += ":changed"
    elif change == "record":
        p["record_sha256"] = "changed"
    elif change == "reading":
        p["detail_evidence"][0]["envelope"]["data"]["record"]["third"]["title"] += " revised"
    elif change == "detail_api":
        p["detail_evidence"][0]["envelope"]["data"]["lat"] = 16.38299
    else:
        p["id"] = "dpwh:house-reading:other"
    payload = reviewed_result(p)
    row = payload[SUMMARY_PATH]["projects"][0]
    features = payload[GEOJSON_PATH]["features"]
    assert len(features) == len(row["segments"]) == 1
    assert features[0]["geometry"]["coordinates"] == [p["upstream"]["lon"], p["upstream"]["lat"]]
    assert features[0]["properties"]["role"] == "api_published_point"
    assert ("stale_or_ambiguous_title_interpretation" in row["location_flags"]) == (change != "unsupported")


def test_derived_counts_hash_and_all_source_files_immutable():
    folder = ROOT / "data/national-budget/2027"
    before = {path: path.read_bytes() for path in folder.glob("*.json")}
    projects = json.loads((folder / "projects.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    payload = publication_payload(ROOT, projects, manifest)
    features = payload[GEOJSON_PATH]["features"]
    assert sum(f["geometry"]["type"] == "Point" for f in features) == 207
    assert sum(f["geometry"]["type"] == "LineString" for f in features) == 33
    assert len({f["properties"]["project_id"] for f in features}) == 174
    assert payload[SUMMARY_PATH]["counts"]["projects"] == 732
    assert payload[SUMMARY_PATH]["files"]["projects.geojson"] == public_file_hash(payload[GEOJSON_PATH])
    assert all(path.read_bytes() == raw for path, raw in before.items())
