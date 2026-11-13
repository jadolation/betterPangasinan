"""Better Pangasinan web crawler CLI.  Usage: .venv/bin/python web-crawler <command> --help"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crawler import cli  # noqa: E402

if __name__ == '__main__':
    sys.exit(cli.main(sys.argv[1:]))
