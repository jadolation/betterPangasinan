#!/usr/bin/env python3
"""Validate datasets and assemble src/pages + partials into isolated public/.

Production also regenerates root HTML for compatibility. Synthetic data is
available only through --mode test, never as a fallback for missing data.
"""

import argparse
import html
import json
import math
import os
import re
import shutil
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

from scripts.national_budget.pipeline import publication_payload
from scripts.site_data import publication_payloads
from scripts.lgu_profiles import publication_payloads as profile_payloads
from scripts.home_snapshot import publication_payload as home_payload

ROOT = Path(__file__).resolve().parent
SRC_PAGES = ROOT / "src" / "pages"
SRC_PARTIALS = ROOT / "src" / "partials"


def atomic_write(destination, content):
    """Root mirrors can also be adapter inputs or live-server resources."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.read_bytes() == content:
        return
    descriptor, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
        os.replace(temporary, destination)
    finally:
        Path(temporary).unlink(missing_ok=True)

# Single place to change the repo link that appears in every page's footer.
SITE_CONFIG = {
    "REPO_URL": "https://github.com/bettergovph",
}

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.S)
DATASETS = ("sources", "entities", "lgus", "finances", "projects", "procurements",
            "contracts", "legislation", "documents", "services", "statistics", "geography")
RELATIONSHIPS = {"source_ids": "sources", "entity_id": "entities", "lgu_id": "lgus",
                 "project_id": "projects", "procurement_id": "procurements",
                 "contract_id": "contracts"}


def load_data(directory: Path, mode: str = "production") -> dict:
    """Validate the entire graph before any output is written."""
    if mode not in ("production", "test", "preview"):
        raise ValueError("Unknown build mode")
    schema = json.loads((ROOT / "schemas" / "record.json").read_text())
    data = {}
    ids = set()
    for name in DATASETS:
        module_schema = json.loads((ROOT / "schemas" / f"{name}.json").read_text())
        validator = Draft202012Validator({"allOf": [schema, module_schema]}, format_checker=FormatChecker())
        path = directory / f"{name}.json"
        if not path.exists() and name in ("sources", "entities", "lgus"):
            raise ValueError(f"Missing required dataset: {name}")
        records = json.loads(path.read_text()) if path.exists() else []
        if not isinstance(records, list):
            raise ValueError(f"{name}: expected an array")
        for record in records:
            validator.validate(record)
            identifier = record["id"]
            for field in ("amount", "value"):
                number = record.get(field)
                if number is not None and (isinstance(number, bool) or not math.isfinite(number)):
                    raise ValueError(f"Invalid numeric value: {identifier}")
            if record.get("amount") is not None and Decimal(str(record["amount"])) % Decimal("0.01"):
                raise ValueError(f"Currency must use exact centavos: {identifier}")
            if identifier in ids:
                raise ValueError(f"Duplicate ID: {identifier}")
            ids.add(identifier)
            if record["is_mock"] != identifier.startswith("mock-"):
                raise ValueError(f"Mock ID/flag mismatch: {identifier}")
            if record["is_mock"] and record["verification_status"] == "verified":
                raise ValueError(f"Mock record cannot be verified: {identifier}")
            if mode == "production" and (record["is_mock"] or record["publication_status"] != "approved"):
                raise ValueError(f"Production rejects mock or unpublished record: {identifier}")
            if mode == "production" and record["verification_status"] == "unreviewed":
                raise ValueError(f"Production rejects unreviewed record: {identifier}")
            if mode == "preview" and record["is_mock"]:
                raise ValueError(f"Preview mode requires real source records: {identifier}")
            if name != "sources" and not record.get("source_ids"):
                raise ValueError(f"Missing provenance: {identifier}")
            if name == "sources" and not record.get("url"):
                raise ValueError(f"Missing source URL: {identifier}")
            if name in ("finances", "projects", "procurements", "contracts", "services") and not record.get("entity_id"):
                raise ValueError(f"Missing responsible entity: {identifier}")
            if name in ("finances", "statistics") and not record.get("reporting_period"):
                raise ValueError(f"Missing reporting period: {identifier}")
            if name == "finances" and not all(key in record for key in ("amount", "amount_type", "category", "unit")):
                raise ValueError(f"Incomplete financial record: {identifier}")
            if name == "lgus" and record.get("psgc") is not None:
                registry_path = directory / "psgc-registry.json"
                registry = json.loads(registry_path.read_text()) if registry_path.exists() else []
                if record["is_mock"] or not any(entry.get("psgc") == record["psgc"] and entry.get("lgu_id") == identifier and entry.get("reviewed") is True and entry.get("source_id") in record.get("source_ids", []) for entry in registry):
                    raise ValueError(f"PSGC requires reviewed registry membership: {identifier}")
            if name == "geography" and record.get("geometry") is not None:
                validate_geometry(record["geometry"])
                if mode == "production" and not record.get("license"):
                    raise ValueError(f"Public geometry requires a reviewed license: {identifier}")
        data[name] = records
    indexes = {name: {record["id"]: record for record in records} for name, records in data.items()}
    for records in data.values():
        for record in records:
            for key, target in RELATIONSHIPS.items():
                values = record.get(key, []) if key == "source_ids" else [record.get(key)]
                for value in values:
                    if value is None:
                        continue
                    related = indexes[target].get(value)
                    if related is None:
                        raise ValueError(f"Broken {key}: {record['id']} -> {value}")
                    if related["is_mock"] != record["is_mock"]:
                        raise ValueError("Mixed mock/real relationships")
            contract = indexes["contracts"].get(record.get("contract_id"))
            project_id = record["id"] if record["id"] in indexes["projects"] else record.get("project_id")
            if contract and project_id and contract.get("project_id") != project_id:
                raise ValueError("Contract/project relationship mismatch")
            procurement = indexes["procurements"].get(record.get("procurement_id"))
            if procurement and project_id and procurement.get("project_id") and procurement["project_id"] != project_id:
                raise ValueError("Procurement/project relationship mismatch")
    return data


def validate_geometry(geometry: dict) -> None:
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")

    def point(value):
        if not isinstance(value, list) or len(value) != 2 or any(isinstance(n, bool) or not isinstance(n, (int, float)) for n in value) or not (-180 <= value[0] <= 180 and -90 <= value[1] <= 90):
            raise ValueError("Invalid geographic coordinates")

    if kind == "Point":
        point(coordinates)
    elif kind in ("Polygon", "MultiPolygon"):
        polygons = [coordinates] if kind == "Polygon" else coordinates
        if not isinstance(polygons, list) or not polygons:
            raise ValueError("Empty geometry")
        for polygon in polygons:
            if not isinstance(polygon, list) or not polygon:
                raise ValueError("Empty polygon")
            for ring in polygon:
                if not isinstance(ring, list) or len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError("Polygon ring must be closed")
                for coordinate in ring:
                    point(coordinate)
    else:
        raise ValueError("Unsupported geometry type")


def financial_summary(records: list) -> dict:
    """One compatible series only; unknown is not silently converted to zero."""
    if not records:
        return {"total": None, "values": []}
    dimensions = {(r["reporting_period"], r["unit"], r["amount_type"], r["is_mock"]) for r in records}
    if len(dimensions) != 1:
        raise ValueError("Cannot aggregate incompatible financial series")
    values = [None if r["amount"] is None else Decimal(str(r["amount"])) for r in records]
    return {"total": None if None in values else sum(values, Decimal(0)), "values": values}


SECTION_NAV_ITEMS = (
    ("overview", "Overview", "transparency.html"),
    ("projects", "2027 Projects", "national-budget.html"),
    ("historical", "Historical Budgets", "historical-budget.html"),
    ("offices", "Offices & Districts", "national-budget.html#offices"),
    ("context", "Context", "budget-context.html"),
    ("hearings", "Hearings", "budget-hearings.html"),
    ("finances", "Local Finances", "finances.html"),
    ("about", "About", "methodology.html#national-budget-methodology"),
)


def render_section_nav(meta: dict) -> str:
    if not meta.get("section_nav"):
        return ""
    if meta["section_nav"] != "transparency":
        raise ValueError("Unknown section navigation")
    selected = meta.get("section_item", "")
    if selected and selected not in {key for key, _, _ in SECTION_NAV_ITEMS}:
        raise ValueError("Unknown transparency section item")
    links = []
    for key, label, href in SECTION_NAV_ITEMS:
        current = ' aria-current="page"' if key == selected else ""
        links.append(f'<a href="{html.escape(href, quote=True)}" data-section-item="{key}"{current}>{html.escape(label)}</a>')
    return fill((SRC_PARTIALS / "transparency-nav.html").read_text(),
                {"SECTION_LINKS": "\n".join(links)})


def parse_page(text: str) -> tuple[dict, str]:
    match = FRONT_MATTER_RE.match(text)
    if not match:
        sys.exit("Page is missing --- front matter (title/description).")
    meta_block, body = match.groups()
    meta = {}
    for line in meta_block.splitlines():
        key, _, value = line.partition(":")
        meta[key.strip()] = value.strip()
    for required in ("title", "description"):
        if required not in meta:
            sys.exit(f"Page is missing required front matter field: {required}")
    return meta, body.strip("\n")


def fill(template: str, values: dict) -> str:
    for key, value in values.items():
        template = template.replace("{{" + key + "}}", value)
    return template


def build(mode: str = "production", output: Path | None = None, data_dir: Path | None = None,
          root_compatibility: bool = True) -> None:
    data = load_data(data_dir or ROOT / "data" / ("fixtures" if mode == "test" else "production"), mode)
    national_budget = publication_payload(ROOT)
    supplemental = publication_payloads(ROOT, data, mode, data_dir)
    supplemental["data/home-snapshot.json"] = home_payload(data, supplemental, national_budget)
    supplemental.update(profile_payloads(data, supplemental, national_budget))
    output = (output or ROOT / {"production": "public", "test": "test-public", "preview": "preview-public"}[mode]).resolve()
    if output == ROOT or ROOT in output.parents and output.parts[len(ROOT.parts)] in ("src", "data", "schemas", "tests", "assets", ".git", ".github", ".kilo") or output in ROOT.parents:
        raise ValueError("Unsafe build output directory")
    base = (SRC_PARTIALS / "base.html").read_text()
    header = (SRC_PARTIALS / "header.html").read_text()
    footer = fill((SRC_PARTIALS / "footer.html").read_text(), SITE_CONFIG)

    page_files = sorted(SRC_PAGES.glob("*.html"))
    if not page_files:
        sys.exit(f"No page sources found in {SRC_PAGES}")

    locale_path = ROOT / "src" / "locales" / "en.json"
    dictionary = json.loads(locale_path.read_text()) if locale_path.exists() else {}

    def strings(value, prefix=""):
        result = {}
        for key, text in value.items():
            name = f"{prefix}.{key}" if prefix else key
            if isinstance(text, dict):
                result.update(strings(text, name))
            elif isinstance(text, str):
                result[f"t:{name}"] = html.escape(text, quote=True)
        return result

    rendered = {}
    for page_path in page_files:
        meta, body = parse_page(page_path.read_text())
        rendered_html = fill(
            base,
            {
                "TITLE": html.escape(meta["title"], quote=True),
                "DESCRIPTION": html.escape(meta["description"], quote=True),
                "HEADER": header,
                "SECTION_NAV": render_section_nav(meta),
                "BODY": body,
                "FOOTER": footer,
            },
        )
        localized = fill(rendered_html, strings(dictionary))
        if mode == "preview":
            localized = localized.replace('<main id="main-content" tabindex="-1">', '<aside class="preview-banner" role="note">Development preview: real collected records with their original source labels. Not a deployment-ready artifact.</aside>\n<main id="main-content" tabindex="-1">')
        if locale_path.exists() and re.search(r"\{\{t:[^}]+\}\}", localized):
            raise ValueError(f"Missing English translation in {page_path.name}")
        rendered[page_path.name] = localized.replace("</head>", f'<meta name="data-mode" content="{mode}">\n</head>')
    if output.exists() and any(output.iterdir()) and not (output / ".build-output").exists():
        raise ValueError("Refusing to replace a directory not owned by this builder")
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    (output / ".build-output").write_text("Better Pangasinan generated output\n")
    for name, content in rendered.items():
        (output / name).write_text(content, encoding="utf-8")
        if root_compatibility and mode == "production":
            atomic_write(ROOT / name, content.encode("utf-8"))
    if (ROOT / "assets").exists():
        for asset in sorted((ROOT / "assets").rglob("*")):
            relative = asset.relative_to(ROOT / "assets")
            if asset.is_file() and not asset.is_symlink() and not any(part.startswith(".") for part in relative.parts) and asset.suffix.lower() in {".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}:
                destination = output / "assets" / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(asset, destination)
    if (ROOT / "logo.svg").exists():
        shutil.copy2(ROOT / "logo.svg", output / "logo.svg")
    (output / "data").mkdir()
    for name, records in data.items():
        (output / "data" / f"{name}.json").write_text(json.dumps(records, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (output / "data" / "public.json").write_text(json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    budget_output = output / "data" / "national-budget" / "2027"
    budget_output.mkdir(parents=True)
    for name, value in national_budget.items():
        (budget_output / f"{name}.json").write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    for relative, value in supplemental.items():
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(value, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    if root_compatibility and mode == "production":
        for path in (output / "data").glob("*.json"):
            atomic_write(ROOT / "data" / path.name, path.read_bytes())
        budget_root = ROOT / "data" / "national-budget" / "2027"
        budget_root.mkdir(parents=True, exist_ok=True)
        for name in ("manifest", "projects", "offices", "coverage", "sources"):
            atomic_write(budget_root / f"{name}.json", (budget_output / f"{name}.json").read_bytes())
        for relative in supplemental:
            destination = ROOT / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            atomic_write(destination, (output / relative).read_bytes())
    if dictionary:
        (output / "locales").mkdir()
        (output / "locales" / "en.json").write_text(json.dumps(dictionary, ensure_ascii=True, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(f"Built {len(rendered)} pages in {output} ({mode}).")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build the validated Better Pangasinan static site")
    parser.add_argument("--mode", choices=("production", "test", "preview"), default="production")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--no-root-compatibility", action="store_true")
    args = parser.parse_args()
    build(args.mode, args.output, args.data_dir, not args.no_root_compatibility)
