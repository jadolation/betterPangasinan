"""Offline P0 review exports never alter approved source inputs."""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from collector.p0 import export_p0
from scripts.national_budget.pipeline import publication_payload

ROOT = Path(__file__).resolve().parents[2]


def protected_hashes():
    folders = ["data/production", "data/national_budget/approved", "data/geography"]
    return {
        str(p): hashlib.sha256(p.read_bytes()).hexdigest()
        for folder in folders
        for p in (ROOT / folder).rglob("*")
        if p.is_file()
    }


def test_p0_outputs_preserve_counts_evidence_and_source_bytes(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError("P0 repository review must remain offline")

    monkeypatch.setattr("socket.create_connection", no_network)
    before = protected_hashes()
    manifest = export_p0(ROOT, tmp_path)
    assert protected_hashes() == before
    assert manifest["coverage_status"] == "partial"
    assert manifest["network_requests"] == 0
    lgus = json.loads((tmp_path / "02_lgu_directory/pangasinan_lgus.json").read_text())
    barangays = json.loads(
        (tmp_path / "02_lgu_directory/pangasinan_barangays.json").read_text()
    )
    assert len(lgus["records"]) == 48
    assert len(barangays["records"]) == 1364
    assert barangays["official"] is False
    assert barangays["psa_release"] is None
    assert "unofficial" in " ".join(barangays["warnings"]).lower()
    assert all(
        r["review_status"] == "pending" for r in lgus["records"] + barangays["records"]
    )
    assert all(
        r["population"] is None and r["missing_fields"]["population"] == "not_collected"
        for r in barangays["records"]
    )
    assert all(
        r["evidence"]["population"]["reference_period"] == "2024-07-01"
        for r in lgus["records"]
    )
    overview = json.loads(
        (tmp_path / "01_provincial_overview/pangasinan_overview.json").read_text()
    )
    assert overview["fields"]["population"]["value"] == 3188540
    assert overview["fields"]["administrative_region"]["value"] is None
    assert (
        overview["fields"]["administrative_region"]["missing_reason"] == "not_collected"
    )
    with (
        tmp_path / "05_national_budget_2027/national_budget_2027_review.csv"
    ).open() as handle:
        review = list(csv.DictReader(handle))
    assert len(review) == 732
    assert {
        "nep_php",
        "hgab2_php",
        "hgab3_php",
        "house_stage",
        "record_sha256",
    } <= review[0].keys()
    originals = {row["id"]: row for row in publication_payload(ROOT)["projects"]}
    for row in review:
        original = originals[row["id"]]
        assert row["house_stage"] == original["house_stage"]
        assert row["record_sha256"] == original["record_sha256"]
        for stage in ("nep_php", "hgab2_php", "hgab3_php"):
            value = original["upstream"][stage]
            assert row[stage] == ("" if value is None else str(value))
    candidates = json.loads(
        (
            tmp_path / "05_national_budget_2027/project_geographic_candidates.json"
        ).read_text()
    )
    assert len(candidates["records"]) == 732
    assert all(
        row["review_status"] == "pending" and not row["lgu_associations"]
        for row in candidates["records"]
    )
    namesake = next(r for r in candidates["records"] if "Koronadal" in r["title"])
    assert namesake["scope"] == "uncertain"
    assert manifest["inputs"] and manifest["outputs"]
    for relative, digest in manifest["outputs"].items():
        assert hashlib.sha256((tmp_path / relative).read_bytes()).hexdigest() == digest


def test_p0_rerun_deterministic(tmp_path):
    export_p0(ROOT, tmp_path)
    before = {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }
    export_p0(ROOT, tmp_path)
    assert before == {
        str(p.relative_to(tmp_path)): p.read_bytes()
        for p in tmp_path.rglob("*")
        if p.is_file()
    }


def test_p0_refuses_production_destination():
    with pytest.raises(ValueError):
        export_p0(ROOT, ROOT / "data/production")


def test_review_metadata_preserves_unknown_retrieval_and_original_transcription(
    tmp_path,
):
    manifest = export_p0(ROOT, tmp_path)
    lgus = json.loads((tmp_path / "02_lgu_directory/pangasinan_lgus.json").read_text())
    starter = json.loads((ROOT / "pangasinan_lgu_registry_staging.json").read_text())
    originals = {r["psgc"]: r for r in starter["lgus"]}
    for row in lgus["records"]:
        assert row["original_source_row"] == originals[row["psgc"]]
        assert row["retrieved_at"] is None
        assert row["source_published_at"] is None
        assert row["license"] is None and row["redistribution_review"] == "pending"
        assert row["collection_run_id"] == manifest["collection_run_id"]
        assert row["source_record_id"] == row["psgc"]
        assert (
            row["evidence"]["population"]["source_kind"]
            == "user_reviewed_transcription"
        )
        assert row["evidence"]["population"]["independently_verified"] is False
        assert row["evidence"]["population"]["source_agencies"] == [
            "Philippine Statistics Authority"
        ]
    with (
        tmp_path / "05_national_budget_2027/budget_source_inventory.csv"
    ).open() as handle:
        documents = [
            r for r in csv.DictReader(handle) if r["stage"] in ("nep", "hgab2", "hgab3")
        ]
    assert documents and all(
        r["retrieved_at"] == "" and r["snapshot_retrieved_at"] for r in documents
    )


def test_unavailable_barangay_snapshot_does_not_become_zero(tmp_path, monkeypatch):
    from collector import p0

    actual = p0.geography_payload(ROOT)
    actual["data/geography/barangays.json"] = []
    actual["data/geography/manifest.json"]["barangay_status"] = "unavailable"
    monkeypatch.setattr(p0, "geography_payload", lambda root: actual)
    export_p0(ROOT, tmp_path)
    lgus = json.loads((tmp_path / "02_lgu_directory/pangasinan_lgus.json").read_text())
    assert all(r["barangay_count_in_snapshot"] is None for r in lgus["records"])
    assert all(
        r["missing_fields"]["barangay_count_in_snapshot"] == "not_collected"
        for r in lgus["records"]
    )


def test_lgu_districts_reuse_existing_validated_official_listing(tmp_path):
    from scripts.government_directory import publication_payload as government_payload

    government = government_payload(ROOT)["data/government-leadership.json"]
    districts = {
        code: district
        for district in government["districts"]
        for code in district["lgu_psgcs"]
    }
    source = next(row for row in government["sources"] if row["id"] == "districts")
    manifest = export_p0(ROOT, tmp_path)
    lgus = json.loads((tmp_path / "02_lgu_directory/pangasinan_lgus.json").read_text())[
        "records"
    ]
    assert len(lgus) == len(districts) == 48
    assert {r["legislative_district"]["number"] for r in lgus} == set(range(1, 7))
    for row in lgus:
        assert row["legislative_district"] == districts[row["psgc"]]
        assert "legislative_district" not in row["missing_fields"]
        evidence = row["evidence"]["legislative_district"]
        assert evidence["source_url"] == source["url"]
        assert evidence["source_sha256"] == source["sha256"]
        assert evidence["retrieved_at"] == source["retrieved_at"]
        assert evidence["original_district"] == districts[row["psgc"]]
        assert evidence["source_published_at"] is None
        assert evidence["reference_period"] is None
    input_file = "data/production/government_directory.json"
    assert manifest["inputs"][input_file] == checksum_file(ROOT / input_file)
    with (tmp_path / "source_inventory.csv").open() as handle:
        inventory = list(csv.DictReader(handle))
    district_source = next(
        r for r in inventory if r["source_id"] == "government-directory:districts"
    )
    assert district_source["source_sha256"] == source["sha256"]
    assert district_source["retrieved_at"] == source["retrieved_at"]
    with (tmp_path / "collection_gaps.csv").open() as handle:
        assert all(
            "legislative_district" not in r["field"] for r in csv.DictReader(handle)
        )
    with (tmp_path / "02_lgu_directory/lgu_directory.csv").open() as handle:
        assert all(r["legislative_district"] for r in csv.DictReader(handle))


def checksum_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_overview_reuses_saved_official_land_area_and_general_location(tmp_path):
    from scripts.provincial_reference import publication_payload as provincial_payload

    reference = provincial_payload(ROOT)["data/provincial-reference.json"]
    page = next(p for p in reference["official_pages"] if p["id"] == "about")
    manifest = export_p0(ROOT, tmp_path)
    fields = json.loads(
        (tmp_path / "01_provincial_overview/pangasinan_overview.json").read_text()
    )["fields"]
    assert fields["land_area"]["value"] == 536818
    assert fields["land_area"]["unit"] == "hectares"
    assert fields["land_area"]["approximate"] is True
    assert fields["land_area"]["raw_value"] == next(
        t for t in page["text"] if t.startswith("Covering approximately")
    )
    assert fields["general_location"]["value"] == next(
        t for t in page["text"] if t.startswith("Pangasinan is bounded on")
    )
    for field in ("land_area", "general_location"):
        evidence = fields[field]["evidence"]
        assert evidence["source_url"] == page["source_url"]
        assert evidence["retrieved_at"] == page["collected_at"]
        assert evidence["reference_period"] is None
        assert evidence["source_published_at"] is None
        assert (
            evidence["artifact_path"] == "data/provincial_reference/official_pages.json"
        )
        assert evidence["artifact_sha256"] == checksum_file(
            ROOT / evidence["artifact_path"]
        )
        assert (
            evidence["hash_scope"]
            == "saved_extracted_page_collection_not_original_html"
        )
        assert evidence["source_page_id"] == "about"
    assert fields["coordinates"]["value"] is None
    assert fields["administrative_region"]["value"] is None
    assert "data/provincial_reference/official_pages.json" in manifest["inputs"]
    with (tmp_path / "collection_gaps.csv").open() as handle:
        assert all(r["field"] != "land_area" for r in csv.DictReader(handle))


def test_unexpected_saved_area_layout_remains_unknown(tmp_path, monkeypatch):
    from collector import p0

    actual = p0.provincial_payload(ROOT)
    page = next(
        p
        for p in actual["data/provincial-reference.json"]["official_pages"]
        if p["id"] == "about"
    )
    page["text"] = [
        t.replace("536,818 hectares", "an unspecified area") for t in page["text"]
    ]
    monkeypatch.setattr(p0, "provincial_payload", lambda root: actual)
    export_p0(ROOT, tmp_path)
    fields = json.loads(
        (tmp_path / "01_provincial_overview/pangasinan_overview.json").read_text()
    )["fields"]
    assert fields["land_area"]["value"] is None
    assert fields["land_area"]["missing_reason"] == "source_layout_unrecognized"
