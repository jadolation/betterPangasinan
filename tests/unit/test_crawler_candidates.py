import json
from pathlib import Path
import pytest
from collector.candidates import export_candidates

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / "data/staging/web-crawler/psa-geography-20261109-01"


def test_changed_capture_is_rejected(tmp_path):
    (tmp_path / "manifest.json").write_text(
        json.dumps({"errors": [], "files": {"page-1/response.redacted.raw": "0" * 64}})
    )
    page = tmp_path / "page-1"
    page.mkdir()
    (page / "response.redacted.raw").write_text("{}")
    with pytest.raises(ValueError, match="checksum"):
        export_candidates(tmp_path, tmp_path / "out")
    assert not (tmp_path / "out").exists()


def test_exports_are_deterministic_drafts_from_captures(tmp_path):
    import hashlib

    run = tmp_path / "run"
    page = run / "page-1"
    page.mkdir(parents=True)
    base = dict(version="Q2_2024", reg=1, prv=55, populations=[])
    rows = [
        dict(base, code="0105500000", area_name="Pangasinan", geographic_level="Prov"),
        dict(
            base,
            code="0105501000",
            area_name="Synthetic test municipality",
            geographic_level="Mun",
            populations=[dict(psgc="0105501000", year=2024, population="1,234")],
        ),
    ]
    raw = page / "response.redacted.raw"
    raw.write_text(json.dumps(dict(count=2, next=None, results=rows)))
    checksum = hashlib.sha256(raw.read_bytes()).hexdigest()
    (run / "manifest.json").write_text(
        json.dumps(
            dict(
                errors=[],
                files={"page-1/response.redacted.raw": checksum},
                sources=[
                    dict(
                        status=200,
                        artifact_sha256=checksum,
                        source_url="https://classification.psa.gov.ph/psgc/Q2_2024/all",
                        retrieved_at="2026-11-09T00:00:00Z",
                        artifact_redacted=True,
                    )
                ],
            )
        )
    )
    a = export_candidates(run, tmp_path / "a")
    b = export_candidates(run, tmp_path / "b")
    assert a["files"] == b["files"]
    lgu = json.loads((tmp_path / "a/lgus.json").read_text())[0]
    assert lgu["publication_status"] == "draft"
    assert lgu["population"] == 1234
    assert lgu["population_reference_date"] is None
    with pytest.raises(ValueError, match="fresh"):
        export_candidates(run, tmp_path / "a")
