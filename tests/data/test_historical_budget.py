"""Real snapshot reconciliation plus isolated offline publication regressions."""

import copy
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError

from scripts.historical_budget.collect import Collector, digest, save
from scripts.historical_budget.publish import ALLOWLIST, publication_payload, review_prototype, safe_values

ROOT = Path(__file__).resolve().parents[2]


class HistoricalBudgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = publication_payload(ROOT)

    def test_contract_and_all_discovered_departments(self):
        self.assertEqual(set(self.payload), ALLOWLIST)
        manifest = self.payload["data/historical-budget/manifest.json"]
        self.assertEqual(manifest["years"], [str(y) for y in range(2020, 2027)])
        self.assertEqual(manifest["scale"], "pesos")
        self.assertEqual(manifest["stage"], "enacted_appropriations")
        deps = self.payload["data/historical-budget/departments.json"]["data"]
        queries = self.payload["data/historical-budget/coverage.json"]["data"]
        self.assertEqual({d["id"] for d in deps}, {q["department_id"] for q in queries if q["query"] == "Pangasinan"})
        self.assertTrue(all(q["complete"] and q["matched"] == q["fetched"] for q in queries))
        self.assertTrue(any(len(q["pages"]) > 1 for q in queries))

    def test_real_families_have_exact_annual_values(self):
        rows = self.payload["data/historical-budget/programs.json"]["data"]
        self.assertGreater(len(rows), 0)
        self.assertEqual(len({r["key"] for r in rows}), len(rows))
        for row in rows:
            self.assertTrue(row["key"].startswith("gaa:" + row["department_id"] + ":"))
            self.assertEqual(row["geography"], "name_match_unverified")
            self.assertEqual(set(row["years"]), {str(y) for y in range(2020, 2027)})
            for value in row["years"].values():
                self.assertIsInstance(value["amount"], (int, str, type(None)))
        self.assertTrue(any(r["years"]["2020"]["amount"] == 0 for r in rows))

    def test_distinct_context_and_honest_api_error(self):
        context = self.payload["data/budget-context.json"]["datasets"]
        self.assertEqual(context["nep_overview"]["response"]["meta"]["fiscal_year"], 2027)
        self.assertEqual(context["budget_cycle_overview"]["response"]["meta"]["scope"], "current_new_appropriations")
        self.assertEqual(context["budget_cycle_dpwh"]["status"], 404)
        self.assertIsNone(context["budget_cycle_dpwh"]["response"])
        hearing = self.payload["data/budget-hearings.json"]
        self.assertGreater(hearing["coverage"]["returned"], 0)
        self.assertIn("not approved funding", hearing["notice"])

    def test_safe_integer_and_null(self):
        self.assertEqual(safe_values([None, 0, 9007199254740992]), [None, 0, "9007199254740992"])

    def test_stale_review_fails_closed_without_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            shutil.copytree(ROOT / "data/historical_budget/approved", Path(tmp) / "data/historical_budget/approved")
            path = Path(tmp) / "data/historical_budget/approved/collection.json"
            data = json.loads(path.read_text())
            data["limitations"].append("unreviewed change")
            save(path, data)
            with patch("urllib.request.urlopen", side_effect=AssertionError("No production network")):
                with self.assertRaisesRegex(ValueError, "stale"):
                    publication_payload(tmp)

    def test_cursor_exhaustion_and_repeated_cursor(self):
        with tempfile.TemporaryDirectory() as tmp:
            collector = Collector(tmp)
            first = {"url": "first", "data": {"data": [1], "next_cursor": "cursor"}}
            last = {"url": "last", "data": {"data": [2], "next_cursor": None}}
            with patch.object(collector, "get", side_effect=[first, last]) as get:
                result = collector.programs("18", "Pangasinan")
                self.assertTrue(result["exhausted"])
                self.assertEqual(get.call_args.args[1]["cursor"], "cursor")
            with patch.object(collector, "get", side_effect=[first, first]):
                self.assertFalse(collector.programs("18", "Pangasinan")["exhausted"])

    def test_transient_failure_then_success_clears_error_and_resumes(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = MagicMock()
            response.__enter__.return_value = response
            response.status = 200
            response.read.return_value = b'{"data":[]}'
            with patch("scripts.historical_budget.collect.urlopen", side_effect=[HTTPError("url", 503, "temporary", {}, None), response]) as fetch, patch("scripts.historical_budget.collect.time.sleep"):
                collector = Collector(tmp)
                result = collector.get("/api/v1/gaa/departments")
                self.assertNotIn("error", result)
                self.assertEqual(result["status"], 200)
                self.assertEqual(collector.get("/api/v1/gaa/departments"), result)
                self.assertEqual(fetch.call_count, 2)

    def test_dedup_overlapping_queries_and_conflicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "data/historical_budget/approved"
            # Two departments may legitimately use the same upstream family key.
            row = {"department_id": "18", "agency_id": "18-001", "fam_key": "same", "name": "Pangasinan program",
                   "years": {"2020": {"amount": 0, "count": 0}, "2026": {"amount": 123, "count": 1}}}
            meta = {"currency": "PHP", "scale": "pesos", "years": list(range(2020, 2027))}
            entries = {}
            def entry(url, body):
                e = {"url": url, "data": body, "payload_sha256": digest(body), "status": 200, "retrieved_at": "2026-11-01T00:00:00Z"}
                name = digest(url) + ".json"
                entries[url] = name
                save(folder / "inputs" / name, e)
                return url
            base = "https://budget.bettergov.ph/api/v1"
            deps = entry(base + "/gaa/departments", {"meta": {**meta, "total_items": 2}, "data": [{"id": "18"}, {"id": "05"}]})
            queries = []
            for department, query in [("18", "Pangasinan"), ("05", "Pangasinan"), ("18", "Dagupan")]:
                r = copy.deepcopy(row); r["department_id"] = department
                url = entry(base + f"/gaa/departments/{department}/programs?q={query}&limit=500", {"meta": {**meta, "matched": 1}, "data": [r], "next_cursor": None})
                queries.append({"department_id": department, "query": query, "pages": [url], "error": None, "exhausted": True})
            url = entry(base + "/hearings/search?q=Pangasinan&limit=100", {"data": []})
            spec = entry(base + "/openapi.json", {})
            save(folder / "collection.json", {"departments_url": deps, "queries": queries, "contexts": {"hearings": url, "openapi": spec}, "limitations": []})
            review_prototype(tmp)
            result = publication_payload(tmp)["data/historical-budget/programs.json"]["data"]
            self.assertEqual(len(result), 2)
            merged = next(r for r in result if r["department_id"] == "18")
            self.assertEqual(merged["queries"], ["Pangasinan", "Dagupan"])
            self.assertEqual(merged["years"]["2020"]["amount"], 0)
            self.assertIsNone(merged["years"]["2021"]["amount"])
            conflict = folder / "inputs" / entries[queries[-1]["pages"][0]]
            value = json.loads(conflict.read_text()); value["data"]["data"][0]["years"]["2026"]["amount"] = 999
            value["payload_sha256"] = digest(value["data"]); save(conflict, value); review_prototype(tmp)
            with self.assertRaisesRegex(ValueError, "Conflicting"):
                publication_payload(tmp)


if __name__ == "__main__":
    unittest.main()
