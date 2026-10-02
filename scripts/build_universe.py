#!/usr/bin/env python3
"""
Build data/universe.json from S&P 500 + S&P 400 + STOXX Europe 600.

Run: uv run python scripts/build_universe.py [--allow-partial-stoxx]

Sources:
  S&P 500   Wikipedia — https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
  S&P 400   Wikipedia — https://en.wikipedia.org/wiki/List_of_S%26P_400_companies
  STOXX 600 iShares STOXX Europe 600 UCITS ETF (DE) (EXSA) holdings CSV (primary;
            ISHARES_URLS tried in order, tiers "ishares-b", "ishares-c", ...)
            Wikipedia — https://en.wikipedia.org/wiki/STOXX_Europe_600 (fallback;
            the table had only 467 of 600 rows as of 2026-10)
            Hardcoded fallback of ~55 major components (last resort)

Completeness guard: if the winning STOXX tier yields fewer than
STOXX_MIN_COMPLETE tickers, main() raises RuntimeError before writing anything,
unless --allow-partial-stoxx is passed (then it logs a WARNING and continues).

Ticker normalisation to yfinance format:
  US tickers:    no suffix (AAPL, MSFT, BRK-B)
  EU tickers:    exchange suffix from the iShares "Exchange" column
                 (Wikipedia fallback: derived from the country column)
                 (.AS, .DE, .PA, .L, .SW, .CO, .MC, .MI, .ST, .OL, .HE, ...)
  Multi-class:   space replaced with hyphen (NOVO B → NOVO-B, then .CO suffix)

Wikipedia requires a properly identifying bot User-Agent per its policy (https://w.wiki/4wJS).
iShares and other financial sites use a browser-like User-Agent.
"""

import argparse
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

# STOXX Europe 600 has 600 members; the EXSA ETF holds ~602 equity lines (index
# changes are held briefly in parallel). Below this the STOXX source is treated
# as incomplete and main() fails loud (see --allow-partial-stoxx).
STOXX_MIN_COMPLETE = 590

# Minimum rows for an iShares response to count as a real holdings CSV at all
# (a login wall / error page parses to a handful of rows).
ISHARES_MIN_ROWS = 50

# iShares "Asset Class" value of real holdings; Cash, FX, Futures etc. are dropped.
ISHARES_EQUITY_ASSET_CLASS = "Equity"

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

# iShares STOXX Europe 600 holdings CSV URLs, tried in order. Tier label of the
# n-th URL is "ishares-<chr(ord('b') + n)>" ("ishares-b" for the first).
# The former SXXP URLs (uk/251783, us/251781) were dead (HTTP 500/404) by 2026-10.
ISHARES_URLS: list[str] = [
    # iShares STOXX Europe 600 UCITS ETF (DE), EXSA — verified 2026-10-02.
    (
        "https://www.ishares.com/ch/individual/en/products/251931/"
        "ishares-stoxx-europe-600-ucits-etf-de-fund/1495092304805.ajax"
        "?fileType=csv&fileName=EXSA_holdings&dataType=fund"
    ),
]

# Exchange label → yfinance suffix used when parsing the iShares "Exchange" column.
# The block at the top holds the exact labels of the EXSA holdings CSV (01 Oct 2026).
# "Nasdaq Omx Nordic" is iShares' label for Nasdaq Stockholm: all 51 rows carrying
# it have Location "Sweden" (Helsinki and Copenhagen have their own labels), so it
# maps straight to .ST.
# "Eurex Deutschland" is deliberately absent: it only carries the index-futures
# line (Asset Class "Futures"), which the Equity filter drops before the lookup.
ISHARES_EXCHANGE_SUFFIX: dict[str, str] = {
    "Nyse Euronext - Euronext Paris": ".PA",
    "Nasdaq Omx Nordic": ".ST",
    "Omx Nordic Exchange Copenhagen A/S": ".CO",
    "Oslo Bors Asa": ".OL",
    "Warsaw Stock Exchange/Equities/Main Market": ".WA",
    "Nasdaq Omx Helsinki Ltd.": ".HE",
    "Nyse Euronext - Euronext Brussels": ".BR",
    "Athens Exchange S.A. Cash Market": ".AT",
    "Wiener Boerse Ag": ".VI",
    "Irish Stock Exchange - All Market": ".IR",
    "Nyse Euronext - Euronext Lisbon": ".LS",
    "Bolsa De Madrid": ".MC",
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


# Verified, provenance-native symbol corrections from GATE 1 (Wikipedia-Company anchor;
# docs/superpowers/audits/2026-06-06-0a-symbol-contaminants/correction_table.md).
# RIC/contaminated symbol -> correct Yahoo symbol. 20 remaps, all live-verified
# (EQUITY + Wikipedia-Company longName agreement + exchange).
SYMBOL_CORRECTIONS: dict[str, str] = {
    "AIRP.PA": "AI.PA",    # Air Liquide
    "ATOS.PA": "ATO.PA",   # Atos
    "BNPP.PA": "BNP.PA",   # BNP Paribas
    "BOUY.PA": "EN.PA",    # Bouygues
    "CAGR.PA": "ACA.PA",   # Credit Agricole
    "CAPP.PA": "CAP.PA",   # Capgemini
    "CARR.PA": "CA.PA",    # Carrefour (NOT Carrier US)
    "CTS.DE": "EVD.DE",    # CTS Eventim
    "DANO.PA": "BN.PA",    # Danone (NOT Danaher)
    "ENX.AS": "ENX.PA",    # Euronext (wrong venue .AS -> .PA)
    "MICP.PA": "ML.PA",    # Michelin
    "OREP.PA": "OR.PA",    # L'Oreal
    "PERP.PA": "RI.PA",    # Pernod Ricard
    "RENA.PA": "RNO.PA",   # Renault
    "SASY.PA": "SAN.PA",   # Sanofi
    "SCHN.PA": "SU.PA",    # Schneider Electric
    "SGEF.PA": "DG.PA",    # Vinci (ex-"Societe Generale d'Entreprises")
    "SGOB.PA": "SGO.PA",   # Saint-Gobain
    "SOGN.PA": "GLE.PA",   # Societe Generale
    "FTI.L": "FTI",        # TechnipFMC (twin-collapse onto existing NYSE listing)
}

# Dead listings / unresolvable ambiguities — dropped, not remapped (drop-not-guess).
SYMBOL_DROP: set[str] = {
    "LII.L",   # Liberty Global (LII US = Lennox, different company; listing ambiguous)
    "SKY.L",   # Sky Group (delisted 2018)
}


def _apply_symbol_corrections(
    tickers: list[str],
    corrections: dict[str, str] | None = None,
    drop: set[str] | None = None,
) -> list[str]:
    """Remap contaminated symbols to their verified Yahoo equivalent and drop dead
    listings. Pure: no dedup here (caller's sorted(set(...)) collapses remapped
    twins). Instrumentation-visible: logs each remap/drop."""
    corrections = SYMBOL_CORRECTIONS if corrections is None else corrections
    drop = SYMBOL_DROP if drop is None else drop
    out: list[str] = []
    for t in tickers:
        if t in drop:
            logger.info("symbol_correction: drop %s", t)
            continue
        if t in corrections:
            logger.info("symbol_correction: remap %s -> %s", t, corrections[t])
            out.append(corrections[t])
        else:
            out.append(t)
    return out


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

def _find_ishares_header(lines: list[str]) -> int:
    """Index of the column-header row (first field exactly "Ticker").

    Skips the "Fund Holdings as of" preamble, the non-breaking-space line and a
    leading UTF-8 BOM (httpx' response.text keeps it)."""
    for i, line in enumerate(lines):
        first_field = line.lstrip("﻿").strip().split(",", 1)[0].strip('"')
        if first_field == "Ticker":
            return i
    raise ValueError("Could not locate 'Ticker' header row in iShares CSV")


def _normalise_ishares_ticker(raw: str) -> str:
    """iShares local ticker -> yfinance base symbol (without suffix).

    "ASSA B" -> "ASSA-B" (class share), "RR." -> "RR" (LSE trailing dot),
    "BT.A" -> "BT-A" (LSE class share with internal dot; Yahoo: BT-A.L),
    "ERICb" -> "ERIC-B" (via _normalise_class_suffix)."""
    ticker = raw.strip().replace(" ", "-").rstrip(".").replace(".", "-")
    return _normalise_class_suffix(ticker)


def _parse_ishares_csv(csv_text: str) -> list[str]:
    """
    Parse an iShares holdings CSV and return a list of yfinance-format tickers.

    Only rows with Asset Class "Equity" are kept (cash, FX, futures dropped).
    The suffix comes from the "Exchange" column via ISHARES_EXCHANGE_SUFFIX —
    explicitly not "Location", which precedes it and names the domicile.
    Equity rows on an unmapped exchange are skipped and reported as one WARNING
    with count and labels, never dropped silently.
    """
    lines = csv_text.splitlines()
    header_index = _find_ishares_header(lines)

    table_text = "\n".join(lines[header_index:])
    df = pd.read_csv(StringIO(table_text), dtype=str, on_bad_lines="skip")
    df.columns = [c.strip() for c in df.columns]

    missing = {"Ticker", "Exchange", "Asset Class"} - set(df.columns)
    if missing:
        raise ValueError(
            f"iShares CSV lacks columns {sorted(missing)}; got {list(df.columns)}"
        )

    tickers: list[str] = []
    non_equity = 0
    unknown: dict[str, int] = {}

    for _, row in df.iterrows():
        if str(row["Asset Class"]).strip() != ISHARES_EQUITY_ASSET_CLASS:
            non_equity += 1
            continue

        ticker = _normalise_ishares_ticker(str(row["Ticker"]))
        if not ticker or ticker in ("-", "nan"):
            continue

        exchange = str(row["Exchange"]).strip()
        suffix = ISHARES_EXCHANGE_SUFFIX.get(exchange)
        if suffix is None:
            unknown[exchange] = unknown.get(exchange, 0) + 1
            logger.debug("iShares: unknown exchange '%s' for '%s'", exchange, ticker)
            continue
        tickers.append(f"{ticker}{suffix}")

    if non_equity:
        logger.info("iShares CSV: %d non-equity rows dropped", non_equity)
    if unknown:
        logger.warning(
            "STOXX CSV: %d equity tickers skipped — exchange not in mapping: %s",
            sum(unknown.values()),
            unknown,
        )
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


def _fetch_stoxx600_ishares() -> tuple[list[str], str] | None:
    """
    Attempt to fetch STOXX Europe 600 from iShares holdings CSV.

    Tries ISHARES_URLS in order.  On success returns ``(tickers, tier)`` where
    tier is ``"ishares-b"`` for the first URL, ``"ishares-c"`` for the second,
    and so on.  Returns ``None`` when all fail or return too few rows (likely
    a login-wall redirect).
    """
    for option_idx, url in enumerate(ISHARES_URLS):
        label = chr(ord("B") + option_idx)  # "B", "C", ...
        logger.info("STOXX 600: trying Option %s (iShares CSV) ...", label)
        try:
            csv_text = _get(url)
            tickers = _parse_ishares_csv(csv_text)
            if len(tickers) < ISHARES_MIN_ROWS:
                logger.warning(
                    "Option %s returned only %d tickers — likely not a real holdings CSV",
                    label,
                    len(tickers),
                )
                continue
            logger.info("STOXX 600 fetched via iShares Option %s: %d tickers", label, len(tickers))
            return tickers, f"ishares-{label.lower()}"
        except Exception as exc:  # noqa: BLE001
            logger.warning("Option %s failed: %s", label, exc)

    return None


def fetch_stoxx600() -> tuple[list[str], str]:
    """
    Fetch STOXX Europe 600 tickers in yfinance format.

    Priority:
      1. iShares EXSA holdings CSV (primary — ~602 equity lines)
      2. Wikipedia component table (fallback — only 467 rows as of 2026-10)
      3. Hardcoded list of ~55 major components (last resort)

    Returns ``(tickers, tier)`` where tier reports which source actually
    fired: ``"ishares-b"`` (``"ishares-c"``, ... for further URLs),
    ``"wikipedia"`` or ``"hardcoded-fallback"``. Completeness is enforced
    by main(), not here.
    """
    ishares = _fetch_stoxx600_ishares()
    if ishares:
        return ishares

    logger.warning("STOXX 600: iShares unavailable — falling back to Wikipedia")
    tickers = _fetch_stoxx600_wikipedia()
    if tickers:
        return tickers, "wikipedia"

    logger.warning(
        "All STOXX 600 sources failed. Using hardcoded fallback (%d tickers). "
        "Universe will cover only major European components.",
        len(STOXX_FALLBACK),
    )
    return list(STOXX_FALLBACK), "hardcoded-fallback"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build data/universe.json.")
    parser.add_argument(
        "--allow-partial-stoxx",
        action="store_true",
        help=(
            "continue with a WARNING when the STOXX 600 source yields fewer than "
            f"{STOXX_MIN_COMPLETE} tickers, instead of aborting"
        ),
    )
    return parser.parse_args(argv)


def _check_stoxx_completeness(count: int, tier: str, allow_partial: bool) -> None:
    """Fail loud on an incomplete STOXX 600 source unless explicitly allowed."""
    if count >= STOXX_MIN_COMPLETE:
        return
    message = (
        f"STOXX 600 incomplete: tier '{tier}' yielded {count} tickers "
        f"(< {STOXX_MIN_COMPLETE})"
    )
    if not allow_partial:
        raise RuntimeError(f"{message}; rerun with --allow-partial-stoxx to accept")
    logger.warning("%s — continuing because --allow-partial-stoxx was given", message)


def main(argv: list[str] | None = None, data_dir: Path | None = None) -> None:
    """Build universe.json + universe_provenance.json.

    ``argv`` defaults to sys.argv[1:]; ``data_dir`` defaults to the repo's data/
    directory (tests pass a tmp dir so the real files are never touched).
    """
    args = _parse_args(argv)
    sp500 = fetch_sp500()
    sp400 = fetch_sp400()
    stoxx, stoxx_tier = fetch_stoxx600()
    _check_stoxx_completeness(len(stoxx), stoxx_tier, args.allow_partial_stoxx)

    combined = sorted(set(_apply_symbol_corrections(sp500 + sp400 + stoxx)))
    # Guard: no contaminated key may survive into the universe (fail loud).
    surviving = set(SYMBOL_CORRECTIONS) & set(combined)
    if surviving:
        raise RuntimeError(
            f"symbol_correction guard: contaminated keys survived: {sorted(surviving)}"
        )
    logger.info("symbol_correction: %d corrections, %d drops applied",
                len(SYMBOL_CORRECTIONS), len(SYMBOL_DROP))

    logger.info("--- Summary ---")
    logger.info("S&P 500:      %d tickers", len(sp500))
    logger.info("S&P 400:      %d tickers", len(sp400))
    logger.info("STOXX 600:    %d tickers (tier: %s)", len(stoxx), stoxx_tier)
    logger.info("Total unique: %d tickers", len(combined))

    if data_dir is None:
        data_dir = Path(__file__).parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    out_path = data_dir / "universe.json"
    out_path.write_text(json.dumps(combined, indent=2), encoding="utf-8")
    logger.info("Written to %s", out_path)

    provenance = {
        "stoxx_tier": stoxx_tier,
        "sp500_count": len(sp500),
        "sp400_count": len(sp400),
        "stoxx600_count": len(stoxx),
        "total_unique": len(combined),
    }
    prov_path = data_dir / "universe_provenance.json"
    prov_path.write_text(json.dumps(provenance, indent=2), encoding="utf-8")
    logger.info("Provenance written to %s", prov_path)


if __name__ == "__main__":
    main()
