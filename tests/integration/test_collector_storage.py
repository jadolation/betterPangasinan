import os

import pytest
from sqlalchemy import func, select

from collector.persistence import Store, artifacts, record_versions, runs


def record(name="Fixture City", checksum="a" * 64):
    return {
        "id": "lgu:psgc:TEST_001",
        "source_id": "psa_psgc",
        "name": name,
        "artifact_sha256": checksum,
        "review_status": "pending",
        "is_mock": True,
        "retrieved_at": "2026-11-03T00:00:00Z",
        "collection_run_id": "first",
    }


def stage(store, run_id, records=None, checksum="a" * 64, valid=True):
    return store.stage(
        [record(checksum=checksum)] if records is None else records,
        {"sha256": checksum, "path": "/private/raw/" + checksum},
        {"run_id": run_id, "source_id": "psa_psgc"},
        {"validation_status": "valid" if valid else "invalid"},
    )


def count(store, table):
    with store.engine.connect() as connection:
        return connection.scalar(select(func.count()).select_from(table))


def test_identical_rerun_keeps_one_version_and_distinct_audit(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    first = stage(store, "first")
    row = record()
    row.update(collection_run_id="second", retrieved_at="2026-11-03T01:00:00Z")
    second = stage(store, "second", [row])
    assert first["created_versions"] == 1
    assert second["created_versions"] == 0
    assert count(store, record_versions) == 1
    assert count(store, artifacts) == 1
    assert count(store, runs) == 2
    assert store.report("first")["records"][0]["collection_run_id"] == "first"
    assert store.latest("psa_psgc")["run"]["run_id"] == "second"


def test_changed_artifact_preserves_previous_versions_and_reports_changes(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    stage(store, "first")
    changed = record("Changed Fixture City", "b" * 64)
    result = stage(store, "second", [changed], checksum="b" * 64)
    assert result["changes"]["changed"] == [changed["id"]]
    assert count(store, record_versions) == 2
    assert count(store, artifacts) == 2
    assert store.report("first")["records"][0]["name"] == "Fixture City"
    assert store.report("second")["records"][0]["name"] == "Changed Fixture City"
    result = stage(store, "third", [], checksum="c" * 64)
    assert result["changes"]["removed"] == [changed["id"]]


def test_invalid_quality_retains_audit_but_not_entity_versions(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    stage(store, "first", valid=False)
    assert count(store, record_versions) == 0
    assert store.report("first")["quality"]["validation_status"] == "invalid"
    assert len(store.report("first")["records"]) == 1
    assert store.latest("psa_psgc") is None


def test_approval_cannot_be_written_and_duplicate_run_is_atomic(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    approved = record()
    approved["review_status"] = "approved"
    with pytest.raises(ValueError, match="pending"):
        stage(store, "bad", [approved])
    assert count(store, runs) == 0
    stage(store, "first")
    with pytest.raises(ValueError, match="run"):
        stage(store, "first", checksum="b" * 64)
    assert count(store, artifacts) == 1
    assert count(store, record_versions) == 1


def test_duplicate_ids_and_changed_artifact_metadata_rejected(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    with pytest.raises(ValueError, match="Duplicate"):
        stage(store, "bad", [record(), record()])
    stage(store, "first")
    with pytest.raises(ValueError, match="artifact"):
        store.stage(
            [record()],
            {"sha256": "a" * 64, "path": "changed"},
            {"run_id": "second", "source_id": "psa_psgc"},
            {"validation_status": "valid"},
        )
    assert count(store, runs) == 1


@pytest.mark.skipif(
    not os.environ.get("COLLECTOR_TEST_DATABASE_URL"),
    reason="Disposable PostgreSQL URL not supplied",
)
def test_disposable_postgres_migration_and_idempotency(tmp_path):
    from alembic import command
    from alembic.config import Config

    config = Config("migrations/alembic.ini")
    config.set_main_option("sqlalchemy.url", os.environ["COLLECTOR_TEST_DATABASE_URL"])
    command.upgrade(config, "head")
    store = Store(os.environ["COLLECTOR_TEST_DATABASE_URL"])
    from pathlib import Path
    from collector.pipeline import collect
    from collector.exporters import export_run

    source_path = (
        Path(__file__).resolve().parents[2] / "pangasinan_lgu_registry_staging.json"
    )
    first = collect(source_path, tmp_path / "raw", store)
    second = collect(source_path, tmp_path / "raw", store)
    assert first["stage"]["new_versions"] == 49
    assert second["stage"]["new_versions"] == 0
    assert count(store, record_versions) == 49
    manifest = export_run(second, tmp_path / "review")
    assert manifest["is_mock"] is False
    assert manifest["coverage_status"] == "partial"
    with store.engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT PostGIS_Version()").scalar()


def test_failed_acquisition_is_audited_without_invented_artifact(tmp_path):
    store = Store(tmp_path / "staging.sqlite")
    result = store.stage(
        [],
        {"sha256": None, "path": None},
        {"run_id": "failed", "source_id": "psa_psgc"},
        {"validation_status": "invalid", "source_errors": ["FILE_NOT_FOUND"]},
    )
    assert result["created_versions"] == 0
    assert count(store, artifacts) == 0
    assert store.report("failed")["artifact"]["sha256"] is None
    assert store.latest("psa_psgc") is None
