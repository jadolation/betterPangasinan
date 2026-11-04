"""Test-only adversarial workbook mapping; unavailable through the operational CLI."""

from io import BytesIO

from openpyxl import load_workbook

from collector.models import GeographicUnit
from collector.pipeline import collect as collect_artifact
from collector.transport import inspect_xlsx

CODES = {
    "TEST_PROVINCE": "9900000000",
    "TEST_CITY": "9900001000",
    "TEST_TOWN": "9900002000",
    "TEST_BARANGAY_A": "9900001001",
    "TEST_BARANGAY_B": "9900002001",
}
METADATA = {
    "is_mock": True,
    "source_url": "https://example.invalid/synthetic-psgc.xlsx",
    "source_agency": "Synthetic test fixture",
    "source_title": "Synthetic adversarial workbook",
    "release": "synthetic-v1",
    "reference_period": None,
    "source_published_at": None,
    "license_status": "test_only",
    "mapping_version": "test_only_workbook_v1",
    "collection_method": "test_fixture",
    "data_format": "xlsx",
}


def extract_psgc(body):
    inspect_xlsx(body)
    book = load_workbook(
        BytesIO(body), read_only=True, data_only=False, keep_links=False
    )
    try:
        if book.sheetnames != ["PSGC_MOCK_V1"]:
            raise ValueError("Unexpected test worksheet")
        rows = book.active.iter_rows()
        headers = tuple(c.value for c in next(rows))
        if headers != ("Code", "Name", "Classification", "Parent", "Notes"):
            raise ValueError("Unexpected test headers")
        result = []
        for number, cells in enumerate(rows, 2):
            if any(c.data_type == "f" for c in cells):
                raise ValueError("Formula in test source")
            raw = dict(zip(headers, (c.value for c in cells)))
            unit = GeographicUnit(
                psgc_code=CODES.get(raw["Code"], raw["Code"]),
                name=raw["Name"],
                classification=raw["Classification"],
                parent_psgc=CODES.get(raw["Parent"], raw["Parent"]),
                population=None,
                release="synthetic-v1",
            )
            result.append(
                {
                    "data": unit.model_dump(),
                    "raw_values": raw,
                    "evidence": {"sheet": "PSGC_MOCK_V1", "row": number},
                }
            )
        return {"rows": result, "metadata": METADATA}
    finally:
        book.close()


def collect(path, raw, store):
    return collect_artifact(
        path, raw, store, extractor=extract_psgc, source_metadata=METADATA
    )
