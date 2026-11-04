"""Real-source artifact collection and read-only P0 review commands. No approval/publication API."""

import argparse
import json
from pathlib import Path
import sys

from collector.exporters import export_run, safe_target
from collector.persistence import Store
from collector.pipeline import collect, validate_records

ROOT = Path(__file__).resolve().parents[1]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("collect", "validate", "export", "report"):
        command = sub.add_parser(name)
        command.add_argument("--source", choices=["psa_psgc"], default="psa_psgc")
        command.add_argument(
            "--state-dir", type=Path, default=ROOT / "data/staging/collector"
        )
        if name == "collect":
            command.add_argument(
                "--input",
                type=Path,
                required=True,
                help="Saved attributable source artifact; reviewed PSA transcription JSON is currently supported",
            )
        else:
            command.add_argument("--run-id", required=True)
        if name == "export":
            command.add_argument("--format", choices=["json,csv"], default="json,csv")
            command.add_argument("--target", type=Path, required=True)
    p0 = sub.add_parser("review-p0")
    p0.add_argument(
        "--target", type=Path, default=ROOT / "data/staging/Better_Pangasinan_Research"
    )
    args = parser.parse_args(argv)
    try:
        if args.command == "review-p0":
            from collector.p0 import export_p0

            result = export_p0(ROOT, args.target)
        else:
            state = safe_target(args.state_dir)
            store = Store(state / "staging.sqlite")
            if args.command == "collect":
                result = collect(args.input, state / "raw", store)
                export_run(result, state / "runs" / result["run_id"])
            else:
                result = store.report(args.run_id)
                result.update(result["run"])
                if result["source_id"] != args.source:
                    raise ValueError("Run belongs to another source")
                if args.command == "validate":
                    quality = validate_records(result["records"])
                    # Parser/acquisition failures cannot become successes after a recheck.
                    if result["quality"]["validation_status"] != "invalid":
                        result["quality"] = quality
                elif args.command == "export":
                    result = export_run(result, args.target)
        print(json.dumps(result, ensure_ascii=True, sort_keys=True, allow_nan=False))
        return int(result.get("quality", {}).get("validation_status") == "invalid")
    except (ValueError, OSError) as error:
        print(
            json.dumps({"error": type(error).__name__, "message": str(error)}),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
