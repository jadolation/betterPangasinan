import copy
import json
from pathlib import Path
import pytest
import jsonschema
from scripts.geography_data import publication_payload, contains, interior_point

ROOT = Path(__file__).resolve().parents[2]


def test_geography_bundle():
    payload = publication_payload(ROOT)
    schema = json.loads((ROOT / 'schemas/geography_bundle.schema.json').read_text())
    jsonschema.Draft202012Validator(schema).validate(payload)
    features = payload['data/geography/municipalities.geojson']['features']
    assert len(features) == 48
    barangays = payload['data/geography/barangays.json']
    assert len(barangays) == 1364
    assert len({b['psgc'] for b in barangays}) == 1364
    assert len({b['parent_psgc'] for b in barangays}) == 48
    assert sum(f['properties']['barangay_count'] for f in features) == len(barangays)
    assert all(b['psgc'] == b['raw_code'] and 'Unversioned' in b['release'] for b in barangays)
    assert len({f['properties']['source_shape_id'] for f in features}) == 48
    manifest = payload['data/geography/manifest.json']
    assert manifest['boundary_metadata']['boundaryYearRepresented'] == '2020'
    assert manifest['registry_release'] == '2025-07-31'
    assert manifest['barangay_source']['psa_release'] is None
    assert manifest['barangay_source']['official'] is False
    assert manifest['barangay_source']['verified_parent_count'] == 48
    assert all('3.0' in f['properties']['license'] for f in features)


@pytest.mark.parametrize('mutation', ['duplicate', 'parent', 'ring', 'license', 'barangay_parent', 'barangay_duplicate', 'count', 'shape'])
def test_reject_corruption(tmp_path, mutation):
    folder = tmp_path / 'data/geography'
    folder.mkdir(parents=True)
    payload = copy.deepcopy(publication_payload(ROOT))
    features = payload['data/geography/municipalities.geojson']['features']
    if mutation == 'duplicate':
        features.append(features[0])
    elif mutation == 'parent':
        features[0]['properties']['psgc'] = '9999999999'
    elif mutation == 'license':
        features[0]['properties']['license'] = ''
    elif mutation == 'barangay_parent':
        payload['data/geography/barangays.json'][0]['parent_psgc'] = '9999999000'
    elif mutation == 'barangay_duplicate':
        payload['data/geography/barangays.json'].append(payload['data/geography/barangays.json'][0])
    elif mutation == 'count':
        features[0]['properties']['barangay_count'] += 1
    elif mutation == 'shape':
        features[1]['properties']['source_shape_id'] = features[0]['properties']['source_shape_id']
    else:
        features[0]['geometry'] = {'type': 'Polygon', 'coordinates': [[[120, 16], [121, 16], [121, 17]]]}
    for path, obj in payload.items():
        (tmp_path / path).write_text(json.dumps(obj))
    (tmp_path / 'pangasinan_lgu_registry_staging.json').write_bytes((ROOT / 'pangasinan_lgu_registry_staging.json').read_bytes())
    with pytest.raises(ValueError):
        publication_payload(tmp_path)


def test_containment_excludes_holes_and_handles_multiple_components():
    geometry = {'type': 'MultiPolygon', 'coordinates': [
        [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
         [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]]],
        [[[20, 20], [21, 20], [21, 21], [20, 21], [20, 20]]]]}
    assert contains(geometry, [2, 2])
    assert contains(geometry, [20.5, 20.5])
    assert not contains(geometry, [5, 5])
    assert not contains(geometry, [15, 15])
    assert contains(geometry, interior_point(geometry))
