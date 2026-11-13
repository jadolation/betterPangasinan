"""Command-line interface. Every command prints JSON and exits non-zero on failure."""
import argparse
import json

from . import net
from .runs import Run, list_runs, resolve_run
from .sources import PROVINCE_PAGES, SOURCES


def cmd_sources(args):
    return {name: {k: v for k, v in spec.items() if k != 'collect'} for name, spec in SOURCES.items()}, 0


def cmd_collect(args):
    if not args.authorize_live:
        raise SystemExit('collect contacts live official sources; pass --authorize-live')
    names = args.source or list(SOURCES)
    unknown = set(names) - set(SOURCES)
    if unknown:
        raise SystemExit(f'unknown source(s): {", ".join(sorted(unknown))}')
    options = {'psa_versions': args.psa_version, 'pages': args.page, 'lgu_limit': args.lgu_limit}
    run = Run.create(names, options)
    for name in names:
        try:
            SOURCES[name]['collect'](run, options)
            run.manifest.setdefault('source_status', {})[name] = 'collected'
        except (net.FetchError, OSError, ValueError, KeyError) as error:
            code = str(error) if isinstance(error, net.FetchError) else type(error).__name__
            run.record_error(name, 'collect', code)
            run.manifest.setdefault('source_status', {})[name] = 'failed'
    run.manifest['status'] = 'collected' if not run.manifest['errors'] else 'collected_with_errors'
    run.save_manifest()
    result = {'run_id': run.id, 'status': run.manifest['status'], 'source_status': run.manifest['source_status'],
              'evidence_files': len(run.manifest['evidence']), 'errors': run.manifest['errors']}
    if args.build:
        from .build import build
        result['build'] = build(run.path)
    return result, 0 if run.manifest['status'] == 'collected' else 1


def cmd_build(args):
    from .build import BuildError, build
    try:
        return build(resolve_run(args.run)), 0
    except BuildError as error:
        return {'run_id': args.run, 'build': 'failed', 'error': str(error)}, 1


def cmd_verify(args):
    from .verify import verify
    result = verify(resolve_run(args.run), update_checklist=not args.no_checklist)
    failed = [c['check'] for c in result['checks'] if c['result'] != 'pass']
    return {k: result[k] for k in ('run_id', 'validation_status', 'collection_completeness',
                                   'publication_approval', 'inconsistency_counts')} | {'failed_checks': failed}, \
        0 if result['validation_status'] == 'passed' else 1


def cmd_status(args):
    from .verify import staleness
    path = resolve_run(args.run)
    return {'run_id': path.name, 'verification': staleness(path)}, 0


def cmd_budget_review(args):
    from .budget import export_review
    return export_review(args.target), 0


def cmd_runs(args):
    from .verify import staleness
    rows = []
    for path in list_runs():
        m = Run(path).manifest
        verification = path / 'verification.json'
        rows.append({'run_id': m['run_id'], 'created_at': m['created_at'], 'status': m['status'],
                     'sources': m.get('source_status'), 'errors': len(m['errors']),
                     'verified': json.loads(verification.read_text()).get('validation_status')
                     if verification.is_file() else None, 'verification': staleness(path)})
    return rows, 0


def main(argv):
    parser = argparse.ArgumentParser(prog='web-crawler', description='Better Pangasinan P0 collection (review-only).')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('sources', help='list registered sources').set_defaults(func=cmd_sources)
    p = sub.add_parser('collect', help='capture live evidence into a new run')
    p.add_argument('--authorize-live', action='store_true', help='confirm live requests to official sources')
    p.add_argument('--source', action='append', choices=sorted(SOURCES), help='repeatable; default: all')
    p.add_argument('--psa-version', action='append', help='PSGC version(s) to probe, e.g. Q3_2026')
    p.add_argument('--page', action='append', choices=sorted(PROVINCE_PAGES), help='provincial page(s)')
    p.add_argument('--lgu-limit', type=int, help='capture only the first N LGU detail pages (0: none)')
    p.add_argument('--build', action='store_true', help='build outputs after collection')
    p.set_defaults(func=cmd_collect)
    p = sub.add_parser('build', help='rebuild outputs from saved evidence (offline)')
    p.add_argument('run', help='run ID or path')
    p.set_defaults(func=cmd_build)
    p = sub.add_parser('verify', help='independently verify a built run and update doc/P0-VERIFICATION.md')
    p.add_argument('run', help='run ID or path')
    p.add_argument('--no-checklist', action='store_true', help='do not update doc/P0-VERIFICATION.md')
    p.set_defaults(func=cmd_verify)
    p = sub.add_parser('status', help='is the saved verification current or stale?')
    p.add_argument('run', help='run ID or path')
    p.set_defaults(func=cmd_status)
    p = sub.add_parser('budget-review', help='read-only FY2027 review export of the approved snapshot')
    p.add_argument('--target', help='fresh directory under data/staging/web-crawler (default: timestamped)')
    p.set_defaults(func=cmd_budget_review)
    sub.add_parser('runs', help='list runs').set_defaults(func=cmd_runs)
    args = parser.parse_args(argv)
    result, code = args.func(args)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return code
