from scripts.home_snapshot import publication_payload


def test_home_counts_are_derived_without_loading_or_combining_amounts():
    graph = {"lgus": [{}, {}], "finances": [], "services": []}
    extra = {"data/historical-budget/manifest.json": {"programs": 9},
             "data/budget-hearings.json": {"response": {"data": [{}, {}, {}]}},
             "data/provincial-reference.json": {"budget_observations": [{}]}}
    budget = {"manifest": {"status": "approved"}, "projects": [{}, {}, {}, {}]}
    result = publication_payload(graph, extra, budget)
    assert result["transparency"] == {"budget_2027_records": 4, "historical_programs": 9, "hearing_topics": 3, "local_finance_records": 0, "local_budget_observations": 1}
    assert result["government"] == {"local_governments": 2, "service_records": 0}
    assert not any("amount" in key for key in result["transparency"])


def test_missing_failed_sources_stay_unknown_not_zero():
    result = publication_payload({}, {"data/budget-hearings.json": {"response": None, "error": "HTTP 500"}}, {"manifest": {"status": "unavailable"}})
    for key in ("budget_2027_records", "historical_programs", "hearing_topics", "local_budget_observations"):
        assert result["transparency"][key] is None


def test_boolean_or_negative_program_count_is_not_a_metric():
    for value in (True, -1, None):
        result = publication_payload({}, {"data/historical-budget/manifest.json": {"programs": value}}, {})
        assert result["transparency"]["historical_programs"] is None
