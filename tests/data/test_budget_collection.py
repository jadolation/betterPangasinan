"""Deterministic synthetic transport failures plus a separately captured real fixture."""

import hashlib
import json
import threading
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, urlsplit

import pytest

from scripts.national_budget.collect import (
    BASE, Client, CollectionError, SafeRedirect, check_url, collect, main, paginate,
    reconcile, strict_json, settings,
)


META = {"dataset": "hgab", "fiscal_year": 2027, "currency": "PHP", "scale": "pesos",
        "source_repo": "https://example.org/synthetic", "source_commit": "synthetic-a",
        "built_at": "2026-01-01T00:00:00Z", "notice": "Synthetic test only"}


def envelope(rows=None, total=None, offset=0, next_offset=None, directory=False, sums=None):
    rows = [] if rows is None else rows
    total = len(rows) if total is None else total
    meta = {**META, "returned": len(rows), "total": total, "offset": offset}
    if not directory:
        meta.update(dataset_key="dpwh", house_stage="hgab3")
    data = {"districts" if directory else "rows": rows,
            "total": total, "next_offset": next_offset}
    if not directory:
        data["sums"] = sums if sums is not None else {"nep_php": None}
    return {"meta": meta, "disclaimers": [], "data": data}


def reply(env):
    return 200, {}, json.dumps(env).encode()


def client_for(tmp_path, responses, sleeps=None):
    responses = iter(responses)
    def send(url, timeout):
        assert timeout == 25
        item = next(responses)
        if isinstance(item, Exception):
            raise item
        return reply(item) if isinstance(item, dict) else item
    return Client(tmp_path, transport=send, sleep=(sleeps if sleeps is not None else []).append)


def test_valid_zero_retains_null_sums(tmp_path):
    result = paginate(client_for(tmp_path, [envelope()]), "province", "dpwh", {"q": "none"})
    assert result["complete"] and result["total"] == result["unique"] == 0
    assert result["sums"]["nep_php"] is None
    assert result["reconciled_sums"]["nep_php"] is None


def test_bounded_configuration_is_used_for_requests(tmp_path):
    config = settings()
    config.update(page_size=1, timeout_seconds=20, attempts=1)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    requests = []
    def send(url, timeout):
        requests.append((url, timeout))
        return reply(envelope())
    client = Client(tmp_path / "batch", transport=send, config=path)
    assert paginate(client, "province", "dpwh")["complete"]
    assert parse_qs(urlsplit(requests[0][0]).query)["limit"] == ["1"]
    assert requests[0][1] == 20


@pytest.mark.parametrize("key,value", [("api_base", "http://bad.invalid"), ("page_size", 201), ("timeout_seconds", 90), ("attempts", 0), ("lgu_batch_limit", 100)])
def test_untrusted_or_unbounded_configuration_rejected(tmp_path, key, value):
    config = settings()
    config[key] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(config))
    with pytest.raises(CollectionError):
        settings(path)


def test_detail_batch_cannot_be_unbounded(tmp_path):
    with pytest.raises(CollectionError, match="1..50"):
        collect(tmp_path, detail_limit=51)


def test_interrupted_collection_never_persists_premature_completeness(tmp_path):
    calls = 0
    def send(url, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            return reply(envelope())
        if calls == 2:
            return reply(envelope(directory=True))
        raise KeyboardInterrupt()
    with pytest.raises(KeyboardInterrupt):
        collect(tmp_path, transport=send)
    saved = strict_json((tmp_path / "manifest.json").read_bytes())
    assert not saved["complete"] and not saved["run_complete"]


def test_project_and_district_pagination(tmp_path):
    for directory in (False, True):
        first = envelope([{"id": "a", "nep_php": 1}], 2, next_offset=1, directory=directory,
                         sums={"nep_php": 3, "rows_with_amount": {"nep": 2}})
        second = envelope([{"id": "b", "nep_php": 2}], 2, offset=1, directory=directory,
                          sums={"nep_php": 3, "rows_with_amount": {"nep": 2}})
        result = paginate(client_for(tmp_path / str(directory), [first, second]),
                          "districts" if directory else "province", None if directory else "dpwh")
        assert result["complete"] and result["downloaded"] == result["unique"] == 2
        assert len(result["response_ids"]) == 2


@pytest.mark.parametrize("mutation", [
    lambda env: env["meta"].update(returned=3),
    lambda env: env["meta"].update(total=9),
    lambda env: env["meta"].update(offset=1),
    lambda env: env["meta"].update(house_stage="hgab2"),
    lambda env: env["data"].update(next_offset=0),
    lambda env: env["data"].pop("next_offset"),
    lambda env: env["data"].update(total=2),
    lambda env: env["data"].update(sums={"nep_php": 2}),
    lambda env: env["data"].update(rows=[{"id": "a"}, {"id": "a"}]),
])
def test_malformed_pagination_never_complete(tmp_path, mutation):
    env = envelope([{"id": "a", "nep_php": 1}], sums={"nep_php": 1})
    mutation(env)
    query = paginate(client_for(tmp_path, [env]), "province", "dpwh")
    assert not query["complete"] and query["error"]


def test_duplicate_ids_across_pages(tmp_path):
    first = envelope([{"id": "a"}], 2, next_offset=1)
    second = envelope([{"id": "a"}], 2, offset=1)
    result = paginate(client_for(tmp_path, [first, second]), "province", "dpwh")
    assert not result["complete"] and "Duplicate" in result["error"]
    assert result["downloaded"] == result["unique"] == 1


@pytest.mark.parametrize("key,value", [("source_commit", "other"), ("built_at", "2026-02-01T00:00:00Z")])
def test_snapshot_change(tmp_path, key, value):
    first = envelope([{"id": "a"}], 2, next_offset=1)
    second = envelope([{"id": "b"}], 2, offset=1)
    second["meta"][key] = value
    result = paginate(client_for(tmp_path, [first, second]), "province", "dpwh")
    assert not result["complete"] and "snapshot changed" in result["error"]


@pytest.mark.parametrize("raw", [b"", b"{", b"{}", b'{"meta":{}}',
                                  b'{"a":1,"a":2}', b'{"a":NaN}'])
def test_invalid_envelopes_logged_with_original_bytes(tmp_path, raw):
    client = client_for(tmp_path, [(200, {}, raw)])
    with pytest.raises(CollectionError):
        client.get()
    log = client.requests[0]
    assert log["status"] == 200 and log["error"] and not log["valid"]
    assert log["sha256"] == hashlib.sha256(raw).hexdigest()
    assert (tmp_path / "responses" / (log["sha256"] + ".json")).read_bytes() == raw


@pytest.mark.parametrize("failure", [(500, {}, b"failure"), (429, {"Retry-After": "7"}, b"rate"),
                                    TimeoutError("timeout"), URLError("offline")])
def test_retries_log_every_attempt(tmp_path, failure):
    sleeps = []
    client = client_for(tmp_path, [failure, envelope()], sleeps)
    client.get()
    assert len(client.requests) == 2
    assert client.requests[0]["error"] and client.requests[1]["valid"]
    assert sleeps == ([7] if isinstance(failure, tuple) and failure[0] == 429 else [1])


def test_permanent_http_error_not_retried(tmp_path):
    client = client_for(tmp_path, [(404, {}, b"not found")])
    with pytest.raises(CollectionError, match="HTTP 404"):
        client.get()
    assert len(client.requests) == 1


def test_retry_exhaustion_and_bounded_retry_after(tmp_path):
    client = client_for(tmp_path, [(503, {}, b"down")] * 3)
    with pytest.raises(CollectionError):
        client.get()
    assert len(client.requests) == 3
    client = client_for(tmp_path / "bounded", [(429, {"Retry-After": "5000"}, b"busy")])
    with pytest.raises(CollectionError, match="bounded"):
        client.get()


@pytest.mark.parametrize("url", ["http://budget.bettergov.ph/x", "https://evil.example/x",
                               "https://budget.bettergov.ph.evil.example/x",
                               "https://user@budget.bettergov.ph/x", "https://budget.bettergov.ph:8443/x"])
def test_https_host_allowlist_applies_to_redirects(url):
    with pytest.raises(ValueError):
        check_url(url)
    with pytest.raises(ValueError):
        SafeRedirect().redirect_request(None, None, 302, "redirect", {}, url)


def test_resume_checks_live_snapshot_and_reuses_raw(tmp_path):
    first = collect(tmp_path, transport=lambda url, timeout: reply(envelope(directory=True)), sleep=lambda _: None)
    assert not first["complete"]  # program metadata intentionally wrong for FMR/HFEP/NIA
    calls = []
    def changed(url, timeout):
        calls.append(url)
        env = envelope()
        env["meta"]["source_commit"] = "changed"
        return reply(env)
    second = collect(tmp_path, transport=changed, sleep=lambda _: None)
    assert calls == [BASE]
    assert not second["complete"] and "snapshot changed" in second["errors"][0]


def test_cache_checksum_validation(tmp_path):
    client = client_for(tmp_path, [envelope()])
    _, digest = client.get()
    (tmp_path / "responses" / (digest + ".json")).write_bytes(b"tampered")
    with pytest.raises(CollectionError, match="checksum"):
        client.get()


def test_cross_query_record_conflict(tmp_path):
    client = client_for(tmp_path, [envelope([{"id": "a"}]), envelope([{"id": "a", "title": "changed"}])])
    assert paginate(client, "province", "dpwh", {"q": "first"})["complete"]
    result = paginate(client, "office", "dpwh", {"office": "exact"})
    assert not result["complete"] and "Conflicting" in result["error"]


def test_null_and_zero_sum_semantics():
    assert reconcile([{"nep_php": None}, {"nep_php": 0}],
                     {"nep_php": 0, "rows_with_amount": {"nep": 1}}) == {"nep_php": 0}
    with pytest.raises(CollectionError):
        reconcile([], {"nep_php": 0})
    with pytest.raises(CollectionError):
        reconcile([{"nep_php": True}], {"nep_php": 1})


def test_real_mapandan_regression():
    folder = Path(__file__).parents[1] / "fixtures" / "national_budget"
    raw = (folder / "mapandan.json").read_bytes()
    provenance = json.loads((folder / "mapandan.provenance.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == provenance["sha256"]
    env = strict_json(raw)
    rows = env["data"]["rows"]
    assert {row["id"] for row in rows} == {"house-reading:3959", "house-reading:3923"}
    assert reconcile(rows, env["data"]["sums"])["nep_php"] == 49_000_000
    for key in ("nep_php", "hgab2_php", "hgab3_php", "house_php"):
        assert sum(row[key] for row in rows) == 49_000_000
    assert sum(row["delta_php"] for row in rows) == 0
    assert all(row["bridge_group"] == "unchanged" for row in rows)
    assert "nep_evidence_review" in rows[1]["flags"]
    assert all(row["lat"] is None and row["lon"] is None for row in rows)
    assert all("contractor" not in row and "implementation_status" not in row for row in rows)


def test_full_collection_shared_offices_and_opt_in_details(tmp_path):
    calls = []
    office = {"id": "o", "name": "Short", "tier": "B", "district_ids": ["d:1", "d:2"],
              "years": [{"fy": 2027, "stage": "hgab3", "matched_label": "Exact Published"}]}
    def send(url, timeout):
        calls.append(url)
        parts = urlsplit(url)
        if parts.path.endswith("/districts"):
            return reply(envelope([{"id": "d:1", "jurisdiction": "Pangasinan"},
                                   {"id": "d:2", "jurisdiction": "Pangasinan"}], directory=True))
        if "/districts/" in parts.path:
            number = "1" if parts.path.endswith("1") else "2"
            env = envelope()
            env["data"] = {"id": "d:" + number, "offices": [
                {**office, "co_served_districts": [{"id": "d:" + ("2" if number == "1" else "1")}]}]}
            return reply(env)
        env = envelope()
        for dataset in ("fmr", "hfep", "nia"):
            if "/datasets/" + dataset + "/" in url:
                env["meta"].update(dataset_key=dataset, house_stage="hgab2")
        return reply(env)
    result = collect(tmp_path, offices=True, transport=send, sleep=lambda _: None)
    assert result["complete"] and len(result["offices"]) == 1
    assert result["offices"][0]["matched_label"] == "Exact Published"
    assert len([query for query in result["queries"] if query["category"] == "office"]) == 1
    assert any(parse_qs(urlsplit(url).query).get("office") == ["Exact Published"] for url in calls)
    assert not result["details"]
    calls.clear()
    assert collect(tmp_path, offices=True, transport=send, sleep=lambda _: None)["complete"]
    assert calls == [BASE]  # same-snapshot raw cache, with a live overview anchor


def test_failed_collection_always_writes_manifest(tmp_path):
    result = collect(tmp_path, transport=lambda url, timeout: (500, {}, b"down"), sleep=lambda _: None)
    assert not result["complete"] and result["errors"]
    persisted = json.loads((tmp_path / "manifest.json").read_text())
    assert len(persisted["requests"]) == 3
    assert persisted["requests"][0]["status"] == 500


def test_cli_failure_exit_code(monkeypatch, tmp_path):
    monkeypatch.setattr("scripts.national_budget.collect.collect", lambda **kwargs: {
        "complete": False, "snapshot": None, "errors": ["synthetic failure"], "queries": []})
    assert main(["--output", str(tmp_path)]) == 1


def test_details_opaque_ids_encoded_once_and_conflicts_fail(tmp_path):
    paths = []
    row = {"id": "opaque:%/id", "nep_php": 0}
    def send(url, timeout):
        parts = urlsplit(url)
        paths.append(parts.path)
        if parts.path.endswith("/districts"):
            return reply(envelope(directory=True))
        if parts.path.endswith("/projects/opaque%3A%25%2Fid"):
            env = envelope()
            env["data"] = {**row, "nep_php": 5}  # synthetic conflicting detail
            return reply(env)
        env = envelope([row], sums={"nep_php": 0}) if "/datasets/dpwh/" in url else envelope()
        for dataset in ("fmr", "hfep", "nia"):
            if "/datasets/" + dataset + "/" in url:
                env["meta"].update(dataset_key=dataset, house_stage="hgab2")
        return reply(env)
    result = collect(tmp_path, details=True, transport=send, sleep=lambda _: None)
    assert not result["complete"] and "detail conflicts" in result["errors"][0]
    assert any(path.endswith("opaque%3A%25%2Fid") for path in paths)


def test_retry_after_http_date(tmp_path):
    sleeps = []
    client = client_for(tmp_path, [(429, {"retry-after": "Wed, 01 Jan 2020 00:00:00 GMT"}, b"busy"),
                                   envelope()], sleeps)
    client.get()
    assert sleeps == [1]


def test_reviewed_registry_controlled_batch(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"review_status": "approved", "reviewer": "human:test",
                                   "release": "Synthetic test release", "source_url": "https://psa.gov.ph/classification/psgc",
                                   "reviewed_at": "2026-01-01T00:00:00Z", "lgus": [
                                       {"psgc": "0105501000", "name": "First"},
                                       {"psgc": "0105502000", "name": "Second"}]}))
    def send(url, timeout):
        env = envelope(directory=urlsplit(url).path.endswith("/districts"))
        for dataset in ("fmr", "hfep", "nia"):
            if "/datasets/" + dataset + "/" in url:
                env["meta"].update(dataset_key=dataset, house_stage="hgab2")
        return reply(env)
    result = collect(tmp_path / "batch", registry=registry, lgu_offset=1, lgu_limit=1,
                     transport=send, sleep=lambda _: None)
    queries = [query for query in result["queries"] if query["category"] == "lgu"]
    assert result["complete"] and len(queries) == 4
    assert all(query["lgu_psgc"] == "0105502000" and query["params"] == {"q": "Second"}
               for query in queries)
    registry.write_text(json.dumps({"lgus": []}))
    failed = collect(tmp_path / "unreviewed", registry=registry, transport=send, sleep=lambda _: None)
    assert not failed["complete"] and "human review" in failed["errors"][0]


class ResumeTransport:
    """Synthetic same-snapshot service with independently controllable failures."""

    def __init__(self):
        self.calls = []
        self.fail_anchor = False
        self.fail_queries = set()
        self.fail_details = set()
        self.conflicting_details = set()
        self.rows = [{"id": "one", "nep_php": 1}, {"id": "two", "nep_php": 2}]

    def __call__(self, url, timeout):
        self.calls.append(url)
        parts = urlsplit(url)
        params = parse_qs(parts.query)
        if url == BASE and self.fail_anchor:
            return 503, {}, b"synthetic anchor failure"
        if parts.path.endswith("/districts"):
            return reply(envelope(directory=True))
        if "/projects/" in parts.path:
            identity = parts.path.rsplit("/", 1)[1]
            if identity in self.fail_details:
                return 503, {}, b"synthetic detail failure"
            env = envelope()
            env["data"] = next(dict(row) for row in self.rows if row["id"] == identity)
            if identity in self.conflicting_details:
                env["data"]["extra"] = "conflicting detail evidence"
            return reply(env)
        query = params.get("q", [""])[0]
        if query in self.fail_queries:
            return 503, {}, b"synthetic query failure"
        env = (envelope(self.rows, sums={"nep_php": 3})
               if "/datasets/dpwh/" in parts.path else envelope())
        for dataset in ("fmr", "hfep", "nia"):
            if "/datasets/" + dataset + "/" in parts.path:
                env["meta"].update(dataset_key=dataset, house_stage="hgab2")
        return reply(env)


def test_resume_two_detail_batches_accumulate_idempotently(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    assert first["complete"] and [item["id"] for item in first["details"]] == ["one"]
    second = collect(tmp_path, detail_ids=["dpwh:two"], transport=send, sleep=lambda _: None)
    assert second["complete"] and [item["id"] for item in second["details"]] == ["one", "two"]
    send.calls.clear()
    third = collect(tmp_path, detail_ids=["dpwh:two"], transport=send, sleep=lambda _: None)
    assert third["complete"] and send.calls == [BASE]
    for field in ("queries", "details", "district_details", "offices"):
        assert third[field] == second[field]


def test_default_detail_batches_advance_to_missing_evidence(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, details=True, detail_limit=1, transport=send)
    second = collect(tmp_path, details=True, detail_limit=1, transport=send)
    assert first["complete"] and second["complete"]
    assert {row["id"] for row in second["details"]} == {"one", "two"}
    send.calls.clear()
    third = collect(tmp_path, details=True, detail_limit=1, transport=send)
    assert third["complete"] and send.calls == [BASE]


def test_detail_concurrency_is_explicitly_bounded_and_retains_all_logs(tmp_path):
    send = ResumeTransport()
    send.rows.append({"id": "three", "nep_php": 0})
    barrier = threading.Barrier(3)
    def concurrent(url, timeout):
        if "/projects/" in url:
            barrier.wait(timeout=10)
        return send(url, timeout)
    result = collect(tmp_path, details=True, detail_workers=3, transport=concurrent)
    assert result["complete"] and len(result["details"]) == 3
    entries = [entry for entry in result["requests"] if "/projects/" in entry["url"]]
    assert len(entries) == 3 and all(entry["valid"] and entry["sha256"] for entry in entries)
    with pytest.raises(CollectionError, match="1..3"):
        collect(tmp_path, detail_workers=4)


def test_resume_lgu_offsets_accumulate_and_unrequested_failures_remain(tmp_path):
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"review_status": "approved", "reviewer": "human:test",
                                   "release": "Synthetic test release", "source_url": "https://psa.gov.ph/classification/psgc",
                                   "reviewed_at": "2026-01-01T00:00:00Z", "lgus": [
                                       {"psgc": "0105501000", "name": "First"},
                                       {"psgc": "0105502000", "name": "Second"}]}))
    send = ResumeTransport()
    output = tmp_path / "batch"
    send.fail_queries.add("First")
    first = collect(output, registry=registry, lgu_limit=1, transport=send, sleep=lambda _: None)
    assert not first["complete"]
    send.fail_queries.clear()
    second = collect(output, registry=registry, lgu_offset=1, lgu_limit=1, transport=send, sleep=lambda _: None)
    queries = [query for query in second["queries"] if query["category"] == "lgu"]
    assert len(queries) == 8 and not second["complete"]
    assert {query["lgu_psgc"] for query in queries} == {"0105501000", "0105502000"}
    assert all(query["error"] for query in queries if query["params"]["q"] == "First")
    recovered = collect(output, registry=registry, lgu_limit=1, transport=send, sleep=lambda _: None)
    assert recovered["complete"] and not recovered["errors"]
    assert len([query for query in recovered["queries"] if query["category"] == "lgu"]) == 8


def test_failed_anchor_preserves_manifest_bytes_and_logs_attempts(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    before = (tmp_path / "manifest.json").read_bytes()
    send.fail_anchor = True
    failed = collect(tmp_path, detail_ids=["dpwh:two"], transport=send, sleep=lambda _: None)
    assert not failed["complete"] and failed["errors"]
    assert (tmp_path / "manifest.json").read_bytes() == before
    assert failed["details"] == first["details"]
    log = json.loads((tmp_path / "failed-attempts.jsonl").read_text())
    assert log["operation"] == "anchor" and len(log["requests"]) == 3
    assert all(attempt["status"] == 503 and attempt["sha256"] for attempt in log["requests"])
    for attempt in log["requests"]:
        assert (tmp_path / "responses" / (attempt["sha256"] + ".json")).read_bytes() == b"synthetic anchor failure"
    send.fail_anchor = False
    assert collect(tmp_path, transport=send, sleep=lambda _: None)["complete"]


def test_failed_detail_retains_prior_evidence_until_same_operation_recovers(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    send.fail_details.add("two")
    failed = collect(tmp_path, detail_ids=["dpwh:two"], transport=send, sleep=lambda _: None)
    assert not failed["complete"] and failed["details"] == first["details"]
    send.fail_details.clear()
    unrelated = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    assert not unrelated["complete"] and unrelated["errors"] == failed["errors"]
    recovered = collect(tmp_path, detail_ids=["dpwh:two"], transport=send, sleep=lambda _: None)
    assert recovered["complete"] and not recovered["errors"]
    assert len(recovered["details"]) == 2


def test_failed_requery_preserves_successful_rows_and_can_recover(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, transport=send, sleep=lambda _: None)
    # Changing a bounded page size reruns the query without reusing that URL's cache.
    config = settings()
    config["page_size"] = 100
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps(config))
    send.fail_queries.add("Pangasinan")
    failed = collect(tmp_path, config=config_path, transport=send, sleep=lambda _: None)
    old = next(query for query in first["queries"] if query["category"] == "province" and query["dataset"] == "dpwh")
    retained = next(query for query in failed["queries"] if query["category"] == "province" and query["dataset"] == "dpwh")
    assert not failed["complete"] and retained["error"] and not retained["complete"]
    assert retained["rows"] == old["rows"] and retained["response_ids"] == old["response_ids"]
    send.fail_queries.clear()
    recovered = collect(tmp_path, config=config_path, transport=send, sleep=lambda _: None)
    assert recovered["complete"]
    assert all(not query.get("error") for query in recovered["queries"])
    assert len(recovered["queries"]) == len(first["queries"])


def test_detail_conflict_never_overwrites_existing_evidence(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    # Delete only the cached bytes to force a failed retry, then provide a conflicting detail.
    detail = first["details"][0]
    raw_path = tmp_path / "responses" / (detail["response_id"] + ".json")
    original = raw_path.read_bytes()
    raw_path.unlink()
    failed = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    assert not failed["complete"]
    send.conflicting_details.add("one")
    conflict = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    assert not conflict["complete"] and "Conflicting retained details" in conflict["errors"][0]
    assert conflict["details"] == first["details"]
    send.conflicting_details.clear()
    recovered = collect(tmp_path, detail_ids=["dpwh:one"], transport=send, sleep=lambda _: None)
    assert recovered["complete"] and recovered["details"] == first["details"]
    assert raw_path.read_bytes() == original


def test_initial_anchor_failure_recovers(tmp_path):
    send = ResumeTransport()
    send.fail_anchor = True
    assert not collect(tmp_path, transport=send, sleep=lambda _: None)["complete"]
    send.fail_anchor = False
    recovered = collect(tmp_path, transport=send, sleep=lambda _: None)
    assert recovered["complete"] and recovered["errors"] == []


def test_changed_snapshot_anchor_preserves_manifest_bytes(tmp_path):
    send = ResumeTransport()
    first = collect(tmp_path, transport=send, sleep=lambda _: None)
    before = (tmp_path / "manifest.json").read_bytes()
    def changed(url, timeout):
        assert url == BASE
        env = envelope()
        env["meta"]["source_commit"] = "synthetic-new-snapshot"
        return reply(env)
    failed = collect(tmp_path, transport=changed, sleep=lambda _: None)
    assert not failed["complete"] and "snapshot changed" in failed["errors"][0]
    assert failed["snapshot"] == first["snapshot"]
    assert (tmp_path / "manifest.json").read_bytes() == before
    logged = json.loads((tmp_path / "failed-attempts.jsonl").read_text())
    assert len(logged["requests"]) == 1
    assert logged["requests"][0]["status"] == 200 and not logged["requests"][0]["valid"]
