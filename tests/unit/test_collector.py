import hashlib
import json
import socket
from pathlib import Path

import pytest

from tests.support.synthetic_collector import collect, extract_psgc
from collector.exporters import export_run, safe_target
from collector.persistence import Store

FIXTURE = Path(__file__).parents[1] / "fixtures/collector/psgc_sample.xlsx"


def test_offline_end_to_end_and_rerun(tmp_path, monkeypatch):
    monkeypatch.setattr(
        socket, "socket", lambda *a, **k: pytest.fail("network in fixture mode")
    )
    store = Store(tmp_path / "stage.sqlite")
    first = collect(FIXTURE, tmp_path / "raw", store)
    second = collect(FIXTURE, tmp_path / "raw", store)
    assert first["run_id"] != second["run_id"]
    assert second["stage"]["new_versions"] == 0
    assert (
        first["artifact"]["sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    )
    assert all(
        r["is_mock"] and r["review_status"] == "pending" for r in first["records"]
    )
    assert all(
        r["data"]["population"] is None
        and r["missing_fields"]["population"] == "not_collected"
        for r in first["records"]
    )
    manifest = export_run(first, tmp_path / "review")
    assert manifest["coverage_status"] == "partial"
    assert (tmp_path / "review/collection_gaps.csv").exists()
    assert (
        len(
            json.loads((tmp_path / "review/pangasinan_lgus.json").read_text())[
                "records"
            ]
        )
        == 2
    )


def test_changed_artifact_preserves_history(tmp_path):
    from openpyxl import load_workbook

    store = Store(tmp_path / "stage.sqlite")
    first = collect(FIXTURE, tmp_path / "raw", store)
    book = load_workbook(FIXTURE)
    book["PSGC_MOCK_V1"]["B3"] = "Fictional Changed City"
    changed = tmp_path / "changed.xlsx"
    book.save(changed)
    second = collect(changed, tmp_path / "raw", store)
    assert first["artifact"]["sha256"] != second["artifact"]["sha256"]
    assert store.report(first["run_id"])["records"] == first["records"]
    assert second["changes"]["changed"]


@pytest.mark.parametrize(
    "case", ["duplicate", "parent", "header", "integer-code", "formula", "blank-name"]
)
def test_bad_workbooks_are_audited(tmp_path, case):
    from openpyxl import load_workbook

    book = load_workbook(FIXTURE)
    sheet = book["PSGC_MOCK_V1"]
    if case == "duplicate":
        sheet.append([c.value for c in sheet[3]])
    if case == "blank-name":
        sheet["B3"] = "   "
    if case == "parent":
        sheet["D5"] = "TEST_MISSING"
    if case == "header":
        sheet["A1"] = "Unexpected"
    if case == "integer-code":
        sheet["A3"] = 1055
    if case == "formula":
        sheet["B3"] = '=HYPERLINK("bad")'
    path = tmp_path / "bad.xlsx"
    book.save(path)
    run = collect(path, tmp_path / "raw", Store(tmp_path / "stage.sqlite"))
    assert run["quality"]["validation_status"] == "invalid"
    assert run["quality"]["errors"]
    assert run["stage"]["new_versions"] == 0


def test_unknown_values_preserved():
    rows = extract_psgc(FIXTURE.read_bytes())["rows"]
    assert rows[0]["raw_values"]["Notes"] == "is_mock: true; synthetic only"


def test_production_destinations_rejected():
    for path in [
        "data/production",
        "public/data",
        "data/national_budget/approved",
        "data/national-budget/2027",
    ]:
        with pytest.raises(ValueError):
            safe_target(Path(path))


def test_missing_source_audited(tmp_path):
    store = Store(tmp_path / "stage.sqlite")
    run = collect(tmp_path / "missing.xlsx", tmp_path / "raw", store)
    assert run["quality"]["validation_status"] == "invalid"
    assert run["artifact"]["sha256"] is None
    assert store.report(run["run_id"])["quality"]["errors"]


def test_corrupt_preserved_artifact_not_overwritten(tmp_path):
    store = Store(tmp_path / "stage.sqlite")
    run = collect(FIXTURE, tmp_path / "raw", store)
    artifact = Path(run["artifact"]["path"])
    artifact.write_bytes(b"corrupted")
    failed = collect(FIXTURE, tmp_path / "raw", store)
    assert failed["quality"]["validation_status"] == "invalid"
    assert artifact.read_bytes() == b"corrupted"


def test_csv_formula_and_symlink_output(tmp_path):
    import csv
    from collector.exporters import write_csv, write_json

    path = tmp_path / "safe.csv"
    write_csv(path, [{"name": ' \t=HYPERLINK("evil")'}], ["name"])
    with path.open() as handle:
        row = list(csv.DictReader(handle))[0]
    assert row["name"].startswith("'")
    path = tmp_path / "escape"
    path.symlink_to(
        Path(__file__).resolve().parents[2] / "data/production",
        target_is_directory=True,
    )
    with pytest.raises(ValueError):
        write_json(path / "unsafe.json", {})


def test_change_report_marks_only_changed_values(tmp_path):
    from openpyxl import load_workbook

    store = Store(tmp_path / "stage.sqlite")
    collect(FIXTURE, tmp_path / "raw", store)
    book = load_workbook(FIXTURE)
    book["PSGC_MOCK_V1"]["B3"] = "Changed Fictional City"
    path = tmp_path / "changed.xlsx"
    book.save(path)
    run = collect(path, tmp_path / "raw", store)
    assert run["changes"]["changed"] == ["geographic_unit:psgc:9900001000"]


def test_revalidation_checks_typed_values(tmp_path):
    from collector.pipeline import validate_records

    run = collect(FIXTURE, tmp_path / "raw", Store(tmp_path / "stage.sqlite"))
    run["records"][0]["data"]["population"] = -10
    assert validate_records(run["records"])["validation_status"] == "invalid"
