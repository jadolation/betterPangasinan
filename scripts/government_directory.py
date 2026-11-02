"""Collect official evidence and validate the single government directory."""
import argparse
import hashlib
import json
import re
from html import unescape
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
URLS = {
    'governor': 'https://www.pangasinan.gov.ph/officials/hon-ramon-v-guico-iii/',
    'vice-governor': 'https://www.pangasinan.gov.ph/officials/hon-mark-ronald-dg-lambino/',
    'board': 'https://www.pangasinan.gov.ph/positions/board-member/',
    'districts': 'https://www.pangasinan.gov.ph/city-municipalities/',
    'house': 'https://www.congress.gov.ph/house-members',
    'house-directory': 'https://www.congress.gov.ph/members/',
}


def collect(root=ROOT):
    """Preserve response bytes, including blocked responses; never infer verification."""
    raw = Path(root) / 'data/government_sources/raw'
    raw.mkdir(parents=True, exist_ok=True)
    receipts = []
    for key, url in URLS.items():
        at = datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')
        try:
            with urlopen(Request(url, headers={'User-Agent': 'BetterPangasinan public-source research'}), timeout=60) as response:
                body, status = response.read(), response.status
        except HTTPError as error:
            body, status = error.read(), error.code
        except OSError as error:
            body, status = str(error).encode(), 0
        digest = hashlib.sha256(body).hexdigest()
        (raw / f'{key}-{digest}.html').write_bytes(body)
        receipts.append({'id': key, 'url': url, 'publisher': 'House of Representatives' if key.startswith('house') else 'Province of Pangasinan', 'retrieved_at': at, 'http_status': status, 'sha256': digest, 'raw_path': f'data/government_sources/raw/{key}-{digest}.html'})
    (raw / 'receipts.json').write_text(json.dumps(receipts, indent=2) + '\n')
    return receipts


def validate(data, root=ROOT):
    root = Path(root)
    jsonschema.validate(data, json.loads((root / 'schemas/government_directory.schema.json').read_text()), format_checker=jsonschema.FormatChecker())
    sources = {s['id']: s for s in data['sources']}
    officials = {o['id']: o for o in data['officials']}
    if len(sources) != len(data['sources']) or len(officials) != len(data['officials']):
        raise ValueError('Duplicate source or official ID')
    def check_sources(ids):
        if not ids or not set(ids) <= sources.keys():
            raise ValueError('Unknown or missing source reference')
    for official in officials.values():
        check_sources(official['source_ids'])
        is_district_role = official['role_type'] in {'board_member', 'house_representative'}
        if is_district_role != (official['district_id'] is not None and official['district_number'] is not None):
            raise ValueError('District role scope mismatch')
        if official['verification_status'] == 'source_listed' and any(sources[sid].get('http_status') != 200 for sid in official['source_ids']):
            raise ValueError('Source-listed official requires successful official evidence')
        for field, value in official['contacts'].items():
            evidence = official['field_evidence'].get(f'contacts.{field}')
            if value is not None:
                if not evidence:
                    raise ValueError('Missing contact evidence')
                check_sources(evidence['source_ids'])
                if field == 'facebook' and not any(sid in {'governor', 'vice-governor'} and sources[sid].get('http_status') == 200 for sid in evidence['source_ids']):
                    raise ValueError('Facebook requires official profile evidence')
            if value == '+639171899088' or (value == '+63756323138' and official['role_type'] != 'governor'):
                raise ValueError('Wrong-office telephone policy')
        for evidence in official['field_evidence'].values():
            check_sources(evidence['source_ids'])
        if official['office_location'] is not None and 'office_location' not in official['field_evidence']:
            raise ValueError('Missing office location evidence')
    codes = []
    if [d['number'] for d in data['districts']] != list(range(1, 7)):
        raise ValueError('Exactly six districts required')
    for district, count in zip(data['districts'], [10, 8, 6, 5, 9, 10]):
        check_sources(district['source_ids'])
        if district['id'] != f"leg:pangasinan:{district['number']}{'st' if district['number'] == 1 else 'nd' if district['number'] == 2 else 'rd' if district['number'] == 3 else 'th'}":
            raise ValueError('Invalid district ID')
        if len(district['lgu_psgcs']) != count or len(district['board_member_ids']) != 2:
            raise ValueError('District membership count mismatch')
        for oid, role in [(district['representative_id'], 'house_representative')] + [(x, 'board_member') for x in district['board_member_ids']]:
            person = officials.get(oid)
            if not person or person['role_type'] != role or person['district_id'] != district['id'] or person['district_number'] != district['number']:
                raise ValueError('Wrong district role link')
        codes.extend(district['lgu_psgcs'])
    expected = {x['psgc'] for x in json.loads((root / 'data/production/lgus.json').read_text())}
    if len(codes) != 48 or len(set(codes)) != 48 or set(codes) != expected:
        raise ValueError('Every canonical LGU must occur exactly once')
    for pending in data['pending_positions']:
        check_sources(pending['source_ids'])
    linked = [d['representative_id'] for d in data['districts']] + [oid for d in data['districts'] for oid in d['board_member_ids']]
    if len(linked) != len(set(linked)) or set(linked) != {o['id'] for o in officials.values() if o['role_type'] in {'board_member', 'house_representative'}}:
        raise ValueError('District role links must cover every elected district official once')
    return data


def publication_payload(root=ROOT):
    root = Path(root)
    data = json.loads((root / 'data/production/government_directory.json').read_text())
    validate(data, root)
    public = {**data, 'sources': [{key: value for key, value in source.items() if key != 'raw_path'} for source in data['sources']]}
    return {'data/government-leadership.json': public}


def initialize(root=ROOT):
    """Normalize the captured official listing against the canonical PSGC registry."""
    root = Path(root)
    receipts = json.loads((root / 'data/government_sources/raw/receipts.json').read_text())
    sources = receipts + [
        {'id': 'user-review', 'url': URLS['house'], 'publisher': 'User-provided reviewed House directory references', 'retrieved_at': '2026-11-02T13:40:44Z', 'verification_note': 'Six House names supplied and reviewed by the user; live House retrieval blocked. Not a live House verification.'},
        {'id': 'user-provincial-context', 'url': URLS['board'], 'publisher': 'User-provided provincial context', 'retrieved_at': '2026-11-02T13:40:44Z', 'verification_note': 'Presiding-officer role and reported PCL discrepancy supplied by the user. The cited board listing does not independently establish the unprovided 2025 resolution reference.'},
    ]
    def text(key):
        return (root / next(s['raw_path'] for s in receipts if s['id'] == key)).read_text()
    def evidence(sid, note):
        return {'source_ids': [sid], 'collected_at': next(s['retrieved_at'] for s in sources if s['id'] == sid), 'note': note}
    officials = []
    def person(oid, name, role, position, sid, district=None, full=None):
        o = {'id': oid, 'display_name': name, 'full_name': full or name, 'position': position, 'role_type': role, 'district_id': district['id'] if district else None, 'district_number': district['number'] if district else None, 'source_ids': [sid], 'verification_status': 'user_reviewed' if sid == 'user-review' else 'source_listed', 'contacts': {'telephone': None, 'mobile': None, 'facebook': None}, 'office_location': None, 'field_evidence': {}, 'term': None}
        officials.append(o)
        return o
    gov = person('governor-ramon-guico-iii', 'Ramon V. Guico III', 'governor', 'Governor of Pangasinan', 'governor', full='Ramon Velicaria Guico III')
    gov['contacts']['telephone'] = '+63756323138'
    gov['contacts']['facebook'] = 'https://www.facebook.com/MonMonGuicoIII/'
    gov['office_location'] = '2F Capitol Compound, Lingayen, Pangasinan'
    gov['field_evidence']['contacts.telephone'] = evidence('governor', 'Official profile footer explicitly labels Office of the Governor; not a Vice Governor contact.')
    gov['field_evidence']['contacts.facebook'] = evidence('governor', 'Facebook button on official Governor profile, not the provincial footer account.')
    gov['field_evidence']['office_location'] = evidence('governor', 'Official footer explicitly labels Office of the Governor.')
    gov['field_evidence']['full_name'] = evidence('governor', 'Biography gives Ramon Velicaria Guico III; role current as listed, no term inferred.')
    vice = person('vice-governor-mark-ronald-lambino', 'Hon. Mark Ronald DG. Lambino', 'vice_governor', 'Vice Governor of Pangasinan', 'vice-governor', full='Mark Ronald De Guzman Lambino')
    vice['contacts']['facebook'] = 'https://www.facebook.com/markronaldlambino'
    vice['field_evidence']['contacts.facebook'] = evidence('vice-governor', 'Facebook button on official profile.')
    vice['field_evidence']['full_name'] = evidence('vice-governor', 'Official biography spells out De Guzman.')
    vice['additional_roles'] = ['Presiding Officer, Sangguniang Panlalawigan']
    vice['field_evidence']['additional_roles'] = evidence('user-provincial-context', 'Presiding-officer role supplied by user, separately labeled from profile verification.')
    registry = json.loads((root / 'data/production/lgus.json').read_text())
    def alias(name):
        return re.sub(r'^(city of )| city$', '', name.lower()).strip()
    lookup = {alias(x['name']): x for x in registry}
    if len(lookup) != 48:
        raise ValueError('Ambiguous LGU alias')
    html = text('districts')
    headings = list(re.finditer(r'<h3[^>]*>([1-6])(?:st|nd|rd|th) District</h3>', html))
    board_names = ['Apolonia DG. Bacay', 'Napoleon C. Fontelera Jr.', 'Haidee S. Pacheco', 'Philip Theodore E. Cruz', 'Shiela F. Baniqued', 'Vici C. Ventanilla', 'Jerry Agerico B. Rosario', 'Marinor B. De Guzman', 'Nicholi Jan Louie Q. Sison', 'Rosalina C. Apaga', 'Ranjit R. Shahani', 'Noel Fernando R. Bince Jr.']
    board_text = unescape(re.sub('<[^>]+>', ' ', text('board')))
    normalized_board = re.sub(r'[^a-z0-9]', '', board_text.lower())
    for name in board_names + ['Raul Ramirez Sabangan', 'Joyce Fernandez']:
        if re.sub(r'[^a-z0-9]', '', name.lower()) not in normalized_board:
            raise ValueError(f'Official board name not found in captured source: {name}')
    house_names = ['Arthur F. Celeste', 'Mark O. Cojuangco', 'Maria Rachel J. Arenas', 'Ma. Georgina P. de Venecia', 'Ramon N. Guico Jr.', 'Marlyn L. Primicias-Agabas']
    districts = []
    for i, heading in enumerate(headings[:6]):
        number = i + 1
        ordinal = str(number) + ['st', 'nd', 'rd', 'th', 'th', 'th'][i]
        chunk = html[heading.end():headings[i + 1].start()]
        names = re.findall(r'class="uc_title"[^>]*>\s*<a[^>]*>(.*?)</a>', chunk, re.S)
        if not names:
            names = re.findall(r'<a[^>]*href="https://www.pangasinan.gov.ph/city-municipalities/[^"/]+/"[^>]*>\s*([^<]+)', chunk)
        matched = []
        for name in names:
            key = alias(unescape(re.sub('<[^>]+>', '', name)))
            if key in lookup and lookup[key]['psgc'] not in matched:
                matched.append(lookup[key]['psgc'])
        d = {'id': f'leg:pangasinan:{ordinal}', 'number': number, 'name': f'Pangasinan {ordinal} Legislative District', 'lgu_psgcs': matched, 'representative_id': f'house-{number}', 'board_member_ids': [f'board-{number}-1', f'board-{number}-2'], 'source_ids': ['districts'], 'lgu_names': [next(x['name'] for x in registry if x['psgc'] == code) for code in matched]}
        districts.append(d)
        for j in range(2):
            person(f'board-{number}-{j+1}', board_names[i*2+j], 'board_member', f'Board Member, {ordinal} District', 'board', d)
        representative = person(f'house-{number}', house_names[i], 'house_representative', f'House Representative, {ordinal} District', 'user-review', d)
        representative['source_ids'].extend(['house', 'house-directory'])
    person('ex-officio-abc', 'Raul Ramirez Sabangan', 'ex_officio', 'ABC President / Ex Officio Board Member', 'board')
    person('ex-officio-sk', 'Joyce Fernandez', 'ex_officio', 'SK Federation President / Ex Officio Board Member', 'board')
    data = {'schema_version': 1, 'metadata': {'collected_at': receipts[0]['retrieved_at'], 'scope': 'Six legislative districts, 48 LGUs; source-listed roles, not independently certified terms.', 'house_verification': 'User-reviewed names; both official House directory fetches returned HTTP 403.', 'missing_contacts': 'Unknown values are null; no Vice Governor telephone verified.'}, 'sources': sources, 'officials': officials, 'districts': districts, 'pending_positions': [{'id': 'pcl-president', 'position': 'PCL President / Ex Officio Board Member', 'verification_status': 'pending', 'source_ids': ['board', 'user-provincial-context'], 'note': 'Conflicting evidence: official board listing names Martin Raul S. Sision II; supplied research names Kimberly G. Bandarlipe. No current person confirmed.'}]}
    validate(data, root)
    (root / 'data/production/government_directory.json').write_text(json.dumps(data, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    parser.add_argument('--initialize', action='store_true')
    args = parser.parse_args()
    if args.initialize:
        initialize()
    elif args.collect:
        print(json.dumps(collect(), indent=2))
    else:
        print(f"Validated {len(publication_payload()['data/government-leadership.json']['officials'])} officials")
