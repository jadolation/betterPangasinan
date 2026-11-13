import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web-crawler'))

from crawler.runs import list_runs, sha256, write_json  # noqa: E402


@pytest.fixture(scope='session')
def live_run():
    """Newest real run that captured both sources and was built. Raw evidence is
    not committed, so replay tests skip on a fresh checkout until `collect` runs."""
    for path in reversed(list_runs()):
        manifest = json.loads((path / 'manifest.json').read_text())
        status = manifest.get('source_status', {})
        if status.get('psa-psgc') == 'collected' and status.get('pangasinan-gov') == 'collected' \
                and (path / 'output' / 'build.json').is_file():
            return path
    pytest.skip('no built live run; run `web-crawler collect --authorize-live --build` first')


def synthetic_run(tmp_path, rows, *, count=None, next_url=None, populations=True):
    """Minimal synthetic PSA-only run for adversarial cases. Marked as test data."""
    (tmp_path / 'evidence' / 'psa-psgc').mkdir(parents=True)
    body = json.dumps({'count': len(rows) if count is None else count, 'next': next_url, 'results': rows}).encode()
    (tmp_path / 'evidence' / 'psa-psgc' / 'geo-p1.json').write_bytes(body)
    evidence = [{'source': 'psa-psgc', 'artifact': 'evidence/psa-psgc/geo-p1.json', 'artifact_sha256': sha256(body),
                 'role': 'geography', 'version': 'T1', 'page_number': 1, 'http_status': 200,
                 'source_url': 'https://example.invalid/synthetic', 'retrieved_at': '2026-01-01T00:00:00Z'}]
    write_json(tmp_path / 'manifest.json', {
        'run_id': 'synthetic', 'synthetic_test_data': True, 'evidence': evidence, 'errors': [],
        'psa': {'geography_release': 'T1', 'population_release': None}})
    return tmp_path


def psa_row(code, level, mun=0, name='Synthetic', **extra):
    return {'code': code, 'area_name': name, 'geographic_level': level, 'reg': 1, 'prv': 55, 'mun': mun,
            'version': 'T1', 'income_classification': '', 'urban_rural': '', 'city_class': '',
            'populations': [], **extra}


def valid_rows():
    return [psa_row('0105500000', 'Prov'), psa_row('0105501000', 'Mun', 1),
            psa_row('0105501001', 'Bgy', 1), psa_row('105502000', 'City', 2)]
