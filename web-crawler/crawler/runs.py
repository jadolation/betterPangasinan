"""Run directories, evidence files and manifests.

A run is data/staging/web-crawler/runs/<run_id>/ containing:
  manifest.json   sources requested, evidence inventory with hashes, errors
  evidence/       immutable raw captures (credential-redacted where needed)
  output/         derived review-only files, rebuilt deterministically from evidence
  verification.json
"""
import hashlib
import json
import os
import secrets
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STAGING = ROOT / 'data' / 'staging' / 'web-crawler'
RUNS = STAGING / 'runs'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def file_sha256(path):
    return sha256(Path(path).read_bytes())


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')


def read_json(path):
    return json.loads(Path(path).read_bytes())


def git_commit():
    try:
        out = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(['git', 'status', '--porcelain', '--', 'web-crawler'], cwd=ROOT,
                               capture_output=True, text=True, timeout=5).stdout.strip()
        return out.stdout.strip() + ('+dirty' if dirty else '')
    except (OSError, subprocess.SubprocessError):
        return None


def resolve_run(value):
    """Accept a run ID or a path; refuse anything outside the runs directory."""
    path = Path(value)
    path = (path if path.is_absolute() or os.sep in value else RUNS / value).resolve()
    if path.parent != RUNS.resolve() or not (path / 'manifest.json').is_file():
        raise ValueError(f'not a run directory: {value}')
    return path


def list_runs():
    return sorted((p for p in RUNS.glob('*') if (p / 'manifest.json').is_file()), key=lambda p: p.name)


class Run:
    def __init__(self, path):
        self.path = Path(path)
        self.id = self.path.name
        self.manifest = read_json(self.path / 'manifest.json')

    @classmethod
    def create(cls, sources, options):
        RUNS.mkdir(parents=True, exist_ok=True)
        run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(2)
        path = RUNS / run_id
        (path / 'evidence').mkdir(parents=True)
        write_json(path / 'manifest.json', {
            'run_id': run_id, 'created_at': now(), 'tool_commit': git_commit(),
            'sources': sources, 'options': options, 'status': 'collecting',
            'is_mock': False, 'review_status': 'pending', 'publication_status': 'not_approved',
            'evidence': [], 'errors': [],
        })
        return cls(path)

    def save_manifest(self):
        write_json(self.path / 'manifest.json', self.manifest)

    def add_evidence(self, source, name, data, **meta):
        """Write one immutable evidence file and record its hash and provenance."""
        if '/' in name or name.startswith('.'):
            raise ValueError('unsafe_evidence_name')
        folder = self.path / 'evidence' / source
        folder.mkdir(exist_ok=True)
        with open(folder / name, 'xb') as stream:
            stream.write(data)
        entry = {'source': source, 'artifact': f'evidence/{source}/{name}', 'artifact_sha256': sha256(data),
                 'bytes': len(data), **meta}
        self.manifest['evidence'].append(entry)
        self.save_manifest()
        return entry

    def record_error(self, source, stage, code, **detail):
        self.manifest['errors'].append({'source': source, 'stage': stage, 'code': code, 'at': now(), **detail})
        self.save_manifest()

    def evidence(self, source=None, **match):
        return [e for e in self.manifest['evidence']
                if (source is None or e['source'] == source) and all(e.get(k) == v for k, v in match.items())]

    def read(self, entry):
        data = (self.path / entry['artifact']).read_bytes()
        if sha256(data) != entry['artifact_sha256']:
            raise ValueError(f'evidence_hash_mismatch:{entry["artifact"]}')
        return data
