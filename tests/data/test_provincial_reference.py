import copy
import json
import shutil
from pathlib import Path

import jsonschema
import pytest

from scripts.provincial_reference import DATASETS, PublicHTML, publication_payload

ROOT = Path(__file__).resolve().parents[2]


def bundle():
    return publication_payload(ROOT)['data/provincial-reference.json']


def test_research_is_preserved_without_pending_label_exclusion():
    data = bundle()
    for name in DATASETS:
        original = json.loads((ROOT / 'Better_Pangasinan_Research_Batch_01' / (name + '.json')).read_text())
        assert len(data[name]) == len(original)
        for raw, row in zip(original, data[name]):
            assert all(row[key] == value for key, value in raw.items())
            assert row['publication_review'] == 'publication_reviewed'
            assert row['collected_date'] == '2026-10-31'
    assert len(data['statistics']) == 30
    assert len(data['sources']) == 47
    assert len(data['hospital_directory_observations']) == 12
    assert len(data['budget_observations']) == 15
    assert len(data['legislation_index']) == 15
    assert len(data['project_leads']) == 4


def test_population_periods_and_registry_reconcile():
    data = bundle()
    trend = {row['reference_period']: row['value'] for row in data['statistics'] if row['indicator'] == 'Total population'}
    assert trend == {'2010': 2779862, '2015': 2956726, '2020': 3163190, '2024': 3188540}
    registry = json.loads((ROOT / 'Better_Pangasinan_Research_Batch_01/lgu_registry_2024.json').read_text())
    population_key = next(k for k in registry[0] if 'population' in k)
    assert sum(row[population_key] for row in registry) == 3188540
    assert len(registry) == 48
    assert len({row['psgc_10'] for row in registry}) == 48
    mapandan = next(row for row in bundle()['lgu_registry_2024'] if row['psgc_10'] == '0105528000')
    assert mapandan['name'] == 'Mapandan'
    assert mapandan['population_2024'] == 38228
    assert mapandan['population_reference_date'] == '2024-07-01'
    assert mapandan['collected_date'] == '2026-10-31'


def test_hospital_dates_remain_unknown_and_budget_flags_retained():
    data = bundle()
    assert all(row['as_of_date'] is None for row in data['hospital_directory_observations'])
    text = json.dumps(data['budget_observations']).lower()
    assert '2027' in text and 'propos' in text
    assert 'sual' in text and 'part' in text
    assert '2026' in text


def test_actual_html_collected_and_emergency_evidence():
    pages = {p['id']: p for p in bundle()['official_pages']}
    assert set(pages) == {'directory', 'disaster-services', 'history', 'about'}
    assert any('24/7 Emergency 911 Hotline' in t for t in pages['disaster-services']['text'])
    assert len([r for r in pages['directory']['rows'] if 'hospital' in r[0].lower()]) == 13
    assert any('April 5, 1580' in t for t in pages['history']['text'])
    assert all(p['as_of_date'] is None for p in pages.values())


@pytest.mark.parametrize('field,value', [('reference_collection_status', 'verified_current'), ('publication_review', 'pending')])
def test_schema_rejects_invented_status(field, value):
    data = copy.deepcopy(bundle())
    data['statistics'][0][field] = value
    schema = json.loads((ROOT / 'schemas/provincial_reference.schema.json').read_text())
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(data, schema)


def test_parser_excludes_executable_content():
    parser = PublicHTML()
    parser.feed('<script>invented phone</script><style>fake</style><table><tr><td>Office</td><td>123</td></tr></table>')
    assert parser.rows == [['Office', '123']]
    assert parser.text == ['Office', '123']


@pytest.mark.parametrize('mutation', ['duplicate_record', 'unknown_source', 'unsafe_url', 'duplicate_source'])
def test_publication_rejects_broken_identity_or_provenance(tmp_path, mutation):
    folder = tmp_path / 'data/provincial_reference'
    folder.mkdir(parents=True)
    (tmp_path / 'schemas').mkdir()
    shutil.copyfile(ROOT / 'schemas/provincial_reference.schema.json', tmp_path / 'schemas/provincial_reference.schema.json')
    for path in (ROOT / 'data/provincial_reference').glob('*.json'):
        shutil.copyfile(path, folder / path.name)
    filename = 'sources.json' if mutation == 'duplicate_source' else 'statistics.json'
    rows = json.loads((folder / filename).read_text())
    if mutation == 'duplicate_record':
        rows[1]['id'] = rows[0]['id']
    elif mutation == 'unknown_source':
        rows[0]['source_id'] = 'invented-source'
    elif mutation == 'unsafe_url':
        rows[0]['source_url'] = 'http://example.com/'
    else:
        rows[1]['source_id'] = rows[0]['source_id']
    (folder / filename).write_text(json.dumps(rows))
    with pytest.raises(ValueError):
        publication_payload(tmp_path)
