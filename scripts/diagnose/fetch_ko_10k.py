"""One-shot authorized fetch: KO 10-K via the production code path.

Uses app.services.edgar_client.EdgarClientImpl + app.deepdive.filing_cache.
CachedFilingFetcher so the filing lands in cache/filings/<CIK>/<acc>.txt
exactly the way the deep-dive pipeline would create it.

Authorization scope: ONE filing. No fallback, no retry-on-different-ticker.
On any failure: raise and stop.
"""

from __future__ import annotations

import io
import logging
import os
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Load .env the same way the rest of the project does.
from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.deepdive.filing_cache import CachedFilingFetcher  # noqa: E402
from app.services.edgar_client import EdgarClientImpl  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

TICKER = "KO"
FORM = "10-K"
CACHE_DIR = Path(__file__).resolve().parents[1] / "cache" / "filings"


def main() -> None:
    ua = os.environ.get("FISHERSCREEN_EDGAR_USER_AGENT", "")
    edgar = EdgarClientImpl(user_agent=ua)
    cik = edgar.get_cik(TICKER)
    if not cik:
        raise SystemExit(f"FAIL: no CIK resolved for {TICKER}")
    print(f"resolved {TICKER} -> CIK {cik}")

    # Existing cache dirs are 10-digit padded; keep that layout.
    padded = cik.zfill(10)
    fetcher = CachedFilingFetcher(edgar=edgar, cache_dir=CACHE_DIR)
    filing = fetcher.get(cik=padded, form_type=FORM, use_cache=True)
    print(f"accession: {filing.accession_number}")
    print(f"filing_date: {filing.filing_date}")
    print(f"document_text length: {len(filing.document_text):,} chars")

    cache_file = CACHE_DIR / padded / f"{filing.accession_number}.txt"
    if cache_file.exists():
        print(f"cache file: {cache_file} (raw size {cache_file.stat().st_size:,} bytes)")
    else:
        raise SystemExit(f"FAIL: cache file not written at {cache_file}")


if __name__ == "__main__":
    main()
