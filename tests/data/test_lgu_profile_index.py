import json

import pytest

import build
from scripts.lgu_profiles import publication_payloads
from scripts.site_data import publication_payloads as site_payloads


@pytest.fixture(scope="module")
def profiles():
    graph = build.load_data(build.ROOT / "data/production")
    extra = site_payloads(build.ROOT, graph)
    national = {key: json.loads((build.ROOT / f"data/national-budget/2027/{key}.json").read_text()) for key in ("manifest", "projects")}
    return graph, publication_payloads(graph, extra, national)


def test_generated_profiles_preserve_population_and_parent_barangays(profiles):
    graph, payload = profiles
    assert len(payload) == 48
    for lgu in graph["lgus"]:
        row = payload[f"data/lgu-profiles/{lgu['id']}.json"]
        assert row["lgu_id"] == lgu["id"] and row["psgc"] == lgu["psgc"]
        assert row["barangay_count"] == len(row["barangays"])
        assert all(item["parent_psgc"] == lgu["psgc"] for item in row["barangays"])
    assert payload["data/lgu-profiles/lgu-0105518000.json"]["barangay_count"] == 31
    assert payload["data/lgu-profiles/lgu-0105528000.json"]["barangay_count"] == 15


def test_province_budgets_do_not_become_capital_or_other_lgu_budgets(profiles):
    graph, payload = profiles
    for lgu in graph["lgus"]:
        budgets = payload[f"data/lgu-profiles/{lgu['id']}.json"]["budget_observations"]
        assert all(row["lgu"] != "Pangasinan Provincial Government" for row in budgets)
    sual = next(lgu for lgu in graph["lgus"] if lgu["name"] == "Sual")
    report = payload[f"data/lgu-profiles/{sual['id']}.json"]["budget_observations"][0]
    assert report["amount_php"] == 505000000
    assert report["provincial_review_disposition"] == "operative in PART"


def test_budget_title_matches_are_small_discovery_only_not_local_finances(profiles):
    _, payload = profiles
    row = payload["data/lgu-profiles/lgu-0105528000.json"]
    assert row["national"]["discovery_count"] == 2
    assert row["national"]["verified"] == []
    assert row["budget_observations"] == []
    assert all("nep_php" not in item and "upstream" not in item for item in row["national"]["discovery"])
    assert len(row["historical"]["discovery"]) <= 3


def test_only_reviewed_geographic_associations_establish_budget_relationships():
    lgu = {"id": "lgu-0105518000", "psgc": "0105518000", "name": "City of Dagupan", "classification": "city", "is_mock": False}
    graph = {"lgus": [lgu]}
    first = {"id": "dpwh:one", "title": "Dagupan test source", "scope": "office", "geographic_review_status": "pending", "lgu_associations": []}
    reviewed = {**first, "id": "dpwh:two", "geographic_review_status": "reviewed", "lgu_associations": [{"psgc": lgu["psgc"], "review_status": "reviewed"}]}
    pending = {**reviewed, "id": "dpwh:three", "lgu_associations": [{"psgc": lgu["psgc"], "review_status": "pending"}]}
    row = publication_payloads(graph, {}, {"projects": [first, reviewed, pending]})[f"data/lgu-profiles/{lgu['id']}.json"]
    assert [item["id"] for item in row["national"]["verified"]] == ["dpwh:two"]
    assert {item["id"] for item in row["national"]["discovery"]} == {"dpwh:one", "dpwh:three"}


def test_facility_names_alone_do_not_create_local_service_associations():
    lgu = {"id": "lgu-0105518000", "psgc": "0105518000", "name": "City of Dagupan", "classification": "city", "is_mock": False}
    extra = {"data/provincial-reference.json": {"official_pages": [{"id": "directory", "url": "https://www.pangasinan.gov.ph/directory/", "rows": [
        ["Dagupan District Hospital", "075 123 4567"],
        ["Test facility, Dagupan City", "075 123 4568"],
        ["Another facility, Dagupan City", "075 123 4569"],
    ]}]}}
    row = publication_payloads({"lgus": [lgu]}, extra, {})[f"data/lgu-profiles/{lgu['id']}.json"]
    assert [item["institution"] for item in row["hospitals"]] == ["Test facility", "Another facility"]


def test_mock_names_never_join_real_research_or_budget_candidates():
    lgu = {"id": "mock-lgu", "psgc": "0105518000", "name": "Dagupan", "is_mock": True}
    row = publication_payloads({"lgus": [lgu]}, {}, {"projects": [{"id": "one", "title": "Dagupan"}]})["data/lgu-profiles/mock-lgu.json"]
    assert row["national"]["discovery"] == [] and row["geography"] is None
