"""Evidence-preserving real PSA transcription import into review staging."""

from collections import Counter
from datetime import date, datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from collector.exporters import safe_target
from collector.models import GeographicUnit
from collector.transport import load_source
from scripts.import_psa_lgus import normalize
from scripts.national_budget.collect import strict_json

MAPPING = "reviewed_psa_transcription_v1"


def extract_psgc(body: bytes) -> dict:
    """Map the observed repository transcription, never guess an official XLSX layout."""
    if body.startswith(b"PK\x03\x04"):
        raise ValueError(
            "official_workbook_mapping_unverified: save the official workbook for layout review before import"
        )
    try:
        original = strict_json(body)
        metadata, supplied = original["metadata"], original["lgus"]
        if (
            original.get("is_mock")
            or metadata.get("is_mock")
            or any(row.get("is_mock") for row in supplied)
        ):
            raise ValueError("Real-data import rejects mock source records")
        date.fromisoformat(metadata["administrative_listing_as_of"])
        date.fromisoformat(metadata["population_reference_date"])
        normalized = normalize(
            original, sha256(body).hexdigest(), "not_a_source_retrieval_date"
        )
        source = normalized["sources"][0]
        context = {
            "mapping_version": MAPPING,
            "is_mock": False,
            "source_url": metadata["url"],
            "source_agency": metadata["source"],
            "source_title": source["name"],
            "source_kind": "user_reviewed_transcription",
            "independently_verified": False,
            "release": metadata["administrative_listing_as_of"],
            "reference_period": metadata["population_reference_date"],
            "source_published_at": None,
            "source_retrieved_at": None,
            "license_status": "pending",
            "collection_method": "local_source_import",
            "data_format": "json",
        }
        province = normalized["province_profile"]
        rows = [
            {
                "data": GeographicUnit(
                    psgc_code=metadata["province_psgc"],
                    name=province["name"],
                    classification="province",
                    parent_psgc=None,
                    population=sum(row["population_2024"] for row in supplied),
                    release=context["release"],
                ).model_dump(),
                "raw_values": metadata,
                "evidence": {
                    "json_pointer": "/metadata",
                    "population_derivation": {
                        "method": "sum_of_supplied_lgu_population_2024",
                        "input_json_pointers": [
                            f"/lgus/{index}/population_2024"
                            for index in range(len(supplied))
                        ],
                        "reference_period": context["reference_period"],
                    },
                },
            }
        ]
        for index, row in enumerate(supplied):
            unit = GeographicUnit(
                psgc_code=row["psgc"],
                name=row["name"],
                classification=row["classification"],
                parent_psgc=metadata["province_psgc"],
                population=row["population_2024"],
                release=row["psgc_release"],
            )
            rows.append(
                {
                    "data": unit.model_dump(),
                    "raw_values": row,
                    "evidence": {
                        "json_pointer": f"/lgus/{index}",
                        "population_reference_period": row["population_reference_date"],
                    },
                }
            )
        return {"rows": rows, "metadata": context}
    except (KeyError, TypeError, AttributeError) as error:
        raise ValueError(
            "source_layout_unrecognized: expected reviewed PSA transcription metadata and lgus"
        ) from error


def validate_records(records: list[dict]) -> dict:
    errors = []
    flags = {row.get("is_mock") for row in records}
    if len(flags) > 1:
        errors.append({"code": "mixed_mock_and_real", "record_id": None})
    is_mock = bool(records) and flags == {True}
    for record in records:
        try:
            GeographicUnit.model_validate(record["data"])
        except (ValueError, KeyError) as error:
            errors.append(
                {
                    "code": "invalid_schema",
                    "record_id": record.get("id"),
                    "message": str(error),
                }
            )
    if not errors:
        codes = Counter(row["data"]["psgc_code"] for row in records)
        by_code = {row["data"]["psgc_code"]: row["data"] for row in records}
        allowed = {
            "city": {"province"},
            "municipality": {"province"},
            "barangay": {"city", "municipality"},
        }
        for record in records:
            row = record["data"]
            code, kind, parent = (
                row["psgc_code"],
                row["classification"],
                row["parent_psgc"],
            )
            if codes[code] > 1:
                errors.append({"code": "duplicate_psgc", "record_id": code})
            if kind == "province":
                if parent is not None:
                    errors.append({"code": "province_has_parent", "record_id": code})
            elif (
                parent not in by_code
                or by_code[parent]["classification"] not in allowed[kind]
            ):
                errors.append({"code": "missing_or_invalid_parent", "record_id": code})
        if sum(row["data"]["classification"] == "province" for row in records) != 1:
            errors.append({"code": "province_count", "record_id": None})
        if not is_mock and records and records[0].get("mapping_version") == MAPPING:
            observed_counts = Counter(row["data"]["classification"] for row in records)
            if observed_counts != {"province": 1, "city": 4, "municipality": 44}:
                errors.append(
                    {"code": "transcription_coverage_changed", "record_id": None}
                )
    counts = dict(
        Counter(row.get("data", {}).get("classification", "unknown") for row in records)
    )
    gaps = [
        {"record_id": row["id"], "field": "population", "reason": "not_collected"}
        for row in records
        if row.get("data", {}).get("population") is None
    ]
    if not counts.get("barangay"):
        gaps.append(
            {"record_id": None, "field": "barangays", "reason": "not_collected"}
        )
    return {
        "validation_status": "invalid" if errors else "incomplete",
        "coverage_status": "partial",
        "is_mock": is_mock,
        "errors": errors,
        "counts": counts,
        "gaps": gaps,
        "warnings": [
            "Review staging only; no collection or validation event grants publication approval.",
            "A reviewed transcription is not a newly acquired official PSGC release.",
        ],
    }


def collect(
    input_path: Path,
    raw_directory: Path,
    store,
    *,
    extractor=extract_psgc,
    source_metadata=None,
) -> dict:
    """Import a saved source. The injectable extractor boundary exists for isolated tests."""
    source = load_source("psa_psgc")
    run_id = str(uuid4())
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    context = {
        "mapping_version": MAPPING,
        "is_mock": False,
        "source_url": None,
        "source_agency": None,
        "source_title": None,
        "source_kind": "unclassified_saved_source",
        "independently_verified": False,
        "release": None,
        "reference_period": None,
        "source_published_at": None,
        "source_retrieved_at": None,
        "license_status": "pending",
        "collection_method": "local_source_import",
        "data_format": "unknown",
    }
    if source_metadata:
        context.update(source_metadata)
    run = {
        "run_id": run_id,
        "source_id": "psa_psgc",
        "retrieved_at": retrieved,
        "extractor_version": context["mapping_version"],
    }
    artifact: dict[str, Any] = {
        "sha256": None,
        "path": None,
        "source_id": "psa_psgc",
        "retrieved_at": retrieved,
        **context,
    }
    records = []
    try:
        with Path(input_path).open("rb") as handle:
            body = handle.read(source.max_download_bytes + 1)
        if len(body) > source.max_download_bytes:
            raise ValueError("file_too_large: source exceeds configured limit")
        artifact["sha256"] = sha256(body).hexdigest()
        raw_directory = safe_target(raw_directory)
        raw_directory.mkdir(parents=True, exist_ok=True)
        path = raw_directory / artifact["sha256"]
        artifact["path"] = str(path.absolute())
        if path.exists():
            if (
                path.is_symlink()
                or sha256(path.read_bytes()).hexdigest() != artifact["sha256"]
            ):
                raise ValueError("artifact_corrupt: existing raw evidence differs")
        else:
            with path.open("xb") as handle:
                handle.write(body)
        artifact["path"] = str(path.resolve())
        extracted = extractor(body)
        context.update(extracted["metadata"])
        if source_metadata:
            context.update(source_metadata)
        artifact.update(context)
        run["extractor_version"] = context["mapping_version"]
        for row in extracted["rows"]:
            code = row["data"]["psgc_code"]
            missing = {
                key: "not_supplied"
                for key in ("source_published_at", "source_retrieved_at")
                if context[key] is None
            }
            if row["data"].get("population") is None:
                missing["population"] = "not_collected"
            if context["reference_period"] is None:
                missing["reference_period"] = "not_supplied"
            records.append(
                {
                    "id": "geographic_unit:psgc:" + code,
                    "entity_type": "geographic_unit",
                    "name": row["data"]["name"],
                    "source_id": "psa_psgc",
                    **context,
                    "source_record_id": code,
                    "retrieved_at": retrieved,
                    "collection_run_id": run_id,
                    "artifact_sha256": artifact["sha256"],
                    "version": artifact["sha256"],
                    "validation_status": "collected",
                    "review_status": "pending",
                    "missing_fields": missing,
                    "source_errors": [],
                    "data": row["data"],
                    "raw_values": row["raw_values"],
                    "evidence": [
                        {
                            "artifact_sha256": artifact["sha256"],
                            "mapping_version": context["mapping_version"],
                            **row["evidence"],
                        }
                    ],
                }
            )
        quality = validate_records(records)
    except (OSError, ValueError, KeyError, TypeError) as error:
        quality = {
            "validation_status": "invalid",
            "coverage_status": "partial",
            "is_mock": context["is_mock"],
            "errors": [{"code": type(error).__name__, "message": str(error)}],
            "gaps": [],
            "counts": {},
        }
    for record in records:
        record["validation_status"] = quality["validation_status"]
    stage = store.stage(records, artifact, run, quality)
    result = store.report(run_id)
    result.update(result["run"])
    result["stage"] = {"new_versions": stage["created_versions"]}
    return result
