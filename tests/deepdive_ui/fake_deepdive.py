"""Stand-in for `python -m app.deepdive` in RunManager tests.

Options before the CLI arguments steer the fake; everything after is echoed so
the test can check the argv the manager built. Never writes a file itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--exit", type=int, default=0)
    parser.add_argument("--wait-for", default=None)
    parser.add_argument("--no-dossier", action="store_true")
    own, rest = parser.parse_known_args()
    if own.wait_for:
        deadline = time.monotonic() + 30
        while not Path(own.wait_for).exists() and time.monotonic() < deadline:
            time.sleep(0.02)
    print("ARGV " + json.dumps(rest))
    print("ENV " + json.dumps({k: os.environ.get(k) for k in ("PYTHONUNBUFFERED",)}))
    print("STDIN_TTY " + str(sys.stdin.isatty()))
    print("✗ Peer XYZ nicht gefunden")
    sys.stderr.write("stderr line\n")
    if not own.no_dossier:
        print("Dossier written to: output/Watchlist/FAKE_2026-10-24.md")
    return own.exit


if __name__ == "__main__":
    sys.exit(main())
