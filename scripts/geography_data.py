"""Collect attributable geography; validate the publication bundle without network access."""
import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

API = 'https://www.geoboundaries.org/api/current/gbOpen/PHL/ADM3/'
BARANGAY_SOURCES = [
    'https://psa.gov.ph/classification/psgc/barangays/0105500000',
    'https://publicpsgc.gitlab.io/',
]
ALIASES = {'City of Dagupan': 'Dagupan City', 'City of San Carlos': 'San Carlos City'}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def collect(root):
    folder = root / 'data/geography'
    raw = folder / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    sources = []

    def fetch(url, filename, limit=40_000_000, text=False):
        previous = folder / 'manifest.json'
        if previous.exists() and (raw / filename).exists():
            body = (raw / filename).read_bytes()
            for source in json.loads(previous.read_text())['sources']:
                if source['url'] == url and source['sha256'] == digest(body):
                    sources.append(source)
                    return body.decode() if text else json.loads(body)
        request = Request(url, headers={'User-Agent': 'BetterPangasinan/1.0 geography source review'})
        with urlopen(request, timeout=120) as response:
            body = response.read(limit + 1)
        if len(body) > limit:
            raise ValueError('Source exceeds bounded download size')
        (raw / filename).write_bytes(body)
        sources.append({'url': url, 'retrieved_at': datetime.now(timezone.utc).isoformat(),
                        'sha256': digest(body), 'bytes': len(body)})
        return body.decode() if text else json.loads(body)

    meta = fetch(API, 'geoboundaries-api.json')
    url = meta['simplifiedGeometryGeoJSON'].replace('https://github.com/', 'https://media.githubusercontent.com/media/').replace('/raw/', '/')
    national = fetch(url, 'adm3-simplified.geojson')
    province_meta = fetch(API.replace('ADM3', 'ADM2'), 'adm2-api.json')
    province_url = province_meta['simplifiedGeometryGeoJSON'].replace('https://github.com/', 'https://media.githubusercontent.com/media/').replace('/raw/', '/')
    provinces = fetch(province_url, 'adm2-simplified.geojson')
    province_matches = [f for f in provinces['features'] if f['properties']['shapeName'] == 'Pangasinan']
    if len(province_matches) != 1 or province_meta['boundaryLicense'] != meta['boundaryLicense']:
        raise ValueError('Unique, identically licensed Pangasinan province required')
    province = province_matches[0]
    starter = json.loads((root / 'pangasinan_lgu_registry_staging.json').read_text())
    features = []
    for lgu in starter['lgus']:
        name = ALIASES.get(lgu['name'], lgu['name'])
        candidates = []
        for feature in national['features']:
            if feature['properties']['shapeName'].casefold() != name.casefold():
                continue
            point = interior_point(feature['geometry'])
            if contains(province['geometry'], point):
                candidates.append(feature)
        if len(candidates) != 1:
            print('Unresolved unique match:', lgu['name'], len(candidates))
            continue
        feature = candidates[0]
        features.append({'type': 'Feature', 'geometry': feature['geometry'], 'properties': {
            'id': 'lgu-' + lgu['psgc'], 'psgc': lgu['psgc'], 'name': lgu['name'],
            'classification': lgu['classification'], 'population_2024': lgu['population_2024'],
            'barangay_count': None, 'source_shape_id': feature['properties']['shapeID'],
            'source_name': feature['properties']['shapeName'], 'source_url': url,
            'license': meta['boundaryLicense'], 'release': meta['buildDate'],
            'source_sha256': sources[1]['sha256']}})
    attempts = []
    for source in BARANGAY_SOURCES:
        try:
            fetch(source, 'barangay-source-' + str(len(attempts)) + '.json', 5_000_000)
            status = 'Response received; not parsed or approved for publication'
        except (HTTPError, OSError, ValueError) as exc:
            status = str(exc)
        attempts.append({'url': source, 'attempted_at': datetime.now(timezone.utc).isoformat(), 'result': status})
    barangays = []
    barangay_release = None
    try:
        cloud_parents_url = 'https://psgc.cloud/api/provinces/0105500000/cities-municipalities'
        cloud_url = 'https://psgc.cloud/api/provinces/0105500000/barangays'
        cloud_parents = fetch(cloud_parents_url, 'cloud-parents.json')
        expected = {row['psgc']: row['name'] for row in starter['lgus']}
        actual = {row['code']: row['name'].strip() for row in cloud_parents}
        if len(cloud_parents) != 48 or actual != expected:
            raise ValueError('Cloud parent code/name crosswalk differs from reviewed 48')
        cloud_rows = fetch(cloud_url, 'cloud-barangays.json')
        terms = fetch('https://psgc.cloud/terms', 'cloud-terms.html', text=True)
        if not all(text in terms for text in ('2025-08-09', 'lawful, standardized reference purposes', 'nor modify our open data attributions')):
            raise ValueError('PSGC Cloud terms changed; new publication review required')
        fetch('https://psgc.cloud/api-docs', 'cloud-docs.html', text=True)
        source = next(s for s in sources if s['url'] == cloud_url)
        barangay_release = 'Unversioned PSGC Cloud snapshot retrieved ' + source['retrieved_at']
        for row in cloud_rows:
            code = row['code']
            parent = code[:7] + '000'
            if len(code) != 10 or not code.isdigit() or parent not in expected:
                raise ValueError('Cloud barangay code does not belong to verified parent')
            barangays.append({'psgc': code, 'raw_code': code, 'parent_psgc': parent,
                              'parent_id': 'lgu-' + parent, 'name': row['name'],
                              'source_url': cloud_url, 'source_sha256': source['sha256'],
                              'publisher': 'PSGC Cloud (John Joshua A. Lipio), unofficial mirror',
                              'release': barangay_release,
                              'license': 'PSGC Cloud Terms of Service 2025-08-09: lawful standardized read-only geographic reference use; preserve attribution',
                              'license_url': 'https://psgc.cloud/terms',
                              'parent_mapping': '10-digit source code first seven digits plus 000; all 48 source parent codes and trimmed official names verified against supplied PSA registry. No 9-digit conversion.'})
    except (HTTPError, OSError, ValueError, KeyError) as exc:
        barangays = []
        attempts.append({'url': 'https://psgc.cloud/api', 'attempted_at': datetime.now(timezone.utc).isoformat(), 'result': str(exc)})
    for feature in features:
        if barangays:
            feature['properties']['barangay_count'] = sum(b['parent_psgc'] == feature['properties']['psgc'] for b in barangays)
    geometry = {'type': 'FeatureCollection', 'features': features}
    manifest = {'version': 1, 'municipality_count': len(features), 'expected_municipality_count': 48,
                'geometry_status': 'complete' if len(features) == 48 else 'partial',
                'barangay_status': 'complete' if barangays and len({b['parent_psgc'] for b in barangays}) == 48 else 'unavailable', 'barangay_count': len(barangays),
                'barangay_note': ('Barangays from an unofficial, unversioned PSGC Cloud snapshot; not verified as the latest PSA release. ' + barangay_release) if barangays else 'No verified, licensed barangay release collected. Zero published records is not a count of actual barangays.',
                'barangay_source': {'publisher': 'PSGC Cloud (John Joshua A. Lipio)', 'official': False,
                                    'psa_release': None, 'snapshot_release': barangay_release,
                                    'documentation_url': 'https://psgc.cloud/api-docs',
                                    'terms_url': 'https://psgc.cloud/terms',
                                    'terms_date': '2025-08-09',
                                    'license_note': 'Custom reference-use terms, not a Creative Commons license; no official release currency asserted.',
                                    'verified_parent_count': len(actual) if barangays else 0,
                                    'verified_parent_crosswalk': actual if barangays else {}},
                'sources': sources, 'barangay_attempts': attempts, 'boundary_metadata': meta,
                'province_boundary_metadata': province_meta,
                'matching': {'aliases': ALIASES, 'province_shape_id': province['properties']['shapeID'], 'rule': 'Exact case-insensitive source name; area centroid of largest polygon if interior, otherwise deterministic 39x39 interior grid point. Ray-casting point-in-polygon against actual ADM2 Pangasinan exterior minus holes, all components. Exactly one source candidate and globally unique shape ID required. This tests an interior representative point, not full polygon containment; simplified edges may differ. No bounding-box-only assignment.'},
                'registry_sha256': digest((root / 'pangasinan_lgu_registry_staging.json').read_bytes()),
                'registry_source_url': starter['metadata']['url'],
                'registry_release': starter['metadata']['administrative_listing_as_of'],
                'attribution': 'NAMRIA, PSA and OCHA Philippines via geoBoundaries. CC BY 3.0 IGO. Simplified boundaries matched to the supplied reviewed registry; not a legal boundary survey.',
                'license_url': 'https://creativecommons.org/licenses/by/3.0/igo/'}
    for name, obj in [('manifest.json', manifest), ('barangays.json', barangays), ('municipalities.geojson', geometry)]:
        (folder / name).write_text(json.dumps(obj, ensure_ascii=True, separators=(',', ':')) + '\n')
    publication_payload(root)


def coordinates(value):
    if isinstance(value, list) and len(value) >= 2 and all(isinstance(n, (float, int)) for n in value):
        yield value
    elif isinstance(value, list):
        for child in value:
            yield from coordinates(child)


def in_ring(ring, point):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:]):
        if (a[1] > y) != (b[1] > y) and x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]:
            inside = not inside
    return inside


def contains(geometry, point):
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    return any(in_ring(p[0], point) and not any(in_ring(hole, point) for hole in p[1:]) for p in polygons)


def interior_point(geometry):
    polygons = [geometry['coordinates']] if geometry['type'] == 'Polygon' else geometry['coordinates']
    def area(ring):
        return sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
    ring = max(polygons, key=lambda p: abs(area(p[0])))[0]
    cross = area(ring)
    if cross:
        point = [sum((a[i] + b[i]) * (a[0] * b[1] - b[0] * a[1]) for a, b in zip(ring, ring[1:])) / (3 * cross) for i in (0, 1)]
        if contains(geometry, point):
            return point
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    for i in range(1, 40):
        for j in range(1, 40):
            point = [min(xs) + (max(xs) - min(xs)) * i / 40, min(ys) + (max(ys) - min(ys)) * j / 40]
            if contains(geometry, point):
                return point
    raise ValueError('No defensible interior representative point')


def publication_payload(root):
    root = Path(root)
    payload = {f'data/geography/{name}': json.loads((root / 'data/geography' / name).read_text())
               for name in ('manifest.json', 'barangays.json', 'municipalities.geojson')}
    manifest, barangays, geo = payload.values()
    registry = json.loads((root / 'pangasinan_lgu_registry_staging.json').read_text())['lgus']
    parents = {row['psgc']: row for row in registry}
    if len(parents) != 48 or len(registry) != 48:
        raise ValueError('Registry must contain 48 unique PSGC codes')
    if manifest['registry_sha256'] != digest((root / 'pangasinan_lgu_registry_staging.json').read_bytes()):
        raise ValueError('Reviewed registry changed; recollect and review geography')
    evidence = {source['url']: source['sha256'] for source in manifest['sources']}
    approved_license = manifest['boundary_metadata']['boundaryLicense']
    if approved_license != 'Creative Commons Attribution 3.0 Intergovernmental Organisations (CC BY 3.0 IGO)':
        raise ValueError('Boundary license requires a new review')
    if barangays:
        source_info = manifest['barangay_source']
        if source_info['verified_parent_crosswalk'] != {code: row['name'] for code, row in parents.items()} or source_info['verified_parent_count'] != 48:
            raise ValueError('Barangay source crosswalk does not match all reviewed parents')
        if source_info['official'] is not False or source_info['psa_release'] is not None:
            raise ValueError('Mirror must not claim an official PSA release')
    seen = set()
    shapes = set()
    for feature in geo['features']:
        p, g = feature['properties'], feature['geometry']
        code = p['psgc']
        if code in seen or code not in parents or p['id'] != 'lgu-' + code:
            raise ValueError('Duplicate or unmapped municipality PSGC')
        seen.add(code)
        if p['source_shape_id'] in shapes:
            raise ValueError('Source geometry reused for different municipalities')
        shapes.add(p['source_shape_id'])
        if any(p[key] != parents[code][key] for key in ('name', 'classification', 'population_2024')):
            raise ValueError('Registry attributes differ')
        if p['source_name'].casefold() != ALIASES.get(parents[code]['name'], parents[code]['name']).casefold():
            raise ValueError('Unreviewed source-name alias')
        if not p['source_url'].startswith('https://') or not p['license'] or not p['release'] or len(p['source_sha256']) != 64:
            raise ValueError('Missing licensed provenance')
        if p['license'] != approved_license or evidence.get(p['source_url']) != p['source_sha256']:
            raise ValueError('Boundary provenance does not match collected evidence')
        if g['type'] not in ('Polygon', 'MultiPolygon'):
            raise ValueError('Invalid geometry type')
        polygons = [g['coordinates']] if g['type'] == 'Polygon' else g['coordinates']
        if not polygons:
            raise ValueError('Empty geometry')
        for polygon in polygons:
            if not polygon:
                raise ValueError('Empty polygon')
            for ring in polygon:
                if len(ring) < 4 or ring[0] != ring[-1]:
                    raise ValueError('Unclosed geometry ring')
                for point in ring:
                    if len(point) != 2 or not all(math.isfinite(n) for n in point) or not (-180 <= point[0] <= 180 and -90 <= point[1] <= 90):
                        raise ValueError('Invalid coordinate')
    codes = set()
    for row in barangays:
        if row['psgc'] in codes or row['parent_psgc'] not in parents:
            raise ValueError('Duplicate barangay or invalid parent')
        codes.add(row['psgc'])
        if not all(row.get(k) for k in ('name', 'source_url', 'release', 'license', 'source_sha256')):
            raise ValueError('Missing barangay provenance')
        if evidence.get(row['source_url']) != row['source_sha256'] or row['parent_id'] != 'lgu-' + row['parent_psgc']:
            raise ValueError('Invalid barangay evidence or parent identifier')
        if len(row['psgc']) != 10 or not row['psgc'].isdigit() or row['psgc'][:7] + '000' != row['parent_psgc']:
            raise ValueError('Invalid barangay code hierarchy')
    for feature in geo['features']:
        count = sum(row['parent_psgc'] == feature['properties']['psgc'] for row in barangays)
        if barangays and feature['properties']['barangay_count'] != count:
            raise ValueError('Barangay count does not reconcile')
    if manifest['municipality_count'] != len(seen) or manifest['barangay_count'] != len(barangays):
        raise ValueError('Manifest coverage differs')
    if manifest['geometry_status'] == 'complete' and len(seen) != 48:
        raise ValueError('False complete coverage')
    return payload


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--collect', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.collect:
        collect(root)
    else:
        publication_payload(root)
