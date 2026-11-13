"""Small synthetic adversarial cases for parsing, security and review barriers."""
import json

import pytest

from conftest import synthetic_run, valid_rows
from crawler import net
from crawler.build import BuildError, build, csv_cell, normalize_psgc
from crawler.runs import Run, resolve_run
from crawler.verify import staleness, verify


def test_valid_synthetic_hierarchy_builds(tmp_path):
    build(synthetic_run(tmp_path, valid_rows()))
    lgus = json.loads((tmp_path / 'output' / 'pangasinan_lgus.json').read_text())['records']
    assert [r['psgc'] for r in lgus] == ['0105501000', '0105502000']
    assert lgus[1]['psgc_as_published'] == '105502000'


@pytest.mark.parametrize('mutate', [
    lambda rows: rows.append(dict(rows[1])),                        # duplicate PSGC
    lambda rows: rows[1].update(is_mock=True),                     # mock input
    lambda rows: rows[2].update(mun=9),                            # barangay parent missing
    lambda rows: rows[1].update(geographic_level='Bgy', mun=0),    # wrong parent type / self parent
    lambda rows: rows[1].update(prv=56),                           # out of scope
    lambda rows: rows[1].update(code=105501000),                   # integer code
    lambda rows: rows[1].update(geographic_level='SubMun'),        # unexpected level
])
def test_invalid_source_cannot_build(tmp_path, mutate):
    rows = valid_rows()
    mutate(rows)
    with pytest.raises(BuildError):
        build(synthetic_run(tmp_path, rows))


def test_incomplete_pagination_rejected(tmp_path):
    with pytest.raises(BuildError):
        build(synthetic_run(tmp_path, valid_rows(), count=10))
    with pytest.raises(BuildError):
        build(synthetic_run(tmp_path / 'b', valid_rows(), next_url='https://example.invalid/p2'))


def test_unknown_population_is_missing_not_zero(tmp_path):
    build(synthetic_run(tmp_path, valid_rows()))
    lgu = json.loads((tmp_path / 'output' / 'pangasinan_lgus.json').read_text())['records'][0]
    assert lgu['population_2024'] == {'value': None, 'missing_reason': 'no_release_with_population_found'}


def test_psgc_normalization_is_strict():
    assert normalize_psgc('105500000') == '0105500000'
    for bad in [105500000, '10550000', '01055000001', '0105A00000', None]:
        with pytest.raises(BuildError):
            normalize_psgc(bad)


def test_verifier_detects_tampering_and_staleness(tmp_path):
    run = synthetic_run(tmp_path, valid_rows())
    build(run)
    first = verify(run, update_checklist=False)
    assert [c for c in first['checks'] if c['check'] == 'evidence_hashes_match_manifest'][0]['result'] == 'pass'
    assert staleness(run) == 'current'
    with (run / 'output' / 'pangasinan_lgus.json').open('a') as stream:
        stream.write(' ')
    assert staleness(run) == 'stale'
    assert 'rebuild_reproduces_outputs' in [c['check'] for c in verify(run, update_checklist=False)['checks']
                                           if c['result'] == 'fail']
    (run / 'evidence' / 'psa-psgc' / 'geo-p1.json').write_bytes(b'{}')
    with pytest.raises(ValueError):
        build(run)


def test_verifier_flags_value_not_in_cited_source(tmp_path):
    run = synthetic_run(tmp_path, valid_rows())
    build(run)
    path = run / 'output' / 'pangasinan_lgus.json'
    data = json.loads(path.read_text())
    data['records'][0]['name']['value'] = 'Fabricated'
    path.write_text(json.dumps(data))
    failed = {c['check']: c for c in verify(run, update_checklist=False)['checks'] if c['result'] == 'fail'}
    assert 'field_values_match_cited_evidence' in failed


def test_network_guards():
    with pytest.raises(net.FetchError, match='destination_not_allowlisted'):
        net.get('example.com', '/')
    with pytest.raises(net.FetchError, match='nonpublic_destination'):
        net.public_addresses('x', resolver=lambda *a, **k: [(0, 0, 0, '', ('10.0.0.1', 443))])
    with pytest.raises(net.FetchError, match='nonpublic_destination'):
        net.public_addresses('x', resolver=lambda *a, **k: [(0, 0, 0, '', ('8.8.8.8', 443)),
                                                            (0, 0, 0, '', ('127.0.0.1', 443))])
    assert net.redact(b'?token=a%2Bb&x=a+b', 'a+b') == b'?token=[REDACTED]&x=[REDACTED]'


def test_run_paths_cannot_escape(tmp_path):
    for value in ['../../etc', '/tmp', 'nonexistent-run']:
        with pytest.raises(ValueError):
            resolve_run(value)
    run = Run(synthetic_run(tmp_path, valid_rows()))
    for name in ['../x', '.hidden', 'a/b']:
        with pytest.raises(ValueError):
            run.add_evidence('psa-psgc', name, b'')


def test_csv_formula_injection_escaped():
    assert csv_cell('=HYPERLINK("x")') == '\'=HYPERLINK("x")'
    assert csv_cell(' +1') == "' +1"
    assert csv_cell('Agno') == 'Agno'


def test_site_field_requires_exact_quote():
    from crawler.build import lgu_site_fields
    page = {'evidence': {'artifact': 'a'}, 'body': {'links': [
        {'text': 'WEBSITE', 'href': 'https://a.gov.ph/'}, {'text': 'WEBSITE', 'href': 'https://b.gov.ph/'}],
        'text': 'Number of Barangay: 18\nIt is part of the first congressional district with a land area of 16,660 hectares.'}}
    fields = lgu_site_fields(page)
    assert fields['barangay_count']['value'] == 18
    assert fields['legislative_district']['value'] == 1
    assert fields['land_area_ha']['value'] == 16660
    assert fields['website'] is None  # ambiguous links are not chosen
    assert fields['population_2020_site'] is None
    other = lgu_site_fields({'evidence': {}, 'body': {'links': [], 'text':
                             'Part of the 6th District. A total land area of 4,447.10 hectares.'}})
    assert other['legislative_district']['value'] == 6
    assert other['land_area_ha']['value'] == 4447.10
