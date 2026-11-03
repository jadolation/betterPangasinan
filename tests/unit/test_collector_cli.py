import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests/fixtures/collector/psgc_sample.xlsx"


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "collector.cli", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def test_cli_collect_validate_export_report(tmp_path):
    base = ["--state-dir", tmp_path]
    result = invoke(
        "collect",
        "--source",
        "psa_psgc",
        "--fixture",
        FIXTURE,
        "--environment",
        "test",
        *base,
    )
    assert result.returncode == 0, result.stderr
    run_id = json.loads(result.stdout)["run_id"]
    for command in ("validate", "report"):
        result = invoke(command, "--source", "psa_psgc", "--run-id", run_id, *base)
        assert result.returncode == 0, result.stderr
    target = tmp_path / "export"
    result = invoke(
        "export",
        "--source",
        "psa_psgc",
        "--run-id",
        run_id,
        "--format",
        "json,csv",
        "--target",
        target,
        *base,
    )
    assert result.returncode == 0, result.stderr
    assert (target / "manifest.json").exists()


def test_cli_invalid_fixture_nonzero_and_still_audited(tmp_path):
    broken = tmp_path / "bad.xlsx"
    broken.write_text("<html>not a spreadsheet</html>")
    result = invoke(
        "collect",
        "--source",
        "psa_psgc",
        "--fixture",
        broken,
        "--environment",
        "test",
        "--state-dir",
        tmp_path / "state",
    )
    assert result.returncode == 1
    report = json.loads(result.stdout)
    assert report["quality"]["validation_status"] == "invalid"
    assert report["run_id"]


def test_cli_has_no_publication_or_live_mode(tmp_path):
    for args in [
        ("publish",),
        ("collect", "--source", "psa_psgc", "--environment", "production"),
        (
            "collect",
            "--source",
            "psa_psgc",
            "--fixture",
            FIXTURE,
            "--environment",
            "test",
            "--state-dir",
            ROOT / "data/production",
        ),
    ]:
        result = invoke(*args)
        assert result.returncode != 0


def test_mock_cannot_enter_existing_publication_gate(tmp_path):
    import build
    from collector.pipeline import collect
    from collector.persistence import Store

    run = collect(FIXTURE, tmp_path / "raw", Store(tmp_path / "staging.sqlite"))
    directory = tmp_path / "dataset"
    directory.mkdir()
    assert all(row["is_mock"] for row in run["records"])
    (directory / "entities.json").write_text("[]")
    (directory / "sources.json").write_text(
        (ROOT / "data/production/sources.json").read_text()
    )
    compatible = json.loads((ROOT / "data/production/lgus.json").read_text())[0]
    compatible.update(id="mock-" + compatible["id"], is_mock=True)
    (directory / "lgus.json").write_text(json.dumps([compatible]))
    import pytest

    with pytest.raises(ValueError, match="Production rejects mock"):
        build.load_data(directory, "production")
