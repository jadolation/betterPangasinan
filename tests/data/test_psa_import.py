from copy import deepcopy
import hashlib
import json

import pytest

import build
from scripts.import_psa_lgus import ROOT, normalize, publish
from scripts.site_data import publication_payloads


def starter():
    raw = (ROOT / "pangasinan_lgu_registry_staging.json").read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def test_import_preserves_all_supplied_records_and_reference_dates(tmp_path):
    raw, checksum = starter()
    bundle = normalize(raw, checksum, "2026-11-01")
    assert len(bundle["lgus"]) == 48
    assert sum(row["classification"] == "city" for row in bundle["lgus"]) == 4
    assert sum(row["population"] for row in bundle["lgus"]) == 3188540
    for before, after in zip(raw["lgus"], bundle["lgus"]):
        assert before["name"] == after["name"]
        assert before["psgc"] == after["psgc"]
        assert before["population_2024"] == after["population"]
        assert after["population_reference_date"] == "2024-07-01"
        assert after["psgc_release"] == "2025-07-31"
        assert after["collection_status"] == before["review_status"]
        assert after["source_sha256"] == checksum
    publish(bundle, tmp_path)
    first = {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    publish(bundle, tmp_path)
    assert first == {path.name: path.read_bytes() for path in tmp_path.iterdir()}
    graph = build.load_data(tmp_path)
    assert len(graph["lgus"]) == 48
    payload = publication_payloads(ROOT, graph, data_dir=tmp_path)
    profile = payload["data/province-profile.json"]["profile"]
    assert profile["lgu_count"] == 48 and profile["cities"] == 4 and profile["municipalities"] == 44


@pytest.mark.parametrize("change", ["duplicate", "integer-code", "population", "classification", "release", "source"])
def test_invalid_or_inconsistent_starter_rejected(change):
    raw, checksum = starter()
    raw = deepcopy(raw)
    if change == "duplicate": raw["lgus"][1]["psgc"] = raw["lgus"][0]["psgc"]
    if change == "integer-code": raw["lgus"][0]["psgc"] = 105503000
    if change == "population": raw["lgus"][0]["population_2024"] += 1
    if change == "classification": raw["lgus"][0]["classification"] = "municipality"
    if change == "release": raw["lgus"][0]["psgc_release"] = "2024-07-01"
    if change == "source": raw["metadata"]["url"] = "http://evil.invalid"
    with pytest.raises(ValueError): normalize(raw, checksum, "2026-11-01")


def test_province_summary_must_reconcile_with_published_registry(tmp_path):
    raw, checksum = starter()
    bundle = normalize(raw, checksum, "2026-11-01")
    publish(bundle, tmp_path)
    graph = build.load_data(tmp_path)
    graph["lgus"][0]["population"] += 1
    with pytest.raises(ValueError, match="reconcile"):
        publication_payloads(ROOT, graph, data_dir=tmp_path)


def test_preview_is_explicit_real_data_and_never_accepts_private_mocks(tmp_path):
    with pytest.raises(ValueError, match="Preview mode"):
        build.load_data(ROOT / "data/fixtures", "preview")
    output = tmp_path / "preview"
    build.build("preview", output, root_compatibility=False)
    html = (output / "index.html").read_text()
    assert 'content="preview"' in html and "Development preview" in html
    assert len(json.loads((output / "data/lgus.json").read_text())) == 48


def test_real_draft_records_preview_without_weakening_production(tmp_path):
    raw, checksum = starter()
    bundle = normalize(raw, checksum, "2026-11-01")
    directory = tmp_path / "staging"
    publish(bundle, directory)
    records = json.loads((directory / "lgus.json").read_text())
    for row in records:
        row.update(publication_status="draft", verification_status="unreviewed")
    (directory / "lgus.json").write_text(json.dumps(records))
    assert len(build.load_data(directory, "preview")["lgus"]) == 48
    with pytest.raises(ValueError, match="Production rejects"):
        build.load_data(directory, "production")
    output = tmp_path / "preview"
    build.build("preview", output, directory, root_compatibility=False)
    payload = json.loads((output / "data/province-profile.json").read_text())
    assert payload["status"] == "preview"
