"""Offline, synthetic-only PSGC vertical slice with immutable evidence."""

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import ParseError
from openpyxl.utils.exceptions import InvalidFileException

from collector.exporters import safe_target
from uuid import uuid4

from openpyxl import load_workbook

from collector.models import GeographicUnit
from collector.transport import inspect_xlsx, load_source

HEADERS = ("Code", "Name", "Classification", "Parent", "Notes")
MAPPING = "synthetic_psgc_v1"


def extract_psgc(body: bytes) -> list[dict]:
    inspect_xlsx(body)
    book = load_workbook(
        BytesIO(body), read_only=True, data_only=False, keep_links=False
    )
    try:
        if book.sheetnames != ["PSGC_MOCK_V1"]:
            raise ValueError(
                "layout_changed: expected synthetic PSGC_MOCK_V1 worksheet"
            )
        sheet = book["PSGC_MOCK_V1"]
        rows = sheet.iter_rows()
        if tuple(cell.value for cell in next(rows)) != HEADERS:
            raise ValueError("layout_changed: headers differ from synthetic_psgc_v1")
        result = []
        for number, cells in enumerate(rows, 2):
            if number > 10000:
                raise ValueError("row_limit: synthetic workbook exceeds 10000 rows")
            if len(cells) != len(HEADERS) or any(
                cell.data_type == "f" for cell in cells
            ):
                raise ValueError("unsafe_cell: unexpected columns or formula")
            raw = dict(zip(HEADERS, (cell.value for cell in cells)))
            unit = GeographicUnit(
                psgc_code=raw["Code"],
                name=raw["Name"],
                classification=raw["Classification"],
                parent_psgc=raw["Parent"],
            )
            result.append({"data": unit.model_dump(), "raw_values": raw, "row": number})
        if not result:
            raise ValueError("empty_source: no geographic records")
        return result
    finally:
        book.close()


def validate_records(records: list[dict]) -> dict:
    errors = []
    for record in records:
        try:
            GeographicUnit.model_validate(record["data"])
        except ValueError as error:
            errors.append(
                {
                    "code": "invalid_schema",
                    "record_id": record["id"],
                    "message": str(error),
                }
            )
    if errors:
        return {
            "validation_status": "invalid",
            "coverage_status": "partial",
            "is_mock": True,
            "errors": errors,
            "gaps": [],
            "counts": {},
        }
    codes = Counter(r["data"]["psgc_code"] for r in records)
    by_code = {r["data"]["psgc_code"]: r["data"] for r in records}
    allowed = {
        "city": {"province"},
        "municipality": {"province"},
        "barangay": {"city", "municipality"},
    }
    for record in records:
        row = record["data"]
        code, kind, parent = row["psgc_code"], row["classification"], row["parent_psgc"]
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
    if sum(r["data"]["classification"] == "province" for r in records) != 1:
        errors.append({"code": "province_count", "record_id": None})
    return {
        "validation_status": "invalid" if errors else "incomplete",
        "coverage_status": "partial",
        "is_mock": True,
        "errors": errors,
        "counts": dict(Counter(r["data"]["classification"] for r in records)),
        "gaps": [
            {"record_id": r["id"], "field": "population", "reason": "not_collected"}
            for r in records
        ],
        "warnings": [
            "Synthetic fixture only; no official release or 4-city/44-municipality coverage asserted."
        ],
    }


def collect(fixture: Path, raw_directory: Path, store) -> dict:
    source = load_source("psa_psgc")
    run_id = str(uuid4())
    retrieved = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    run = {
        "run_id": run_id,
        "source_id": "psa_psgc",
        "retrieved_at": retrieved,
        "extractor_version": MAPPING,
    }
    records = []
    artifact: dict[str, Any] = {
        "sha256": None,
        "path": None,
        "source_url": "https://example.invalid/synthetic-psgc.xlsx",
        "source_id": "psa_psgc",
        "retrieved_at": retrieved,
        "is_mock": True,
        "license_status": "test_only",
    }
    try:
        with Path(fixture).open("rb") as handle:
            body = handle.read(source.max_download_bytes + 1)
        if len(body) > source.max_download_bytes:
            raise ValueError("file_too_large: fixture exceeds configured limit")
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
        for row in extract_psgc(body):
            code = row["data"]["psgc_code"]
            records.append(
                {
                    "id": "geographic_unit:psgc:" + code,
                    "entity_type": "geographic_unit",
                    "name": row["data"]["name"],
                    "source_id": "psa_psgc",
                    "source_url": artifact["source_url"],
                    "source_agency": "Synthetic test fixture",
                    "source_title": "PSGC-like synthetic fixture",
                    "source_record_id": code,
                    "source_published_at": None,
                    "reference_period": None,
                    "release": "synthetic-v1",
                    "retrieved_at": retrieved,
                    "collection_run_id": run_id,
                    "artifact_sha256": artifact["sha256"],
                    "version": artifact["sha256"],
                    "license_status": "test_only",
                    "collection_method": "fixture_import",
                    "data_format": "xlsx",
                    "validation_status": "incomplete",
                    "review_status": "pending",
                    "is_mock": True,
                    "missing_fields": {
                        "population": "not_collected",
                        "reference_period": "not_applicable",
                    },
                    "source_errors": [],
                    "data": row["data"],
                    "raw_values": row["raw_values"],
                    "evidence": [
                        {
                            "artifact_sha256": artifact["sha256"],
                            "sheet": "PSGC_MOCK_V1",
                            "row": row["row"],
                            "mapping_version": MAPPING,
                        }
                    ],
                }
            )
        quality = validate_records(records)
    except (
        OSError,
        ValueError,
        KeyError,
        StopIteration,
        ParseError,
        InvalidFileException,
    ) as error:
        quality = {
            "validation_status": "invalid",
            "coverage_status": "partial",
            "is_mock": True,
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
