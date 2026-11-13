"""FY2027 review export reads the approved snapshot without changing it."""
import csv
import json
import tempfile
from pathlib import Path

import pytest

from crawler.budget import export_review
from crawler.runs import ROOT, STAGING


def test_real_snapshot_review_preserves_values_and_inputs():
    STAGING.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=STAGING) as folder:
        target = Path(folder) / 'review'
        manifest = export_review(target)
        assert manifest['inputs_unchanged'] and not manifest['fresh_acquisition']
        with (target / 'national_budget_2027_review.csv').open() as stream:
            rows = list(csv.DictReader(stream))
        assert len(rows) == manifest['project_count']
        for row in rows:
            original = json.loads(row['original_record'])
            for field in ('nep_php', 'hgab2_php', 'hgab3_php'):
                assert row[field] == ('' if original['upstream'].get(field) is None else str(original['upstream'][field]))
        with pytest.raises(ValueError):
            export_review(target)


@pytest.mark.parametrize('target', ['data/national_budget/approved/review', 'data/staging/elsewhere', '/tmp/review'])
def test_destination_outside_crawler_staging_rejected(target):
    with pytest.raises(ValueError):
        export_review(ROOT / target)
