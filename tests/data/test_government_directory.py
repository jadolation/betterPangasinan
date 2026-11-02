"""Publication contract and government contact safeguards."""
import copy
import hashlib
import json
from pathlib import Path

import pytest

from scripts.government_directory import publication_payload, validate

ROOT = Path(__file__).resolve().parents[2]


def bundle():
    return copy.deepcopy(publication_payload(ROOT)['data/government-leadership.json'])


def test_contract_and_counts():
    data = bundle()
    assert set(data) == {'schema_version', 'metadata', 'sources', 'officials', 'districts', 'pending_positions'}
    assert len(data['officials']) == 22
    assert [len(d['lgu_psgcs']) for d in data['districts']] == [10, 8, 6, 5, 9, 10]
    assert len({code for d in data['districts'] for code in d['lgu_psgcs']}) == 48
    assert sum(o['role_type'] == 'board_member' for o in data['officials']) == 12
    assert sum(o['role_type'] == 'house_representative' for o in data['officials']) == 6


def test_leadership_and_house_verification():
    data = bundle()
    vice = next(o for o in data['officials'] if o['role_type'] == 'vice_governor')
    assert vice['full_name'] == 'Mark Ronald De Guzman Lambino'
    assert vice['contacts']['telephone'] is None
    assert vice['office_location'] is None
    assert vice['contacts']['facebook'] == 'https://www.facebook.com/markronaldlambino'
    house = [o for o in data['officials'] if o['role_type'] == 'house_representative']
    assert all(o['verification_status'] == 'user_reviewed' for o in house)
    assert house[4]['display_name'] == 'Ramon N. Guico Jr.'
    assert data['pending_positions'][0]['verification_status'] == 'pending'
    assert not any('Bandarlipe' in o['display_name'] or 'Martin Raul' in o['display_name'] for o in data['officials'])


@pytest.mark.parametrize('mutation', ['source', 'phone', 'unconfirmed', 'duplicate', 'wrong-role', 'missing-contact-evidence'])
def test_rejects_invalid_publication(mutation):
    data = bundle()
    if mutation == 'source':
        data['officials'][0]['source_ids'] = ['missing']
    elif mutation == 'phone':
        data['officials'][1]['contacts']['telephone'] = '+63756323138'
    elif mutation == 'unconfirmed':
        data['officials'][1]['contacts']['telephone'] = '+639171899088'
    elif mutation == 'duplicate':
        data['districts'][1]['lgu_psgcs'][0] = data['districts'][0]['lgu_psgcs'][0]
    elif mutation == 'wrong-role':
        data['districts'][0]['representative_id'] = 'board-1-1'
    else:
        data['officials'][0]['field_evidence'].pop('contacts.telephone')
    with pytest.raises(ValueError):
        validate(data, ROOT)


def test_raw_receipts_when_available():
    for source in bundle()['sources']:
        if 'raw_path' not in source:
            continue
        path = ROOT / source['raw_path']
        if path.exists():
            assert hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256']
    assert next(s for s in bundle()['sources'] if s['id'] == 'house')['http_status'] == 403


def test_reference_form_preserved_before_explorer():
    html = (ROOT / 'src/pages/government.html').read_text()
    assert html.index('data-government-directory') < html.index('data-reference="government"')
    assert 'name="q"' in html and 'name="collection"' in html
