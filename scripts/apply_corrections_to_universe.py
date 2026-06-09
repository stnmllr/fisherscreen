"""One-shot: apply the verified symbol corrections to data/universe.json in place.
Shared function with the live build (build_universe._apply_symbol_corrections), so
the committed universe.json and a future live rebuild agree exactly."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.build_universe import _apply_symbol_corrections

PATH = Path(__file__).parent.parent / "data" / "universe.json"


def main() -> None:
    tickers = json.loads(PATH.read_text(encoding="utf-8"))
    before = len(tickers)
    corrected = sorted(set(_apply_symbol_corrections(tickers)))
    PATH.write_text(json.dumps(corrected, indent=2), encoding="utf-8")
    print(f"universe.json: {before} -> {len(corrected)} (delta {before - len(corrected)})")


if __name__ == "__main__":
    main()
