"""Deterministic evidence -> review-only P0 outputs. Never contacts the network.

Every populated field carries {value, evidence}; every unpopulated field carries
{value: null, missing_reason}. Disagreements between official sources are listed
in inconsistencies and are never silently resolved.
"""
import csv
import io
import json
import re
import shutil
from pathlib import Path

from .runs import Run, sha256, write_json

LEVELS = {'Prov', 'City', 'Mun', 'Bgy'}
ORDINALS = {w: i for i, w in enumerate(
    ['first', 'second', 'third', 'fourth', 'fifth', 'sixth', 'seventh', 'eighth'], 1)}
NUMBER = r'[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+'
SITE = 'pangasinan-gov'
PSA = 'psa-psgc'


class BuildError(ValueError):
    pass


def found(value, evidence, **extra):
    return {'value': value, 'evidence': evidence, **extra}


def missing(reason, **extra):
    return {'value': None, 'missing_reason': reason, **extra}


def to_int(text):
    text = text.strip()
    if not re.fullmatch(NUMBER, text):
        raise BuildError('unparseable_number')
    return int(text.replace(',', ''))


def normalize_psgc(code):
    """PSGC is a 10-digit string. Newer API releases drop the leading zero."""
    if not isinstance(code, str) or not re.fullmatch(r'[0-9]{9,10}', code):
        raise BuildError(f'invalid_psgc:{code!r}')
    return code.zfill(10)


def name_key(name):
    """Comparison key for matching site pages to PSGC names; not used as an identifier."""
    name = name.lower().replace('ñ', 'n')
    name = re.sub(r'^city of |\s+city$', '', name.strip())
    return re.sub(r'[^a-z0-9]+', '', name)


# ---------------------------------------------------------------- PSA

def psa_pages(run, role, version):
    pages = sorted(run.evidence(PSA, role=role, version=version), key=lambda e: e['page_number'])
    if not pages:
        raise BuildError(f'no_psa_{role}_evidence')
    rows, expected = [], None
    for number, entry in enumerate(pages, 1):
        body = json.loads(run.read(entry))
        if entry['page_number'] != number or entry['http_status'] != 200:
            raise BuildError('psa_page_sequence')
        if not isinstance(body.get('results'), list) or type(body.get('count')) is not int:
            raise BuildError('psa_envelope')
        if expected not in (None, body['count']):
            raise BuildError('psa_count_changed')
        expected = body['count']
        if bool(body.get('next')) != (number < len(pages)):
            raise BuildError('psa_pagination_incomplete')
        for index, original in enumerate(body['results']):
            rows.append((original, {'artifact': entry['artifact'], 'artifact_sha256': entry['artifact_sha256'],
                                    'source_url': entry['source_url'], 'retrieved_at': entry['retrieved_at'],
                                    'json_pointer': f'/results/{index}'}))
    if len(rows) != expected:
        raise BuildError('psa_count_mismatch')
    return rows


def parse_geography(run, version):
    records = {}
    for original, evidence in psa_pages(run, 'geography', version):
        if original.get('is_mock'):
            raise BuildError('mock_input')
        if original.get('version') != version or original.get('reg') != 1 or original.get('prv') != 55:
            raise BuildError('psa_scope')
        level = original.get('geographic_level')
        if level not in LEVELS:
            raise BuildError(f'unexpected_level:{level}')
        psgc = normalize_psgc(original['code'])
        if psgc in records:
            raise BuildError(f'duplicate_psgc:{psgc}')
        reg, prv, mun = original['reg'], original['prv'], original['mun']
        parent = {'Prov': None, 'City': f'{reg:02d}{prv:03d}00000', 'Mun': f'{reg:02d}{prv:03d}00000',
                  'Bgy': f'{reg:02d}{prv:03d}{mun:02d}000'}[level]
        if parent and not psgc.startswith(parent[:7] if level == 'Bgy' else parent[:5]):
            raise BuildError(f'parent_code_disagrees:{psgc}')
        records[psgc] = {'psgc': psgc, 'level': level, 'parent': parent, 'original': original, 'evidence': evidence}
    provinces = [r for r in records.values() if r['level'] == 'Prov']
    if len(provinces) != 1 or provinces[0]['psgc'] != '0105500000':
        raise BuildError('province_invalid')
    for r in records.values():
        if r['parent'] is None:
            continue
        allowed = ('Prov',) if r['level'] in ('City', 'Mun') else ('City', 'Mun')
        if r['parent'] == r['psgc'] or r['parent'] not in records or records[r['parent']]['level'] not in allowed:
            raise BuildError(f'parent_invalid:{r["psgc"]}')
    return records


def parse_populations(run, version, issues):
    """{psgc: {year: field}} with original strings preserved."""
    result, names = {}, {}
    for original, evidence in psa_pages(run, 'population', version) if version else []:
        psgc = normalize_psgc(original['code'])
        names[psgc] = original.get('area_name')
        years = {}
        for i, item in enumerate(original.get('populations') or []):
            ev = {**evidence, 'json_pointer': f'{evidence["json_pointer"]}/populations/{i}',
                  'release': version, 'reference_period': str(item.get('year'))}
            try:
                if normalize_psgc(item.get('psgc')) != psgc or type(item.get('year')) is not int:
                    raise BuildError('population_link')
                value = to_int(item['population'])
            except (BuildError, AttributeError, KeyError):
                issues.append({'type': 'population_unparseable', 'psgc': psgc, 'evidence': ev,
                               'original_value': item})
                continue
            if item['year'] in years:
                issues.append({'type': 'population_duplicate_year', 'psgc': psgc, 'year': item['year'], 'evidence': ev})
                continue
            years[item['year']] = found(value, ev, original_value=item['population'])
        result[psgc] = years
    return result, names


# ---------------------------------------------------------------- provincial site

def site_pages(run):
    pages = {}
    for entry in run.evidence(SITE, role='extracted'):
        body = json.loads(run.read(entry))
        pages[entry['page']] = {'body': body, 'evidence': {
            'artifact': entry['artifact'], 'artifact_sha256': entry['artifact_sha256'],
            'source_url': entry['source_url'], 'retrieved_at': entry['retrieved_at']}}
    return pages


def quote_field(page, pattern, convert=lambda m: m[1], flags=re.I):
    """Return a field backed by the exact sentence-level quote from page text, or None."""
    match = re.search(pattern, page['body']['text'], flags)
    if not match:
        return None
    return found(convert(match), {**page['evidence'], 'quote': match[0]})


def link_field(page, label):
    links = {a['href'] for a in page['body']['links'] if a['text'].strip().upper() == label and a['href']}
    if len(links) != 1:
        return None
    return found(links.pop(), {**page['evidence'], 'link_text': label})


def lgu_site_fields(page):
    text_fields = {
        'income_class': quote_field(page, r'\b(\d+)(?:st|nd|rd|th) Class (?:Municipality|City)\b', lambda m: int(m[1])),
        'barangay_count': quote_field(page, r'Number of Barangays?:\s*(\d+)', lambda m: int(m[1])),
        'legislative_district': quote_field(
            page, r'\b(?:(first|second|third|fourth|fifth|sixth) (?:congressional|legislative) district'
                  r'|([1-6])(?:st|nd|rd|th) (?:congressional |legislative )?district)\b',
            lambda m: ORDINALS[m[1].lower()] if m[1] else int(m[2])),
        'land_area_ha': quote_field(page, rf'land area of (?:about |approximately )?((?:{NUMBER})(?:\.[0-9]+)?) hectares',
                                    lambda m: float(m[1].replace(',', '')) if '.' in m[1] else to_int(m[1])),
        'population_2020_site': quote_field(page, rf'population of ({NUMBER})(?: people| residents)? '
                                                  r'(?:according to|based on|as of) the 2020 census',
                                            lambda m: to_int(m[1])),
    }
    return {**text_fields, 'website': link_field(page, 'WEBSITE'), 'facebook': link_field(page, 'FACEBOOK')}


# ---------------------------------------------------------------- outputs

def csv_cell(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, str) and value.lstrip().startswith(('=', '+', '-', '@')):
        value = "'" + value
    return value


def write_csv(path, rows, fields):
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=fields, lineterminator='\n')
    writer.writeheader()
    for row in rows:
        writer.writerow({k: csv_cell(row.get(k)) for k in fields})
    Path(path).write_text(stream.getvalue())


def value(field):
    return field.get('value') if field else None


def build(run_path, out=None):
    run = Run(run_path)
    out = Path(out or run.path / 'output')
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    issues, gaps = [], []
    psa = run.manifest.get('psa') or {}
    geography_release, population_release = psa.get('geography_release'), psa.get('population_release')
    if not geography_release:
        raise BuildError('psa_geography_release_missing')
    geo = parse_geography(run, geography_release)
    pops, pop_names = parse_populations(run, population_release, issues)
    region_entry = run.evidence(PSA, role='region')
    region = None
    if region_entry:
        rows = json.loads(run.read(region_entry[0])).get('results') or []
        if len(rows) == 1:
            region = found(rows[0].get('area_name'), {'artifact': region_entry[0]['artifact'],
                           'artifact_sha256': region_entry[0]['artifact_sha256'],
                           'source_url': region_entry[0]['source_url'],
                           'retrieved_at': region_entry[0]['retrieved_at'], 'json_pointer': '/results/0'},
                           psgc_original=rows[0].get('code'))
    pages = site_pages(run)

    def psa_field(r, key):
        raw = r['original'].get(key)
        if raw in ('', None):
            return missing('empty_in_source', release=geography_release)
        return found(raw, {**r['evidence'], 'json_pointer': r['evidence']['json_pointer'] + '/' + key,
                           'release': geography_release})

    def population(psgc, year):
        if population_release is None:
            return missing('no_release_with_population_found')
        if psgc not in pops:
            return missing(f'psgc_absent_from_population_release_{population_release}')
        return pops[psgc].get(year) or missing(f'year_{year}_absent_in_source')

    for psgc, r in geo.items():
        if psgc in pop_names and pop_names[psgc] != r['original']['area_name']:
            defect = '\ufffd' in r['original']['area_name'] + pop_names[psgc]
            issues.append({'type': 'source_encoding_defect' if defect else 'name_differs_between_releases',
                           'psgc': psgc,
                           'values': {geography_release: r['original']['area_name'],
                                      population_release: pop_names[psgc]}})
    for psgc in sorted(set(pops) - set(geo)):
        issues.append({'type': 'psgc_only_in_population_release', 'psgc': psgc, 'name': pop_names[psgc]})

    def base(r):
        o = r['original']
        return {
            'id': r['psgc'], 'psgc': r['psgc'], 'psgc_as_published': o['code'],
            'name': found(o['area_name'], {**r['evidence'], 'release': geography_release}),
            'geographic_level': o['geographic_level'], 'parent_psgc': r['parent'],
            'psgc_release': geography_release,
            'population_2024': population(r['psgc'], 2024),
            'population_2020': population(r['psgc'], 2020),
            'review_status': 'pending', 'is_mock': False, 'original_values': o,
        }

    children = {}
    for r in geo.values():
        children.setdefault(r['parent'], []).append(r)
    province = geo['0105500000']
    lgus = sorted(children[province['psgc']], key=lambda r: r['psgc'])

    # Match provincial LGU pages to PSGC by exact normalized name; ambiguity is reported, never guessed.
    lgu_by_key = {}
    for r in lgus:
        lgu_by_key.setdefault(name_key(r['original']['area_name']), []).append(r['psgc'])
    page_for = {}
    for key, page in pages.items():
        if not key.startswith('lgu-'):
            continue
        heading = (page['body'].get('headings') or [None])[0]
        matches = lgu_by_key.get(name_key(heading or ''), [])
        if len(matches) == 1 and matches[0] not in page_for:
            page_for[matches[0]] = page
        else:
            issues.append({'type': 'site_page_unmatched', 'page': key, 'heading': heading,
                           'candidates': matches, 'evidence': page['evidence']})

    lgu_records = []
    for r in lgus:
        rec = base(r)
        bgys = children.get(r['psgc'], [])
        rec['classification'] = found({'City': 'city', 'Mun': 'municipality'}[r['level']],
                                      {**r['evidence'], 'json_pointer': r['evidence']['json_pointer'] + '/geographic_level'})
        rec['city_class'] = psa_field(r, 'city_class') if r['level'] == 'City' else None
        rec['income_classification'] = psa_field(r, 'income_classification')
        rec['barangay_count'] = found(len(bgys), {'derived_from': 'count of PSGC barangay records with this parent',
                                                  'release': geography_release})
        page = page_for.get(r['psgc'])
        site = lgu_site_fields(page) if page else {}
        reason = 'not_found_on_provincial_lgu_page' if page else 'provincial_lgu_page_not_captured'
        for key in ('legislative_district', 'land_area_ha', 'website', 'facebook'):
            rec[key] = site.get(key) or missing(reason)
        if value(rec['facebook']):
            rec['facebook']['verification'] = 'listed_on_official_provincial_site; not independently verified'
        for key in ('address', 'contact', 'coordinates'):
            rec[key] = missing('no_official_source_collected')
        rec['provincial_page'] = page['evidence']['source_url'] if page else None
        rec['site_cross_checks'] = {k: site.get(k) for k in ('income_class', 'barangay_count', 'population_2020_site')}
        income = re.match(r'\d+', value(rec['income_classification']) or '')
        checks = [('barangay_count', 'barangay_count', len(bgys)),
                  ('population_2020', 'population_2020_site', value(rec['population_2020'])),
                  ('income_classification', 'income_class', int(income[0]) if income else None)]
        for field, site_key, psa_value in checks:
            site_value = value(site.get(site_key))
            if site_value is not None and psa_value is not None and site_value != psa_value:
                issues.append({'type': f'{field}_differs', 'psgc': r['psgc'], 'name': r['original']['area_name'],
                               'values': {'pangasinan.gov.ph': site_value, 'psa': psa_value},
                               'evidence': site[site_key]['evidence']})
        lgu_records.append(rec)

    barangays = []
    for lgu in lgus:
        for r in sorted(children.get(lgu['psgc'], []), key=lambda r: r['psgc']):
            rec = base(r)
            rec['parent_name'] = lgu['original']['area_name']
            rec['urban_rural'] = psa_field(r, 'urban_rural')
            barangays.append(rec)

    # Provincial overview.
    ov = base(province)
    ov['official_name'] = ov.pop('name')
    ov['region'] = region or missing('psa_region_record_not_captured')
    ov['income_classification'] = psa_field(province, 'income_classification')
    for label, levels in (('number_of_cities', ('City',)), ('number_of_municipalities', ('Mun',)),
                          ('number_of_barangays', ('Bgy',))):
        ov[label] = found(sum(r['level'] in levels for r in geo.values()),
                          {'derived_from': 'count of PSGC records in Pangasinan', 'release': geography_release})
    capital_values = {}
    for key, page in pages.items():
        # "capital town of Lingayen" or "Lingayen, the capital town of Pangasinan".
        f = quote_field(page, r'\bcapital (?:town|city|municipality) of (?!Pangasinan\b)([A-Z][a-z]+)'
                              r'|\b([A-Z][a-z]+), the capital (?:town|city|municipality) of Pangasinan\b',
                        lambda m: m[1] or m[2], flags=0)
        if f:
            capital_values.setdefault(f['value'], []).append(f['evidence'])
    if len(capital_values) == 1:
        name, evs = next(iter(capital_values.items()))
        ov['capital'] = found(name, evs[0], corroborating_evidence=evs[1:])
    elif capital_values:
        ov['capital'] = missing('conflicting_official_statements', candidates=capital_values)
        issues.append({'type': 'capital_conflict', 'values': capital_values})
    else:
        ov['capital'] = missing('no_explicit_statement_found_in_captured_pages')
    areas = []
    for key in ('about', 'geography'):
        if key in pages:
            f = quote_field(pages[key], rf'({NUMBER}) hectares', lambda m: to_int(m[1]))
            if f:
                areas.append(f)
    if len({a['value'] for a in areas}) == 1:
        ov['land_area_ha'] = areas[0]
    elif areas:
        ov['land_area_ha'] = missing('conflicting_official_statements', candidates=areas)
        issues.append({'type': 'provincial_land_area_conflict', 'psgc': '0105500000',
                       'values': [{'value': a['value'], 'quote': a['evidence']['quote'],
                                   'source_url': a['evidence']['source_url']} for a in areas]})
    else:
        ov['land_area_ha'] = missing('provincial_pages_not_captured' if not pages else 'not_stated')
    site_any = next(iter(pages.values()), None)
    ov['official_website'] = (found('https://www.pangasinan.gov.ph/', site_any['evidence'])
                              if site_any else missing('provincial_site_not_captured'))
    ov['coordinates'] = missing('no_official_source_collected')
    ov['seal_logo'] = missing('not_collected; usage permission requires human review')
    footer = quote_field(site_any, r'All content is in the public domain unless otherwise stated\.', lambda m: m[0]) if site_any else None
    ov['site_license_statement'] = footer or missing('not_found')

    # Gaps: every null field, with its reason.
    for rec in [ov, *lgu_records, *barangays]:
        for key, field in rec.items():
            if isinstance(field, dict) and 'missing_reason' in field:
                gaps.append({'record_id': rec['id'], 'level': rec['geographic_level'], 'field': key,
                             'reason': field['missing_reason']})

    # Population reconciliation (reported, not corrected).
    for parent_code, kids in children.items():
        if parent_code is None:
            continue
        parent_value = value(population(parent_code, 2024))
        kid_values = [value(population(k['psgc'], 2024)) for k in kids]
        if parent_value is not None and all(v is not None for v in kid_values) and parent_value != sum(kid_values):
            issues.append({'type': 'population_2024_child_sum_differs', 'psgc': parent_code,
                           'values': {'parent': parent_value, 'children_sum': sum(kid_values)}})

    meta = {'review_status': 'pending', 'is_mock': False, 'publication_status': 'not_approved',
            'run_id': run.id, 'psgc_release': geography_release, 'population_release': population_release,
            'population_reference': 'year as published by PSA; census reference date not stated in source'}
    write_json(out / 'pangasinan_overview.json', {**meta, 'record': ov})
    write_json(out / 'pangasinan_lgus.json', {**meta, 'records': lgu_records})
    write_json(out / 'pangasinan_barangays.json', {**meta, 'records': barangays})
    write_json(out / 'inconsistencies.json', {**meta, 'issues': issues})
    write_csv(out / 'lgu_directory.csv', [{
        'psgc': r['psgc'], 'name': value(r['name']), 'classification': value(r['classification']),
        'income_classification': value(r['income_classification']),
        'legislative_district': value(r['legislative_district']),
        'population_2024': value(r['population_2024']), 'land_area_ha': value(r['land_area_ha']),
        'barangay_count': value(r['barangay_count']), 'website': value(r['website']),
        'facebook': value(r['facebook']), 'provincial_page': r['provincial_page'],
        'psgc_release': geography_release, 'population_release': population_release, 'review_status': 'pending',
    } for r in lgu_records], ['psgc', 'name', 'classification', 'income_classification', 'legislative_district',
                              'population_2024', 'land_area_ha', 'barangay_count', 'website', 'facebook',
                              'provincial_page', 'psgc_release', 'population_release', 'review_status'])
    write_csv(out / 'collection_gaps.csv', gaps, ['record_id', 'level', 'field', 'reason'])
    write_csv(out / 'source_inventory.csv', [{
        'source_id': e['artifact_sha256'][:12], **e} for e in run.manifest['evidence']],
        ['source_id', 'source', 'agency', 'title', 'source_url', 'final_url', 'retrieved_at', 'http_status',
         'content_type', 'role', 'version', 'page', 'page_number', 'collection_method', 'response_sha256',
         'artifact_sha256', 'artifact_redacted', 'artifact', 'bytes'])
    write_csv(out / 'collection_log.csv', [
        *({'at': e['retrieved_at'], 'source': e['source'], 'event': 'captured', 'detail': e['artifact'],
           'http_status': e.get('http_status')} for e in run.manifest['evidence']),
        *({'at': e['at'], 'source': e['source'], 'event': f'error:{e["stage"]}', 'detail': e['code'],
           'http_status': None} for e in run.manifest['errors'])], ['at', 'source', 'event', 'detail', 'http_status'])
    summary = {
        'run_id': run.id, 'manifest_evidence_sha256': sha256(json.dumps(run.manifest['evidence'], sort_keys=True).encode()),
        'psgc_release': geography_release, 'population_release': population_release,
        'counts': {lvl: sum(r['level'] == lvl for r in geo.values()) for lvl in ('Prov', 'City', 'Mun', 'Bgy')},
        'site_pages_matched': len(page_for), 'gaps': len(gaps), 'inconsistencies': len(issues),
        'files': {p.name: sha256(p.read_bytes()) for p in sorted(out.iterdir())},
    }
    write_json(out / 'build.json', summary)
    return {k: summary[k] for k in ('psgc_release', 'population_release', 'counts', 'site_pages_matched',
                                    'gaps', 'inconsistencies')}
