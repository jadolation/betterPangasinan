"""Synthetic contracts exercise review gates; none are production approvals."""

from copy import deepcopy
import hashlib
import json
import shutil
from pathlib import Path

import pytest
import build
from scripts.national_budget import pipeline as budget


STAMP = "2026-10-26T10:00:00Z"


def raw_row(identifier="test:one", dataset="dpwh", **changes):
    row = {"id": identifier, "dataset": dataset, "title": "Test project, Mapandan, Pangasinan",
           "nep_php": 44_000_000, "hgab2_php": 44_000_000, "hgab3_php": 44_000_000,
           "house_php": 44_000_000, "api_php": None, "delta_php": 0,
           "flags": [], "held": False, "bridge_group": "unchanged", "status_label": "Same amount in both",
           "office": "Test office", "office_kind": "District engineering offices (DEOs)",
           "pdf_url": {"nep": "https://example.org/nep.pdf#page=1", "hgab2": "https://example.org/house.pdf#page=2", "hgab3": "https://example.org/house3.pdf#page=2"},
           "nep_doc": "test-document", "hgab2_doc": "test-document", "hgab3_doc": "test-document",
           "lat": None, "lon": None}
    row.update(changes)
    return row


def manifest(rows=None, complete=True):
    rows = rows if rows is not None else [raw_row()]
    meta = {"source_commit": "test-commit", "built_at": STAMP, "fiscal_year": 2027,
            "currency": "PHP", "scale": "pesos", "notice": "Independent, unofficial test source.", "house_stage": "hgab3"}
    return {"overview": {"meta": meta, "disclaimers": [{"id": "notice", "body": "Not spending"}],
                         "data": {"documents": [{"key": "test-document", "pdf_url": "https://example.org/nep.pdf"}]}},
            "queries": [{"category": "province", "dataset": "dpwh", "params": {"q": "Pangasinan"},
                         "meta": deepcopy(meta), "disclaimers": [{"id": "notice", "body": "Not spending"}],
                         "rows": rows, "complete": complete, "total": len(rows), "downloaded": len(rows),
                         "unique": len(rows), "response_ids": ["0" * 64]}],
            "offices": [], "retrieved_at": STAMP, "complete": complete,
            "details": [{"dataset": row["dataset"], "id": row["id"], "response_id": "0" * 64,
                         "envelope": {"meta": deepcopy(meta), "data": deepcopy(row), "disclaimers": [{"id": "notice", "body": "Not spending"}]}} for row in rows]}


def decisions(candidates):
    return {"snapshot_id": candidates["snapshot_id"], "candidate_sha256": candidates["candidate_sha256"],
            "reviewer": "Synthetic test reviewer", "reviewed_at": STAMP, "allow_incomplete_coverage": False,
            "offices": [], "lgu_registry": [], "projects": [
                {"id": row["id"], "record_sha256": row["record_sha256"], "decision": "approve",
                 "reviewer": "Synthetic test reviewer", "reviewed_at": STAMP, "evidence_source_ids": ["test-document"],
                 "scope": "geographic", "geographic_review_status": "reviewed", "source_review_status": "reviewed_with_warnings" if row["upstream"]["flags"] else "reviewed",
                 "lgu_associations": []} for row in candidates["projects"]]}


def rehash(candidates):
    candidates["candidate_sha256"] = budget.digest({key: value for key, value in candidates.items() if key != "candidate_sha256"})


def test_dedup_keeps_queries_and_does_not_assign_lgu():
    batch = manifest()
    second = deepcopy(batch["queries"][0])
    second.update(category="office", params={"office": "Test office"})
    batch["queries"].append(second)
    candidate = budget.normalize(batch)
    assert len(candidate["projects"]) == 1
    row = candidate["projects"][0]
    assert len(row["inclusion_reasons"]) == 2
    assert row["lgu_associations"] == []
    assert row["scope"] == "uncertain"
    assert row["geographic_review_status"] == "pending"
    assert candidate["coverage"]["approved_records"] == 0


def test_query_match_is_not_title_evidence_and_shared_lines_not_geographic():
    row = raw_row(title="Region I Medical Center", dataset="hfep")
    batch = manifest([row])
    batch["queries"][0].update(dataset="hfep")
    batch["queries"][0]["meta"]["house_stage"] = "hgab2"
    candidate = budget.normalize(batch)["projects"][0]
    assert candidate["geographic_match_type"] == "ambiguous_or_region_missing"
    shared = budget.normalize(manifest([raw_row(title="Pangasinan; Cebu; other programs", office_kind="Central Office")]))
    assert shared["projects"][0]["scope"] == "shared"


@pytest.mark.parametrize("changes", [
    {"nep_php": True}, {"house_php": 0.5}, {"api_php": -1},
    {"hgab3_php": 2**53}, {"delta_php": 9}, {"lat": 91},
    {"pdf_url": {"nep": "javascript:alert(1)"}}, {"is_mock": True},
    {"nep_php": None, "delta_php": 0}, {"dataset": "unknown"},
])
def test_invalid_upstream_records_remain_collection_errors(changes):
    candidate = budget.normalize(manifest([raw_row(**changes)]))
    assert not candidate["coverage"]["complete"]
    assert candidate["coverage"]["errors"]
    with pytest.raises(ValueError, match="conflicts/errors"):
        budget.compile_snapshot(candidate, decisions(candidate))


def test_unknown_stage_and_snapshot_change_are_not_publishable():
    batch = manifest()
    batch["queries"][0]["meta"]["house_stage"] = "senate"
    assert not budget.normalize(batch)["coverage"]["complete"]
    batch["queries"][0]["meta"]["source_commit"] = "changed"
    assert len(budget.normalize(batch)["coverage"]["errors"]) == 2


def test_conflicting_records_are_not_silently_replaced():
    batch = manifest()
    second = deepcopy(batch["queries"][0])
    second["rows"][0]["title"] = "Changed title"
    batch["queries"].append(second)
    candidate = budget.normalize(batch)
    assert candidate["coverage"]["conflicts"]
    assert len(candidate["projects"]) == 1
    with pytest.raises(ValueError, match="conflicts/errors"):
        budget.compile_snapshot(candidate, decisions(candidate))


def test_null_zero_and_stage_totals_are_distinct():
    candidate = budget.normalize(manifest([raw_row(nep_php=None, delta_php=None), raw_row("test:zero", nep_php=0, house_php=0, hgab2_php=0, hgab3_php=0)]))
    totals = budget.stage_totals(candidate["projects"])["hgab3"]
    assert totals["nep_php"] == 0
    assert totals["nep_php_known_rows"] == 1
    assert totals["nep_php_missing_rows"] == 1
    assert totals["comparable_rows"] == 1
    assert totals["comparable_delta_php"] == 0
    unknown = budget.normalize(manifest([raw_row(nep_php=None, delta_php=None)]))
    assert budget.stage_totals(unknown["projects"])["hgab3"]["nep_php"] is None
    assert budget.stage_totals([]) == {}


def test_compile_requires_exact_human_review_and_keeps_flags():
    candidate = budget.normalize(manifest([raw_row(flags=["nep_evidence_review"])]))
    review = decisions(candidate)
    published = budget.compile_snapshot(candidate, review)
    assert published["projects"][0]["upstream"]["flags"] == ["nep_evidence_review"]
    assert published["manifest"]["status"] == "approved"
    assert "requests" not in published["sources"]
    assert published["manifest"]["files"]["projects.json"] == budget.public_file_hash(published["projects"])
    review["projects"][0]["source_review_status"] = "reviewed"
    with pytest.raises(ValueError, match="flags"):
        budget.compile_snapshot(candidate, review)
    review["projects"][0]["record_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Stale record"):
        budget.compile_snapshot(candidate, review)
    review["candidate_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="Stale snapshot"):
        budget.compile_snapshot(candidate, review)


def test_modified_candidate_cannot_reuse_approval():
    candidate = budget.normalize(manifest())
    review = decisions(candidate)
    candidate["projects"][0]["upstream"]["nep_php"] = 7
    with pytest.raises(ValueError, match="Candidate checksum"):
        budget.compile_snapshot(candidate, review)


def test_incomplete_coverage_requires_explicit_permission():
    candidate = budget.normalize(manifest(complete=False))
    review = decisions(candidate)
    with pytest.raises(ValueError, match="Incomplete"):
        budget.compile_snapshot(candidate, review)
    review["allow_incomplete_coverage"] = True
    assert not budget.compile_snapshot(candidate, review)["coverage"]["complete"]


@pytest.mark.parametrize("error_scope", ["manifest", "query", "inconsistent"])
def test_collection_errors_cannot_be_waived_as_incomplete_coverage(error_scope):
    batch = manifest()
    if error_scope == "manifest":
        batch["errors"] = ["Source snapshot changed"]
        batch["complete"] = False
    else:
        batch["queries"][0]["complete"] = False
        if error_scope == "query":
            batch["queries"][0]["error"] = "Whole-query sum mismatch"
            batch["complete"] = False
    candidate = budget.normalize(batch)
    assert not candidate["coverage"]["complete"]
    assert candidate["coverage"]["errors"]
    review = decisions(candidate)
    review["allow_incomplete_coverage"] = True
    with pytest.raises(ValueError, match="conflicts/errors"):
        budget.compile_snapshot(candidate, review)


def test_missing_evidence_and_unreviewed_geography_rejected():
    candidate = budget.normalize(manifest())
    review = decisions(candidate)
    review["projects"][0]["evidence_source_ids"] = ["missing"]
    with pytest.raises(ValueError, match="Unknown evidence"):
        budget.compile_snapshot(candidate, review)
    review["projects"][0]["evidence_source_ids"] = ["test-document"]
    review["projects"][0]["geographic_review_status"] = "pending"
    with pytest.raises(ValueError, match="Geographic scope"):
        budget.compile_snapshot(candidate, review)


def test_many_lgus_need_reviewed_registry_and_do_not_duplicate_amounts():
    candidate = budget.normalize(manifest())
    review = decisions(candidate)
    for code, name in (("0105530000", "Mapandan"), ("0105529000", "Mangatarem")):
        review["lgu_registry"].append({"psgc": code, "name": name, "source_url": "https://psa.gov.ph/classification/psgc", "release": "test release",
                                       "reviewer": "Synthetic reviewer", "reviewed_at": STAMP})
        review["projects"][0]["lgu_associations"].append({"psgc": code, "name": name, "review_status": "reviewed", "evidence_source_ids": ["test-document"],
                                                        "reviewer": "Synthetic reviewer", "reviewed_at": STAMP})
    published = budget.compile_snapshot(candidate, review)
    assert len(published["projects"]) == 1
    assert len(published["projects"][0]["lgu_associations"]) == 2
    assert published["coverage"]["stage_totals_by_scope"]["geographic"]["hgab3"]["nep_php"] == 44_000_000
    review["lgu_registry"] = []
    with pytest.raises(ValueError, match="registry membership"):
        budget.compile_snapshot(candidate, review)


def test_shared_office_dedup_and_hash_review():
    candidate = budget.normalize(manifest())
    office = {"id": "office:test", "name": "Test", "matched_label": "Test Engineering Office", "district_ids": ["district:2", "district:4"], "tier": "B", "upstream": {"years": []}}
    candidate["offices"] = [office]
    rehash(candidate)
    review = decisions(candidate)
    decision = {"id": office["id"], "sha256": budget.digest(office), "reviewer": "Synthetic reviewer", "reviewed_at": STAMP}
    review["offices"] = [decision]
    assert len(budget.compile_snapshot(candidate, review)["offices"]) == 1
    review["offices"].append(decision)
    with pytest.raises(ValueError, match="duplicate"):
        budget.compile_snapshot(candidate, review)


def test_shared_umbrella_money_cannot_be_promoted_to_geographic_total():
    candidate = budget.normalize(manifest([raw_row(office_kind="Central Office")]))
    review = decisions(candidate)
    with pytest.raises(ValueError, match="Shared allocations"):
        budget.compile_snapshot(candidate, review)
    review["projects"][0]["scope"] = "shared"
    published = budget.compile_snapshot(candidate, review)
    assert published["coverage"]["stage_totals_by_scope"]["geographic"] == {}


def test_mixed_house_readings_are_never_folded_together():
    candidate = budget.normalize(manifest())
    second = deepcopy(candidate["projects"][0])
    second.update(house_stage="hgab2", dataset="fmr")
    totals = budget.stage_totals([*candidate["projects"], second])
    assert set(totals) == {"hgab2", "hgab3"}
    assert totals["hgab2"]["house_php"] == totals["hgab3"]["house_php"] == 44_000_000


def test_exclusions_require_reason_and_do_not_publish():
    candidate = budget.normalize(manifest([raw_row(), raw_row("test:excluded")]))
    review = decisions(candidate)
    excluded = review["projects"][0]
    excluded.update(decision="exclude", exclusion_reason="Reviewed outside geographic scope")
    published = budget.compile_snapshot(candidate, review)
    assert len(published["projects"]) == 1
    assert published["coverage"]["excluded_records"] == 1


def test_missing_pdf_url_blocks_publication_not_internal_preservation():
    candidate = budget.normalize(manifest([raw_row(pdf_url={"nep": None, "hgab3": "https://example.org/h.pdf"})]))
    with pytest.raises(ValueError, match="source PDF"):
        budget.compile_snapshot(candidate, decisions(candidate))


def test_project_details_required_before_publication():
    batch = manifest()
    batch["details"] = []
    candidate = budget.normalize(batch)
    assert candidate["coverage"]["complete"]
    assert not candidate["coverage"]["all_project_details_collected"]
    with pytest.raises(ValueError, match="project-detail evidence"):
        budget.compile_snapshot(candidate, decisions(candidate))


def test_detail_conflicts_block_publication():
    batch = manifest()
    batch["details"][0]["envelope"]["data"]["title"] = "Conflicting detail"
    candidate = budget.normalize(batch)
    assert not candidate["coverage"]["complete"]
    assert candidate["coverage"]["errors"]


def test_zero_response_is_not_zero_funding():
    candidate = budget.normalize(manifest([]))
    assert candidate["coverage"]["unique_records"] == 0
    assert candidate["coverage"]["approved_records"] == 0
    with pytest.raises(ValueError, match="must contain"):
        budget.compile_snapshot(candidate, decisions(candidate))


def test_unavailable_outputs_are_reproducible_and_isolated(tmp_path, monkeypatch):
    payload = budget.publication_payload(tmp_path)
    monkeypatch.setattr(build, "publication_payload", lambda root: payload)
    assert payload["manifest"]["status"] == "unavailable"
    assert payload["projects"] == []
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    national = output / "data" / "national-budget" / "2027"
    assert {path.name for path in national.iterdir()} == {name + ".json" for name in budget.PUBLIC_FILES}
    assert json.loads((national / "manifest.json").read_text())["status"] == "unavailable"
    assert not any(part in {"raw", "review", "approved", "fixtures", "Better_Pangasinan_Research_Batch_01"} for path in output.rglob("*") for part in path.relative_to(output).parts)


def test_approved_build_emits_exact_checksum_bound_files(tmp_path, monkeypatch):
    candidate = budget.normalize(manifest())
    approved = tmp_path / "data" / "national_budget" / "approved"
    budget.write_json(approved / "candidates.json", candidate)
    budget.write_json(approved / "decisions.json", decisions(candidate))
    monkeypatch.setattr(build, "publication_payload", lambda root: budget.publication_payload(tmp_path))
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    directory = output / "data" / "national-budget" / "2027"
    published = budget.read_json(directory / "manifest.json")
    assert published["status"] == "approved"
    for name, expected in published["files"].items():
        assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == expected
    assert len(budget.read_json(directory / "projects.json")) == 1


@pytest.mark.parametrize("mode,compatibility", [("production", True), ("production", False), ("test", True)])
def test_root_budget_mirror_only_for_production_compatibility(tmp_path, monkeypatch, mode, compatibility):
    candidate = budget.normalize(manifest())
    payload = budget.compile_snapshot(candidate, decisions(candidate))
    original_root = build.ROOT
    shutil.copytree(original_root / "schemas", tmp_path / "schemas")
    shutil.copytree(original_root / "data" / "production", tmp_path / "data" / "production")
    shutil.copytree(original_root / "data" / "fixtures", tmp_path / "data" / "fixtures")
    mirror = tmp_path / "data" / "national-budget" / "2027"
    mirror.mkdir(parents=True)
    (mirror / "projects.json").write_bytes(b"existing root publication")
    before = {str(path.relative_to(tmp_path / "data")): path.read_bytes()
              for path in (tmp_path / "data").rglob("*") if path.is_file()}
    monkeypatch.setattr(build, "ROOT", tmp_path)
    monkeypatch.setattr(build, "publication_payload", lambda root: payload)
    output = tmp_path / "public"
    build.build(mode=mode, output=output, root_compatibility=compatibility)
    if mode != "production" or not compatibility:
        assert before == {str(path.relative_to(tmp_path / "data")): path.read_bytes()
                          for path in (tmp_path / "data").rglob("*") if path.is_file()}
        assert not (tmp_path / "national-budget.html").exists()
        return
    assert {path.name for path in mirror.iterdir()} == {f"{name}.json" for name in budget.PUBLIC_FILES}
    for path in mirror.iterdir():
        assert path.read_bytes() == (output / "data" / "national-budget" / "2027" / path.name).read_bytes()
        if path.name != "manifest.json":
            assert hashlib.sha256(path.read_bytes()).hexdigest() == payload["manifest"]["files"][path.name]
    assert not any((tmp_path / "data" / "national-budget" / name).exists() for name in ("raw", "review", "approved"))


def test_bad_approved_inputs_fail_before_replacing_artifact(tmp_path, monkeypatch):
    approved = tmp_path / "data" / "national_budget" / "approved"
    approved.mkdir(parents=True)
    budget.write_json(approved / "decisions.json", {})
    with pytest.raises(ValueError, match="inputs"):
        budget.publication_payload(tmp_path)
    output = tmp_path / "public"
    build.build(output=output, root_compatibility=False)
    marker = output / "keep.txt"
    marker.write_text("retain")
    monkeypatch.setattr(build, "publication_payload", lambda root: budget.publication_payload(tmp_path))
    with pytest.raises(ValueError):
        build.build(output=output, root_compatibility=False)
    assert marker.read_text() == "retain"


def test_mapandan_capture_regression():
    path = Path(__file__).parents[1] / "fixtures" / "national_budget" / "mapandan.json"
    captured = budget.read_json(path)
    rows = captured["data"]["rows"]
    assert {row["id"] for row in rows} == {"house-reading:3959", "house-reading:3923"}
    batch = manifest(rows)
    batch["overview"]["meta"] = captured["meta"]
    batch["overview"]["disclaimers"] = captured["disclaimers"]
    batch["queries"][0]["meta"] = captured["meta"]
    batch["queries"][0]["disclaimers"] = captured["disclaimers"]
    batch["queries"].append(deepcopy(batch["queries"][0]))
    candidate = budget.normalize(batch)
    assert len(candidate["projects"]) == 2
    totals = budget.stage_totals(candidate["projects"])["hgab3"]
    assert totals["nep_php"] == totals["house_php"] == 49_000_000
    assert totals["comparable_delta_php"] == 0
    for row in candidate["projects"]:
        assert row["upstream"]["bridge_group"] == "unchanged"
        assert row["upstream"]["lat"] is None and row["upstream"]["lon"] is None
        assert "contractor" not in row["upstream"] and "implementation_status" not in row["upstream"]
    flagged = next(row for row in candidate["projects"] if row["upstream_id"] == "house-reading:3923")
    assert "nep_evidence_review" in flagged["upstream"]["flags"]


@pytest.mark.parametrize("name", ["project", "office", "batch", "manifest", "review"])
def test_schemas_are_valid(name):
    budget.Draft202012Validator.check_schema(budget.read_json(budget.ROOT / "schemas" / "national_budget" / (name + ".schema.json")))
