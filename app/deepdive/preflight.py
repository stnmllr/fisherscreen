"""Pre-flight check for a Tool B deep dive — no Gemini, no writes.

Answers two questions before any money is spent: do the ticker and the three
peers exist (yfinance), and what kind of dossier would the run produce
(full / quant_only / none / unknown)? If peer slots are empty, it can offer
peer suggestions through an injected `suggest` callable (read-only).
Pure function with injected dependencies, same pattern as `run_deep_dive`.
Spec: docs/superpowers/specs/2026-10-24-deepdive-ui-design.md, section 1, the
appendix "Prüfung gegen den Code" (items 1 and 3) and the "Nachtrag
2026-10-24: Peer-Vorschlag bei weniger als drei Peers".
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from app.deepdive.adr_resolver import _EU_MARKER
from app.deepdive.peer_suggest import PeerSuggestion
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
SUGGEST_NO_INDUSTRY = "keine Branche bekannt — kein Vorschlag"
SUGGEST_UNAVAILABLE = "Vorschläge nicht abrufbar (Quelle nicht erreichbar)"
SUGGEST_EMPTY = "keine passenden Titel im Universum gefunden"


@dataclass(frozen=True)
class SymbolCheck:
    symbol: str
    ok: bool
    name: str | None  # shortName/longName from yfinance
    currency: str | None
    market_cap: float | None
    message: str  # one line for the human, German
    industry: str | None = None  # yfinance "industry"
    sector: str | None = None  # yfinance "sector"


@dataclass(frozen=True)
class PreflightResult:
    ticker: SymbolCheck
    peers: list[SymbolCheck]
    dossier_kind: DossierKind
    dossier_note: str
    no_sec_source_reason: str | None
    can_start: bool
    needs_quant_only_ack: bool
    missing_peer_slots: list[int] = field(default_factory=list)  # 1-based
    peer_suggestions: list[PeerSuggestion] = field(default_factory=list)
    suggestion_note: str | None = None


def normalize_symbol(raw: str) -> str:
    return raw.strip().upper()


def is_valid_symbol(symbol: str) -> bool:
    return SYMBOL_PATTERN.fullmatch(normalize_symbol(symbol)) is not None


def parse_peer_arg(raw: str) -> list[str]:
    """Parse the CLI `--peers` value for the pre-flight check: 1-3 symbols,
    comma-separated. Fewer than three is allowed here (the check then offers
    suggestions); the deepdive command itself still requires exactly three."""
    tokens = [normalize_symbol(t) for t in raw.split(",")]
    tokens = [t for t in tokens if t]
    if not 1 <= len(tokens) <= PEER_COUNT:
        raise DeepDiveError(
            f"Vorprüfung braucht 1 bis {PEER_COUNT} Peers (kommagetrennt), "
            f"erhalten: {len(tokens)}"
        )
    return tokens


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


def _text(raw: Any) -> str | None:
    return raw if isinstance(raw, str) and raw else None


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
    return SymbolCheck(
        symbol=symbol,
        ok=True,
        name=name,
        currency=_text(info.get("currency")),
        market_cap=_market_cap(info.get("marketCap")),
        message=f"gefunden: {name}" if name else "gefunden",
        industry=_text(info.get("industry")),
        sector=_text(info.get("sector")),
    )


def _check_symbol(symbol: str, yfinance: Any) -> SymbolCheck:
    if not SYMBOL_PATTERN.fullmatch(symbol):
        return _rejected(
            symbol,
            "ungültiges Symbol (erlaubt: A–Z, 0–9, '.', '-', '=', max. 20 Zeichen)",
        )
    return _check_yfinance(symbol, yfinance)


def _check_peers(
    raw_peers: list[str], ticker: str, yfinance: Any
) -> tuple[list[SymbolCheck], list[int]]:
    """Return (checks of the given peers, 1-based empty/missing slots).

    Slots are positional: an empty entry among the first three is a missing
    slot, not a failing row; entries beyond the third are flagged."""
    checks: list[SymbolCheck] = []
    missing: list[int] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_peers):
        symbol = normalize_symbol(raw)
        if index >= PEER_COUNT:
            if symbol:
                checks.append(
                    _rejected(symbol, f"zu viele Peers — genau {PEER_COUNT} nötig")
                )
            continue
        if not symbol:
            missing.append(index + 1)
        elif symbol in seen:
            checks.append(_rejected(symbol, "doppelt — jeder Peer nur einmal"))
        elif symbol == ticker:
            checks.append(_rejected(symbol, "gleich dem Ticker — kein Peer"))
        else:
            checks.append(_check_symbol(symbol, yfinance))
        seen.add(symbol)
    missing.extend(range(len(raw_peers) + 1, PEER_COUNT + 1))
    return checks, missing


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


def _suggestions(
    ticker_check: SymbolCheck,
    peer_checks: list[SymbolCheck],
    suggest: Callable[[SymbolCheck, list[str]], list[PeerSuggestion]],
) -> tuple[list[PeerSuggestion], str | None]:
    """Failure != empty: an unreachable source says so, an empty result says
    that nothing matched."""
    if not ticker_check.ok:
        return [], None
    if not ticker_check.industry:
        return [], SUGGEST_NO_INDUSTRY
    exclude = [ticker_check.symbol] + [c.symbol for c in peer_checks]
    try:
        found = suggest(ticker_check, exclude)
    except DataSourceError as exc:
        logger.warning(
            "preflight: peer suggestions unavailable for %s: %s",
            ticker_check.symbol,
            exc,
        )
        return [], SUGGEST_UNAVAILABLE
    if not found:
        return [], SUGGEST_EMPTY
    return list(found), None


def run_preflight(
    ticker: str,
    peers: list[str],
    *,
    resolver: Any,
    yfinance: Any,
    edgar_map_available: Callable[[], bool],
    suggest: Callable[[SymbolCheck, list[str]], list[PeerSuggestion]] | None = None,
) -> PreflightResult:
    """Check ticker and peers and predict the dossier kind.

    All symbols are normalized (strip + upper) and checked against
    SYMBOL_PATTERN first; an invalid symbol never reaches the network.

    Peers: 0-3 positional slots. Every given peer is checked and reported
    individually — no abort on the first error. Duplicate (case-insensitive),
    ticker-equal and invalid peers are failing rows, flagged without a network
    call. Empty or absent slots are NOT rows: they are listed (1-based) in
    `missing_peer_slots`, so `peers` holds only the given peers' checks, in
    slot order. Entries beyond the third are flagged "zu viele Peers" without
    being checked. Starting still needs exactly three ok peers and no missing
    slot.

    Suggestions: only when slots are missing and `suggest` is given — see
    `_suggestions` for the notes on no industry / source down / no match.

    Ticker: step 1 yfinance — without a hit there is no quant, so no dossier
    ("none") and the resolver is not called. Step 2 the resolver decides
    full / quant_only / none / unknown (see `_classify`).

    Never calls Gemini, never writes anything (Firestore is read only by the
    injected `suggest`).
    """
    symbol = normalize_symbol(ticker)
    ticker_check = _check_symbol(symbol, yfinance)
    peer_checks, missing = _check_peers(peers, symbol, yfinance)

    no_sec_source_reason: str | None = None
    if not ticker_check.ok:
        kind: DossierKind = "none"
        note = f"Ticker nicht verwendbar: {ticker_check.message}"
    else:
        kind, note, no_sec_source_reason = _classify(
            symbol, resolver, edgar_map_available
        )

    suggestions: list[PeerSuggestion] = []
    suggestion_note: str | None = None
    if missing and suggest is not None:
        suggestions, suggestion_note = _suggestions(ticker_check, peer_checks, suggest)

    can_start = (
        ticker_check.ok
        and not missing
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
        missing_peer_slots=missing,
        peer_suggestions=suggestions,
        suggestion_note=suggestion_note,
    )
    logger.info("preflight %s: dossier_kind=%s can_start=%s", symbol, kind, can_start)
    return result


_VERDICT_PREFIX: dict[str, str] = {
    "full": "Vollständiges Dossier",
    "quant_only": "Nur Quant-Dossier (kein SEC-Jahresformular)",
    "none": "Kein Dossier möglich",
    "unknown": "Unklar",
}


def _fmt_cap(cap: float | None) -> str:
    return f"{cap:,.0f}" if cap is not None else "-"


def _format_row(label: str, check: SymbolCheck) -> str:
    status = "OK    " if check.ok else "FEHLER"
    details = [check.name or "-", check.currency or "-", _fmt_cap(check.market_cap)]
    symbol = check.symbol or "(leer)"
    return f"  {label:<7} {symbol:<12} {status} {' | '.join(details)} — {check.message}"


def _format_suggestion(s: PeerSuggestion) -> str:
    stand = (s.cached_at or "")[:10] or "unbekannt"
    match = "Branche" if s.match == "industry" else "Sektor"
    cap = f"{_fmt_cap(s.market_cap)} {s.currency or ''}".rstrip()
    return (
        f"  {s.symbol:<12} {s.name or '-'} | {cap} | "
        f"{match}: {s.industry or '-'} | Stand {stand}"
    )


def format_preflight(result: PreflightResult) -> str:
    """Render a PreflightResult as German plain text for the CLI.

    ASCII status words instead of check marks: redirected stdout on Windows is
    cp1252, and the failure path must not die on a UnicodeEncodeError."""
    lines = [f"Vorprüfung {result.ticker.symbol or '(leer)'}"]
    lines.append(_format_row("Ticker", result.ticker))
    given = iter(result.peers)
    for slot in range(1, len(result.peers) + len(result.missing_peer_slots) + 1):
        if slot in result.missing_peer_slots:
            lines.append(f"  Peer {slot}  fehlt — Vorschlag unten")
        else:
            lines.append(_format_row(f"Peer {slot}", next(given)))
    lines.append(f"{_VERDICT_PREFIX[result.dossier_kind]}: {result.dossier_note}")
    if result.needs_quant_only_ack:
        lines.append(
            "Hinweis: Start nur mit ausdrücklicher Bestätigung "
            "(es gibt kein SEC-Filing — nur Quant-Dossier)."
        )
    if result.peer_suggestions:
        lines.append("Peer-Vorschläge (gleiche Branche, nach Market Cap):")
        lines.extend(_format_suggestion(s) for s in result.peer_suggestions)
    if result.suggestion_note:
        lines.append(f"Peer-Vorschläge: {result.suggestion_note}")
    lines.append(f"Start möglich: {'ja' if result.can_start else 'nein'}")
    return "\n".join(lines)
