#!/usr/bin/env python3
"""
Build data/universe.json from S&P 500 + S&P 400 + STOXX Europe 600.

Run: uv run python scripts/build_universe.py

Sources:
  S&P 500   Wikipedia — https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
  S&P 400   Wikipedia — https://en.wikipedia.org/wiki/List_of_S%26P_400_companies
  STOXX 600 Wikipedia — https://en.wikipedia.org/wiki/STOXX_Europe_600 (primary)
            iShares holdings CSV — two known URLs (Option B / C, both tried)
            Hardcoded fallback of ~55 major components (last resort)

Ticker normalisation to yfinance format:
  US tickers:    no suffix (AAPL, MSFT, BRK-B)
  EU tickers:    exchange suffix derived from Wikipedia country column
                 (.AS, .DE, .PA, .L, .SW, .CO, .MC, .MI, .ST, .OL, .HE, ...)
  Multi-class:   space replaced with hyphen (NOVO B → NOVO-B, then .CO suffix)

Wikipedia requires a properly identifying bot User-Agent per its policy (https://w.wiki/4wJS).
iShares and other financial sites use a browser-like User-Agent.
"""

import json
import logging
import re
from io import StringIO
from pathlib import Path

import httpx
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUEST_TIMEOUT = 30  # seconds

# Wikipedia's bot policy requires an identifying User-Agent including contact info.
WIKIPEDIA_UA = (
    "FisherScreen/1.0 (stn.mueller@gmail.com; fisherscreen-universe-builder) "
    "python-httpx"
)

# iShares and other financial sites prefer a browser-like UA.
BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

# Country → yfinance exchange suffix, based on STOXX 600 Wikipedia table.
# "Bermuda" and "Israel" are registered domiciles but the stocks trade on
# London/US exchanges; handled as special cases in _apply_country_suffix.
COUNTRY_SUFFIX: dict[str, str] = {
    "Austria": ".VI",
    "Belgium": ".BR",
    "Denmark": ".CO",
    "Finland": ".HE",
    "France": ".PA",
    "Germany": ".DE",
    "Greece": ".AT",
    "Ireland": ".IR",
    "Italy": ".MI",
    "Luxembourg": ".LU",
    "Netherlands": ".AS",
    "Norway": ".OL",
    "Poland": ".WA",
    "Portugal": ".LS",
    "Spain": ".MC",
    "Sweden": ".ST",
    "Switzerland": ".SW",
    "United Kingdom": ".L",
}

# iShares STOXX Europe 600 holdings CSV — two known URL patterns, tried in order.
ISHARES_URLS: list[str] = [
    (
        "https://www.ishares.com/uk/individual/en/products/251783/"
        "ishares-stoxx-europe-600-ucits-etf/1478372549651.ajax"
        "?fileType=csv&fileName=SXXP_holdings&dataType=fund"
    ),
    (
        "https://www.ishares.com/us/products/251781/"
        "ishares-stoxx-europe-600-ucits-etf-de-fund/1478372549651.ajax"
        "?fileType=csv&fileName=SXXP_holdings&dataType=fund"
    ),
]

# Exchange-code → yfinance suffix used when parsing iShares CSV "Exchange" column.
ISHARES_EXCHANGE_SUFFIX: dict[str, str] = {
    "Euronext Amsterdam": ".AS",
    "Amsterdam": ".AS",
    "XAMS": ".AS",
    "XETRA": ".DE",
    "Xetra": ".DE",
    "Deutsche Boerse Xetra": ".DE",
    "Frankfurt": ".DE",
    "Euronext Paris": ".PA",
    "Paris": ".PA",
    "XPAR": ".PA",
    "London Stock Exchange": ".L",
    "London": ".L",
    "XLON": ".L",
    "SIX Swiss Exchange": ".SW",
    "Swiss Exchange": ".SW",
    "Zurich": ".SW",
    "XSWX": ".SW",
    "Copenhagen": ".CO",
    "Nasdaq Copenhagen": ".CO",
    "XCSE": ".CO",
    "Madrid": ".MC",
    "BME": ".MC",
    "XMAD": ".MC",
    "Borsa Italiana": ".MI",
    "Milan": ".MI",
    "XMIL": ".MI",
    "Stockholm": ".ST",
    "Nasdaq Stockholm": ".ST",
    "XSTO": ".ST",
    "Oslo": ".OL",
    "Oslo Bors": ".OL",
    "XOSL": ".OL",
    "Helsinki": ".HE",
    "Nasdaq Helsinki": ".HE",
    "XHEL": ".HE",
    "Euronext Brussels": ".BR",
    "Brussels": ".BR",
    "XBRU": ".BR",
    "Euronext Lisbon": ".LS",
    "Lisbon": ".LS",
    "XLIS": ".LS",
    "Vienna": ".VI",
    "Wiener Boerse": ".VI",
    "XWBO": ".VI",
    "Warsaw": ".WA",
    "XWAR": ".WA",
    "Euronext Dublin": ".IR",
    "Dublin": ".IR",
    "XDUB": ".IR",
    "Athens": ".AT",
    "XATH": ".AT",
    "Prague": ".PR",
    "XPRA": ".PR",
    "Budapest": ".BD",
    "XBUD": ".BD",
}

# Hardcoded fallback: major STOXX Europe 600 components in yfinance format.
# Used only when ALL other STOXX sources fail.
STOXX_FALLBACK: list[str] = [
    "ASML.AS", "NESN.SW", "NOVN.SW", "ROG.SW", "NOVO-B.CO",
    "SAP.DE", "SIE.DE", "AIR.PA", "TTE.PA", "MC.PA",
    "BNP.PA", "SAN.PA", "OR.PA", "AI.PA", "AZN.L",
    "HSBA.L", "SHEL.L", "BP.L", "GSK.L", "ULVR.L",
    "RIO.L", "LSEG.L", "BARC.L", "LLOY.L", "NWG.L",
    "PRU.L", "BATS.L", "INGA.AS", "PHIA.AS", "AD.AS",
    "HEIA.AS", "ALV.DE", "MUV2.DE", "BMW.DE", "VOW3.DE",
    "DBK.DE", "BAS.DE", "BAYN.DE", "MRK.DE", "DTE.DE",
    "ENEL.MI", "ISP.MI", "UCG.MI", "ENI.MI",
    "ITX.MC", "IBE.MC", "SAN.MC", "BBVA.MC", "REP.MC",
    "STM.PA", "STLAM.AS",
    "VOLV-B.ST", "ERIC-B.ST", "ATCO-A.ST",
    "UPM.HE", "FORTUM.HE", "NDA-FI.HE",
    "NOVO-B.CO", "MAERSK-B.CO", "DEMANT.CO",
]


# ---------------------------------------------------------------------------
# HTTP helper
# ---------------------------------------------------------------------------

def _get(url: str, *, timeout: int = REQUEST_TIMEOUT, user_agent: str = BROWSER_UA) -> str:
    """Fetch URL via httpx with the given User-Agent. Returns response text."""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        response = client.get(url, headers={"User-Agent": user_agent})
    response.raise_for_status()
    return response.text


# ---------------------------------------------------------------------------
# Ticker normalisation helpers
# ---------------------------------------------------------------------------

def _normalise_us_ticker(raw: str) -> str:
    """Convert Wikipedia dot-notation to yfinance dash-notation (BRK.B → BRK-B)."""
    return raw.strip().replace(".", "-")


# Trailing lowercase class letter on an otherwise upper/digit base, e.g. the
# Nordic source form "ERICb". The base must be >=2 chars so single-letter
# tickers like "A"/"Ab" are never touched; only a/b/c are recognised classes.
_CLASS_SUFFIX_RE = re.compile(r"^([A-Z0-9]{2,})([abc])$")


def _normalise_class_suffix(ticker: str) -> str:
    """Convert a trailing lowercase class letter on an otherwise upper/digit
    base into the hyphenated yfinance form: ERICb -> ERIC-B, ATCOa -> ATCO-A,
    TEL2b -> TEL2-B. Conservative: only fires on r'^[A-Z0-9]{2,}[abc]$' so it
    cannot touch normal tickers. All-caps concatenated forms (e.g. HMB) are
    deliberately NOT split — ambiguous, handled at the data level."""
    match = _CLASS_SUFFIX_RE.match(ticker)
    if match is None:
        return ticker
    base, class_letter = match.groups()
    return f"{base}-{class_letter.upper()}"


def _apply_country_suffix(raw_ticker: str, country: str) -> str | None:
    """
    Map a raw Wikipedia STOXX 600 ticker + country to a yfinance ticker.

    Rules applied in order:
    1. Spaces in the ticker are replaced with hyphens (class-share syntax).
    2. Country is looked up in COUNTRY_SUFFIX for the exchange suffix.
    3. Special cases: Bermuda-domiciled stocks trade in London (.L);
       Israel-domiciled Teva trades as TEVA (no suffix, US-listed).
       Luxembourg companies are diverse — keep .LU and let screener handle misses.

    Returns None when the ticker is blank or the country is not mapped.
    """
    ticker = raw_ticker.strip().replace(" ", "-")
    # Wikipedia LSE tickers arrive with a trailing dot (e.g. "BA.", "RR.", "SN.").
    # Strip trailing dot(s) before appending the suffix so we get "BA.L", not
    # "BA..L". Only trailing dots are removed — legit internal dots survive.
    ticker = ticker.rstrip(".")
    ticker = _normalise_class_suffix(ticker)
    if not ticker or ticker in ("-", "nan"):
        return None

    # Special domicile cases where country ≠ primary exchange.
    if country == "Bermuda":
        return f"{ticker}.L"
    if country == "Israel":
        # Teva trades on NYSE without suffix.
        return ticker  # e.g. TEV → TEV (will likely not resolve, low impact)

    suffix = COUNTRY_SUFFIX.get(country)
    if suffix is None:
        logger.debug("No suffix mapping for country '%s', ticker '%s' — skipped", country, ticker)
        return None

    return f"{ticker}{suffix}"


# ---------------------------------------------------------------------------
# iShares CSV parsing helper
# ---------------------------------------------------------------------------

def _parse_ishares_csv(csv_text: str) -> list[str]:
    """
    Parse iShares holdings CSV and return a list of yfinance-format tickers.

    The iShares CSV has metadata rows at the top before the actual column headers.
    We skip rows until we find the header row (which contains 'Ticker').
    """
    lines = csv_text.splitlines()

    header_index: int | None = None
    for i, line in enumerate(lines):
        if "Ticker" in line:
            header_index = i
            break

    if header_index is None:
        raise ValueError("Could not locate 'Ticker' column in iShares CSV")

    table_text = "\n".join(lines[header_index:])
    df = pd.read_csv(StringIO(table_text), dtype=str, on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    if "Ticker" not in df.columns:
        raise ValueError(f"'Ticker' column missing after parse. Columns: {list(df.columns)}")

    exchange_col = next(
        (c for c in df.columns if "exchange" in c.lower() or "location" in c.lower()),
        None,
    )

    tickers: list[str] = []
    skipped = 0

    for _, row in df.iterrows():
        raw_ticker = str(row.get("Ticker", "")).strip()
        exchange = str(row.get(exchange_col, "")) if exchange_col else ""

        ticker = raw_ticker.replace(" ", "-")
        ticker = _normalise_class_suffix(ticker)
        if not ticker or ticker in ("-", "nan"):
            continue

        suffix = ISHARES_EXCHANGE_SUFFIX.get(exchange.strip())
        if suffix:
            tickers.append(f"{ticker}{suffix}")
        else:
            skipped += 1
            logger.debug("iShares: unknown exchange '%s' for '%s' — skipped", exchange, ticker)

    if skipped:
        logger.warning("STOXX CSV: %d tickers skipped — exchange not in mapping", skipped)

    return tickers


# ---------------------------------------------------------------------------
# Fetch functions
# ---------------------------------------------------------------------------

def fetch_sp500() -> list[str]:
    """Fetch S&P 500 tickers from Wikipedia (table 0: 'Symbol' column)."""
    logger.info("Fetching S&P 500 from Wikipedia ...")
    html = _get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        user_agent=WIKIPEDIA_UA,
    )
    tables = pd.read_html(StringIO(html))
    tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
    clean = [str(t).strip() for t in tickers if str(t).strip()]
    logger.info("S&P 500: %d tickers fetched", len(clean))
    return clean


def fetch_sp400() -> list[str]:
    """Fetch S&P 400 Mid-Cap tickers from Wikipedia (table 0: 'Symbol' column)."""
    logger.info("Fetching S&P 400 from Wikipedia ...")
    html = _get(
        "https://en.wikipedia.org/wiki/List_of_S%26P_400_companies",
        user_agent=WIKIPEDIA_UA,
    )
    tables = pd.read_html(StringIO(html))
    tickers = tables[0]["Symbol"].str.replace(".", "-", regex=False).tolist()
    clean = [str(t).strip() for t in tickers if str(t).strip()]
    logger.info("S&P 400: %d tickers fetched", len(clean))
    return clean


def _fetch_stoxx600_wikipedia() -> list[str]:
    """
    Fetch STOXX Europe 600 from Wikipedia (table 2: 'Ticker' + 'Country' columns).

    Normalises raw exchange tickers to yfinance format by appending the country-
    derived exchange suffix and replacing spaces with hyphens in multi-class tickers.
    Returns an empty list on failure.
    """
    logger.info("STOXX 600: trying Wikipedia ...")
    try:
        html = _get(
            "https://en.wikipedia.org/wiki/STOXX_Europe_600",
            user_agent=WIKIPEDIA_UA,
        )
        tables = pd.read_html(StringIO(html))

        # Find the table that has both 'Ticker' and 'Country' columns.
        component_table: pd.DataFrame | None = None
        for tbl in tables:
            if "Ticker" in tbl.columns and "Country" in tbl.columns:
                component_table = tbl
                break

        if component_table is None:
            logger.warning("Wikipedia STOXX 600: no table with Ticker+Country columns found")
            return []

        tickers: list[str] = []
        skipped = 0
        for _, row in component_table.iterrows():
            result = _apply_country_suffix(str(row["Ticker"]), str(row["Country"]))
            if result:
                tickers.append(result)
            else:
                skipped += 1

        if skipped:
            logger.warning(
                "Wikipedia STOXX 600: %d tickers skipped (unmapped country or blank)",
                skipped,
            )
        logger.info("Wikipedia STOXX 600: %d tickers fetched", len(tickers))
        return tickers

    except Exception as exc:  # noqa: BLE001
        logger.warning("Wikipedia STOXX 600 failed: %s", exc)
        return []


def _fetch_stoxx600_ishares() -> list[str]:
    """
    Attempt to fetch STOXX Europe 600 from iShares holdings CSV.

    Tries the two known URL patterns in order.  Returns an empty list when
    both fail or return too few rows (likely a login-wall redirect).
    """
    for option_idx, url in enumerate(ISHARES_URLS):
        label = chr(ord("B") + option_idx)  # "B", "C"
        logger.info("STOXX 600: trying Option %s (iShares CSV) ...", label)
        try:
            csv_text = _get(url)
            tickers = _parse_ishares_csv(csv_text)
            if len(tickers) < 50:
                logger.warning(
                    "Option %s returned only %d tickers — likely not a real holdings CSV",
                    label,
                    len(tickers),
                )
                continue
            logger.info("STOXX 600 fetched via iShares Option %s: %d tickers", label, len(tickers))
            return tickers
        except Exception as exc:  # noqa: BLE001
            logger.warning("Option %s failed: %s", label, exc)

    return []


def fetch_stoxx600() -> list[str]:
    """
    Fetch STOXX Europe 600 tickers in yfinance format.

    Priority:
      1. Wikipedia component table (primary — reliable, ~530 tickers)
      2. iShares holdings CSV, Option B then C (fallback)
      3. Hardcoded list of ~55 major components (last resort)

    Logs which source was actually used.
    """
    tickers = _fetch_stoxx600_wikipedia()
    if tickers:
        return tickers

    tickers = _fetch_stoxx600_ishares()
    if tickers:
        return tickers

    logger.warning(
        "All STOXX 600 sources failed. Using hardcoded fallback (%d tickers). "
        "Universe will cover only major European components.",
        len(STOXX_FALLBACK),
    )
    return list(STOXX_FALLBACK)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    sp500 = fetch_sp500()
    sp400 = fetch_sp400()
    stoxx = fetch_stoxx600()

    combined = sorted(set(sp500 + sp400 + stoxx))

    logger.info("--- Summary ---")
    logger.info("S&P 500:      %d tickers", len(sp500))
    logger.info("S&P 400:      %d tickers", len(sp400))
    logger.info("STOXX 600:    %d tickers", len(stoxx))
    logger.info("Total unique: %d tickers", len(combined))

    out_path = Path(__file__).parent.parent / "data" / "universe.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    logger.info("Written to %s", out_path)


if __name__ == "__main__":
    main()
