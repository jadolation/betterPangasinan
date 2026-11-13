"""FY2027 national budget: read-only review export of the approved snapshot.

No fresh acquisition. The approved inputs are hashed before and after export and
must be unchanged; this module never writes inside data/national_budget.
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

from .build import write_csv as budget_csv
from .runs import ROOT, STAGING, file_sha256 as sha, write_json

sys.path.insert(0, str(ROOT))
from scripts.national_budget.pipeline import read_json, record_hash  # noqa: E402


def export_review(target=None):
    target = Path(target or STAGING / 'budget-review' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')).resolve()
    if not target.is_relative_to(STAGING.resolve()) or target.exists():
        raise ValueError('Use a fresh directory beneath data/staging/web-crawler')
    inputs = [ROOT / 'data/national_budget/approved' / name for name in ('candidates.json', 'decisions.json')]
    before = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    candidates, decisions = [read_json(p) for p in inputs]
    if candidates['snapshot_id'] != decisions['snapshot_id'] or candidates['candidate_sha256'] != decisions['candidate_sha256']:
        raise ValueError('Snapshot/decision mismatch')
    records = candidates['projects']
    if len({r['id'] for r in records}) != len(records):
        raise ValueError('Duplicate project identifiers')
    indexed = {d['id']: d for d in decisions['projects']}
    rows, geographic, sources = [], [], []
    for record in records:
        if record_hash(record) != record['record_sha256'] or indexed.get(record['id'], {}).get('record_sha256') != record['record_sha256']:
            raise ValueError('Changed project or stale decision')
        upstream = record['upstream']
        rows.append({**upstream, 'id': record['id'], 'snapshot_id': record['snapshot_id'], 'record_sha256': record['record_sha256'], 'scope': record['scope'], 'review_status': 'pending', 'original_record': record, 'existing_decision': indexed[record['id']]})
        geographic.append({key: record[key] for key in ('id', 'title', 'record_sha256', 'geographic_match_type', 'geographic_review_status', 'scope', 'lgu_associations', 'inclusion_reasons')})
        for stage in ('nep', 'hgab2', 'hgab3'):
            sources.append({'project_id': record['id'], 'stage': stage, 'document_id': upstream.get(stage + '_doc'), 'page': upstream.get(stage + '_page'), 'url': (upstream.get('pdf_url') or {}).get(stage), 'retrieved_at': candidates['retrieved_at'], 'snapshot_id': candidates['snapshot_id'], 'link_status': 'retained_not_refetched'})
    target.mkdir(parents=True)
    budget_csv(target / 'national_budget_2027_review.csv', rows, ['id', 'title', 'dataset', 'program', 'pap', 'office', 'region', 'nep_php', 'hgab2_php', 'hgab3_php', 'house_php', 'delta_php', 'bridge_group', 'reading_status', 'flags', 'scope', 'snapshot_id', 'record_sha256', 'review_status', 'original_record', 'existing_decision'])
    write_json(target / 'project_geographic_candidates.json', {'review_status': 'pending', 'new_geographic_matches': False, 'records': geographic, 'offices': candidates['offices'], 'coverage': candidates['coverage']})
    budget_csv(target / 'budget_source_inventory.csv', sources, ['project_id', 'stage', 'document_id', 'page', 'url', 'retrieved_at', 'snapshot_id', 'link_status'])
    after = {str(p.relative_to(ROOT)): sha(p) for p in inputs}
    if before != after:
        raise ValueError('Approved inputs changed during export')
    manifest = {'created_at': datetime.now(timezone.utc).isoformat(), 'collection_method': 'existing_approved_snapshot_review', 'fresh_acquisition': False, 'review_status': 'pending', 'snapshot_id': candidates['snapshot_id'], 'project_count': len(records), 'inputs': before, 'inputs_unchanged': True, 'files': {p.name: sha(p) for p in target.iterdir()}, 'gaps': ['Original documents and API links retained, not refetched or independently verified.', 'Geographic associations remain as recorded; no new location assertions.', 'Budget proposals are not spending; overlapping office and geographic views must not be summed.']}
    write_json(target / 'manifest.json', manifest)
    return manifest
