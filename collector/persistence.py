"""Transactional, append-only staging; SQLite is an isolated prototype backend."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    event,
    insert,
    select,
)
from sqlalchemy.exc import IntegrityError

metadata = MetaData()
artifacts = Table(
    "collector_raw_artifacts",
    metadata,
    Column("sha256", String(64), primary_key=True),
    Column("metadata", JSON, nullable=False),
)
entities = Table(
    "collector_entities",
    metadata,
    Column("id", String(200), primary_key=True),
    Column("source_id", String(100), nullable=False),
)
record_versions = Table(
    "collector_record_versions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("entity_id", ForeignKey("collector_entities.id"), nullable=False),
    Column("version_sha256", String(64), nullable=False),
    Column(
        "artifact_sha256", ForeignKey("collector_raw_artifacts.sha256"), nullable=False
    ),
    Column("record", JSON, nullable=False),
    UniqueConstraint("entity_id", "version_sha256", name="uq_collector_entity_version"),
)
runs = Table(
    "collector_runs",
    metadata,
    Column("sequence", Integer, primary_key=True),
    Column("run_id", String(100), nullable=False, unique=True),
    Column("source_id", String(100), nullable=False),
    Column(
        "artifact_sha256", ForeignKey("collector_raw_artifacts.sha256"), nullable=True
    ),
    Column("status", String(20), nullable=False),
    Column("report", JSON, nullable=False),
)


def version_hash(record: dict[str, Any], *, include_evidence: bool = True) -> str:
    """Acquisition timestamps and workflow state are not entity changes."""
    ignored = {
        "collection_run_id",
        "retrieved_at",
        "validation_status",
        "review_status",
    }

    if not include_evidence:
        ignored |= {"artifact_sha256", "evidence", "version"}

    def stable(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                key: stable(item) for key, item in value.items() if key not in ignored
            }
        if isinstance(value, list):
            return [stable(item) for item in value]
        return value

    return hashlib.sha256(
        json.dumps(
            stable(record), sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


class Store:
    def __init__(self, path_or_url: str | Path = Path("data/staging/collector.sqlite")):
        value = str(path_or_url)
        if "://" not in value:
            path = Path(value)
            path.parent.mkdir(parents=True, exist_ok=True)
            value = "sqlite:///" + str(path)
        self.engine = create_engine(value)
        if self.engine.dialect.name == "sqlite":

            @event.listens_for(self.engine, "connect")
            def enable_foreign_keys(connection: Any, _: Any) -> None:
                connection.execute("PRAGMA foreign_keys=ON")

            metadata.create_all(self.engine)
        elif self.engine.dialect.name != "postgresql":
            raise ValueError("Only PostgreSQL or isolated SQLite staging is supported")
        # PostgreSQL schema creation belongs to Alembic and a separate migration role.

    def stage(
        self,
        records: list[dict[str, Any]],
        artifact: dict[str, Any],
        run: dict[str, Any],
        quality: dict[str, Any],
    ) -> dict[str, Any]:
        if any(row.get("review_status") != "pending" for row in records):
            raise ValueError("Collector can stage pending records only")
        invalid = (
            quality.get("validation_status") == "invalid"
            or quality.get("status") == "invalid"
            or quality.get("valid") is False
        )
        identifiers = [row["id"] for row in records]
        if not invalid and len(identifiers) != len(set(identifiers)):
            raise ValueError("Duplicate record IDs cannot create versions")
        checksum = artifact["sha256"]
        if checksum is None and not invalid:
            raise ValueError("Only failed acquisition may omit an artifact")
        if checksum is not None and (
            len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum)
        ):
            raise ValueError("Invalid artifact SHA-256")
        previous = self.latest(run["source_id"])
        prior_rows = {row["id"]: row for row in previous["records"]} if previous else {}
        current = {row["id"]: row for row in records}
        changes = {
            "added": sorted(current.keys() - prior_rows.keys()) if not invalid else [],
            "removed": sorted(prior_rows.keys() - current.keys())
            if not invalid
            else [],
            "changed": sorted(
                key
                for key in current.keys() & prior_rows.keys()
                if version_hash(current[key], include_evidence=False)
                != version_hash(prior_rows[key], include_evidence=False)
            )
            if not invalid
            else [],
        }
        result: dict[str, Any] = {
            "run": deepcopy(run),
            "artifact": deepcopy(artifact),
            "records": deepcopy(records),
            "quality": deepcopy(quality),
            "changes": changes,
            "created_versions": 0,
        }
        try:
            with self.engine.begin() as connection:
                if connection.scalar(
                    select(runs.c.run_id).where(runs.c.run_id == run["run_id"])
                ):
                    raise ValueError("Collection run already exists")
                stored = connection.scalar(
                    select(artifacts.c.metadata).where(artifacts.c.sha256 == checksum)
                )
                if stored is None and checksum is not None:
                    connection.execute(
                        insert(artifacts).values(sha256=checksum, metadata=artifact)
                    )
                elif stored is not None and stored.get("path") != artifact.get("path"):
                    raise ValueError("Existing artifact location is immutable")
                if not invalid:
                    for row in records:
                        if (
                            row.get("artifact_sha256") != checksum
                            or row.get("source_id") != run["source_id"]
                        ):
                            raise ValueError("Record source/artifact differs from run")
                        owner = connection.scalar(
                            select(entities.c.source_id).where(
                                entities.c.id == row["id"]
                            )
                        )
                        if owner is None:
                            connection.execute(
                                insert(entities).values(
                                    id=row["id"], source_id=run["source_id"]
                                )
                            )
                        elif owner != run["source_id"]:
                            raise ValueError("Entity belongs to another source")
                        digest = version_hash(row)
                        exists = connection.scalar(
                            select(record_versions.c.id).where(
                                record_versions.c.entity_id == row["id"],
                                record_versions.c.version_sha256 == digest,
                            )
                        )
                        if exists is None:
                            connection.execute(
                                insert(record_versions).values(
                                    entity_id=row["id"],
                                    version_sha256=digest,
                                    artifact_sha256=checksum,
                                    record=row,
                                )
                            )
                            result["created_versions"] += 1
                connection.execute(
                    insert(runs).values(
                        run_id=run["run_id"],
                        source_id=run["source_id"],
                        artifact_sha256=checksum,
                        status="invalid" if invalid else "valid",
                        report=result,
                    )
                )
        except IntegrityError as error:
            raise ValueError(
                "Conflicting run or version; transaction rolled back"
            ) from error
        return result

    def report(self, run_id: str) -> dict[str, Any]:
        with self.engine.connect() as connection:
            result = connection.scalar(
                select(runs.c.report).where(runs.c.run_id == run_id)
            )
        if result is None:
            raise ValueError("Unknown collection run")
        return result

    def latest(self, source_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            return connection.scalar(
                select(runs.c.report)
                .where(runs.c.source_id == source_id, runs.c.status != "invalid")
                .order_by(runs.c.sequence.desc())
                .limit(1)
            )
