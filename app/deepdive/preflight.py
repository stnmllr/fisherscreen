"""Pre-flight check for a Tool B deep dive — no Gemini, no Firestore, no writes.

Answers two questions before any money is spent: do the ticker and the three
peers exist (yfinance), and what kind of dossier would the run produce
(full / quant_only / none / unknown)? Pure function with injected
dependencies, same pattern as `run_deep_dive`. Spec:
docs/superpowers/specs/2026-10-24-deepdive-ui-design.md, section 1 plus the
appendix "Prüfung gegen den Code" (items 1 and 3).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, Literal

from app.deepdive.adr_resolver import _EU_MARKER
from app.errors import DataSourceError, DeepDiveError

logger = logging.getLogger(__name__)

# Symbols end up as separate argv entries of the CLI; a value such as "--site"
# would be read by argparse as a flag. The leading character therefore must not
# be "-", ".", or "=".
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9.\-=]{0,19}$")

PEER_COUNT = 3

DossierKind = Literal["full", "quant_only", "none", "unknown"]

_SPELLING_HINT = (
    "Schreibweise prüfen (US-Klassen ohne Punkt: BRK-B) oder Eintrag in "
    "data/adr_table.json"
)
_SEC_MAP_UNAVAILABLE = "Quelle nicht erreichbar (SEC-Tickerliste), später erneut prüfen"
_SOURCE_UNAVAILABLE = "Quelle nicht erreichbar, später erneut prüfen"


@dataclass(frozen=True)
class SymbolCheck:
    symbol: str
    ok: bool
    name: str | None  # shortName/longName from yfinance
    currency: str | None
    market_cap: float | None
    message: str  # one line for the human, German


@dataclass(frozen=True)
class PreflightResult:
    ticker: SymbolCheck
    peers: list[SymbolCheck]
    dossier_kind: DossierKind
    dossier_note: str
    no_sec_source_reason: str | None
    can_start: bool
    needs_quant_only_ack: bool


def normalize_symbol(raw: str) -> str:
    return raw.strip().upper()


def is_valid_symbol(symbol: str) -> bool:
    return SYMBOL_PATTERN.fullmatch(normalize_symbol(symbol)) is not None


def _rejected(symbol: str, message: str) -> SymbolCheck:
    return SymbolCheck(
        symbol=symbol,
        ok=False,
        name=None,
        currency=None,
        market_cap=None,
        message=message,
    )


def _market_cap(raw: Any) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _check_yfinance(symbol: str, yfinance: Any) -> SymbolCheck:
    """Same check as peer_preflight._validate_resolvable, but reported instead
    of raised: a failure becomes ok=False with the reason, never a crash."""
    try:
        info = yfinance.get_ticker_info(symbol)
    except DataSourceError as exc:  # includes DegradedDataError
        logger.warning("preflight: yfinance cannot resolve %s: %s", symbol, exc)
        return _rejected(symbol, f"bei yfinance nicht auflösbar: {exc}")
    if not info:
        return _rejected(symbol, "bei yfinance nicht auflösbar: leere Antwort")
    name = info.get("shortName") or info.get("longName")
    currency = info.get("currency")
    return SymbolCheck(
        symbol=symbol,
        ok=True,
        name=name,
        currency=currency if isinstance(currency, str) else None,
        market_cap=_market_cap(info.get("marketCap")),
        message=f"gefunden: {name}" if name else "gefunden",
    )


def _check_symbol(symbol: str, yfinance: Any) -> SymbolCheck:
    if not SYMBOL_PATTERN.fullmatch(symbol):
        return _rejected(
            symbol,
            "ungültiges Symbol (erlaubt: A–Z, 0–9, '.', '-', '=', max. 20 Zeichen)",
        )
    return _check_yfinance(symbol, yfinance)


def _check_peers(raw_peers: list[str], ticker: str, yfinance: Any) -> list[SymbolCheck]:
    checks: list[SymbolCheck] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_peers):
        symbol = normalize_symbol(raw)
        if index >= PEER_COUNT:
            checks.append(
                _rejected(symbol, f"zu viele Peers — genau {PEER_COUNT} nötig")
            )
        elif not symbol:
            checks.append(_rejected(symbol, "Peer leer"))
        elif symbol in seen:
            checks.append(_rejected(symbol, "doppelt — jeder Peer nur einmal"))
        elif symbol == ticker:
            checks.append(_rejected(symbol, "gleich dem Ticker — kein Peer"))
        else:
            checks.append(_check_symbol(symbol, yfinance))
        seen.add(symbol)
    for _ in range(len(raw_peers), PEER_COUNT):
        checks.append(_rejected("", f"Peer fehlt — genau {PEER_COUNT} nötig"))
    return checks


def _classify(
    ticker: str, resolver: Any, edgar_map_available: Callable[[], bool]
) -> tuple[DossierKind, str, str | None]:
    """Ask the resolver what dossier the run would produce.

    Failure != empty: a DataSourceError (OpenFIGI/EDGAR down) is "unknown",
    never "none". And because EdgarClientImpl.get_cik() reports a failed SEC
    ticker-map load as "not found", a DeepDiveError for an undotted ticker is
    only believed after the (shared) map confirms it actually loaded."""
    try:
        resolved = resolver.resolve(ticker)
    except DeepDiveError as exc:
        if _EU_MARKER not in ticker and not edgar_map_available():
            logger.warning(
                "preflight: SEC ticker map unavailable — %s is unknown, not absent",
                ticker,
            )
            return "unknown", _SEC_MAP_UNAVAILABLE, None
        return "none", f"{exc} — {_SPELLING_HINT}", None
    except DataSourceError as exc:
        logger.warning("preflight: resolver source unavailable for %s: %s", ticker, exc)
        return "unknown", f"{_SOURCE_UNAVAILABLE} ({exc})", None
    if resolved.has_filing_source:
        # The ADR table also maps plain US listings onto themselves
        # (MSFT -> MSFT); "via ADR" only applies to a different symbol.
        adr = resolved.adr_ticker
        via = f" via ADR {adr}" if adr and adr.upper() != ticker.upper() else ""
        return "full", f"{resolved.form_type}{via} (CIK {resolved.cik})", None
    return (
        "quant_only",
        resolved.no_sec_source_note or "",
        resolved.no_sec_source_reason,
    )


def run_preflight(
    ticker: str,
    peers: list[str],
    *,
    resolver: Any,
    yfinance: Any,
    edgar_map_available: Callable[[], bool],
) -> PreflightResult:
    """Check ticker and peers and predict the dossier kind.

    All symbols are normalized (strip + upper) and checked against
    SYMBOL_PATTERN first; an invalid symbol never reaches the network.

    Peers: every given peer is checked and reported individually — no abort on
    the first error. Empty, duplicate (case-insensitive) and ticker-equal peers
    are flagged without a network call. Exactly three are required; a wrong
    count is represented in `peers` itself so the caller always sees the
    problem per row: missing slots are padded with `symbol=""` rows flagged
    "Peer fehlt", and peers beyond the third are flagged "zu viele Peers"
    without being checked (so `peers` has more than three rows in that case).
    Either way `can_start` is False.

    Ticker: step 1 yfinance — without a hit there is no quant, so no dossier
    ("none") and the resolver is not called. Step 2 the resolver decides
    full / quant_only / none / unknown (see `_classify`).

    Never calls Gemini, never touches Firestore, never stores peers.
    """
    symbol = normalize_symbol(ticker)
    ticker_check = _check_symbol(symbol, yfinance)
    peer_checks = _check_peers(peers, symbol, yfinance)

    no_sec_source_reason: str | None = None
    if not ticker_check.ok:
        kind: DossierKind = "none"
        note = f"Ticker nicht verwendbar: {ticker_check.message}"
    else:
        kind, note, no_sec_source_reason = _classify(
            symbol, resolver, edgar_map_available
        )

    can_start = (
        ticker_check.ok
        and len(peer_checks) == PEER_COUNT
        and all(p.ok for p in peer_checks)
        and kind in ("full", "quant_only")
    )
    result = PreflightResult(
        ticker=ticker_check,
        peers=peer_checks,
        dossier_kind=kind,
        dossier_note=note,
        no_sec_source_reason=no_sec_source_reason,
        can_start=can_start,
        needs_quant_only_ack=kind == "quant_only",
    )
    logger.info("preflight %s: dossier_kind=%s can_start=%s", symbol, kind, can_start)
    return result


_VERDICT_PREFIX: dict[str, str] = {
    "full": "Vollständiges Dossier",
    "quant_only": "Nur Quant-Dossier (kein SEC-Jahresformular)",
    "none": "Kein Dossier möglich",
    "unknown": "Unklar",
}


def _format_row(label: str, check: SymbolCheck) -> str:
    status = "OK    " if check.ok else "FEHLER"
    details = [
        check.name or "-",
        check.currency or "-",
        f"{check.market_cap:,.0f}" if check.market_cap is not None else "-",
    ]
    symbol = check.symbol or "(leer)"
    return f"  {label:<7} {symbol:<12} {status} {' | '.join(details)} — {check.message}"


def format_preflight(result: PreflightResult) -> str:
    """Render a PreflightResult as German plain text for the CLI.

    ASCII status words instead of check marks: redirected stdout on Windows is
    cp1252, and the failure path must not die on a UnicodeEncodeError."""
    lines = [f"Vorprüfung {result.ticker.symbol or '(leer)'}"]
    lines.append(_format_row("Ticker", result.ticker))
    for index, peer in enumerate(result.peers, start=1):
        lines.append(_format_row(f"Peer {index}", peer))
    lines.append(f"{_VERDICT_PREFIX[result.dossier_kind]}: {result.dossier_note}")
    if result.needs_quant_only_ack:
        lines.append(
            "Hinweis: Start nur mit ausdrücklicher Bestätigung "
            "(es gibt kein SEC-Filing — nur Quant-Dossier)."
        )
    lines.append(f"Start möglich: {'ja' if result.can_start else 'nein'}")
    return "\n".join(lines)
