"""Regression tests replayed from the newest real capture (offline)."""
import json

from crawler.build import build
from crawler.runs import Run, file_sha256
from crawler.verify import verify


def test_rebuild_is_byte_identical(live_run, tmp_path):
    build(live_run, tmp_path / 'output')
    saved = json.loads((live_run / 'output' / 'build.json').read_text())['files']
    rebuilt = {p.name: file_sha256(p) for p in (tmp_path / 'output').iterdir() if p.name != 'build.json'}
    assert rebuilt == {k: v for k, v in saved.items() if k != 'build.json'}


def test_structural_checks_pass_on_real_capture(live_run):
    result = verify(live_run, update_checklist=False)
    failed = [c['check'] for c in result['checks'] if c['result'] != 'pass']
    assert failed == []
    assert result['publication_approval'] == 'not_approved'


def test_hierarchy_matches_actual_release(live_run):
    run = Run(live_run)
    lgus = json.loads((live_run / 'output' / 'pangasinan_lgus.json').read_text())['records']
    bgys = json.loads((live_run / 'output' / 'pangasinan_barangays.json').read_text())['records']
    codes = {r['psgc'] for r in lgus}
    assert all(b['parent_psgc'] in codes for b in bgys)
    # Counts come from the API envelope of the captured release, not a hard-coded expectation.
    declared = json.loads(run.read(run.evidence('psa-psgc', role='geography')[0]))['count']
    assert 1 + len(lgus) + len(bgys) == declared


def test_site_pages_mapped_to_psgc(live_run):
    summary = json.loads((live_run / 'output' / 'build.json').read_text())
    pages = len([e for e in Run(live_run).evidence('pangasinan-gov', role='extracted') if e['page'].startswith('lgu-')])
    issues = json.loads((live_run / 'output' / 'inconsistencies.json').read_text())['issues']
    unmatched = [i for i in issues if i['type'] == 'site_page_unmatched']
    assert summary['site_pages_matched'] + len(unmatched) == pages
