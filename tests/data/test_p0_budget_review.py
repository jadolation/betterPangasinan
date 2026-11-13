import csv
import json
from pathlib import Path
import tempfile
import pytest
from scripts.p0_budget_review import ROOT, export_review


def test_real_snapshot_review_preserves_values_and_inputs():
    staging = ROOT / 'data/staging'
    staging.mkdir(exist_ok=True, parents=True)
    with tempfile.TemporaryDirectory(dir=staging) as folder:
        target = Path(folder) / 'review'
        manifest = export_review(target)
        assert manifest['project_count'] == 732
        assert manifest['inputs_unchanged'] and not manifest['fresh_acquisition']
        with (target / 'national_budget_2027_review.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == 732
        for row in rows:
            original = json.loads(row['original_record'])
            for field in ('nep_php', 'hgab2_php', 'hgab3_php'):
                assert row[field] == ('' if original['upstream'].get(field) is None else str(original['upstream'][field]))
        with pytest.raises(ValueError):
            export_review(target)


def test_production_destination_rejected():
    with pytest.raises(ValueError):
        export_review(ROOT / 'data/production/forbidden-review')
