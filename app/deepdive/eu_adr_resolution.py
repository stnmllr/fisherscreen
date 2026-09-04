from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, cast

from app.deepdive.adr_resolver import (
    NO_SEC_SOURCE_REASONS,
    NoSecSourceReason,
    ResolvedTicker,
    no_sec_source,
)
from app.errors import DeepDiveError

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient
    from app.services.openfigi_client import OpenFIGIClient
    from app.services.yfinance_client import YFinanceClient

logger = logging.getLogger(__name__)

# Home-exchange codes per Yahoo suffix (lifted from the dual-line audit).
SUFFIX_HOME_EXCH: dict[str, list[str]] = {
    "SW": ["SW", "VX"],
    "DE": ["GY", "GR"],
    "PA": ["FP"],
    "MC": ["SM"],
    "L": ["LN"],
    "AS": ["NA"],
    "CO": ["DC"],
    "VI": ["AV"],
    "WA": ["PW"],
    "BR": ["BB"],
    "ST": ["SS"],
    "HE": ["FH"],
    "OL": ["NO"],
    "MI": ["IM"],
    "IR": ["ID"],
    "AT": ["GA"],
    "LS": ["PL"],
}
# US exchange codes for the ADR line (audit "(US)" bucket).
US_EXCH = {"US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"}

_LEGAL_FORMS = (
    " AG",
    " SA",
    " S.A.",
    " N.V.",
    " NV",
    " PLC",
    " SE",
    " SPA",
    " S.P.A.",
    " ASA",
    " AB",
    " OYJ",
    " A/S",
    " HOLDING",
    " GROUP",
    " INC",
    " LTD",
    " LIMITED",
    " COMPANY",
    " HLDG",
    " HLDGS",
)


def norm_issuer(name: str) -> str:
    """Normalise an issuer name for equality matching: drop legal forms + spaces.
    'ROCHE HOLDING AG' -> 'ROCHEHOLDING'; 'ROCHE BOBOIS SA' -> 'ROCHEBOBOIS'
    (stays distinct -> Bobois noise excluded)."""
    n = (name or "").upper()
    for legal in _LEGAL_FORMS:
        n = n.replace(legal, " ")
    return "".join(n.split())


def issuer_name(figi_name: str) -> str:
    """Issuer identity from an OpenFIGI security name: strip a trailing
    '-CLASSTOKEN' whose token has no space ('ROCHE HOLDING AG-BR' -> 'ROCHE
    HOLDING AG'); the no-space guard keeps hyphenated real names ('COCA-COLA
    CO')."""
    n = (figi_name or "").upper().strip()
    if "-" in n:
        head, _, tail = n.rpartition("-")
        if head and tail and " " not in tail:
            return head.strip()
    return n


def home_exch_codes(ticker: str) -> list[str]:
    suffix = ticker.rsplit(".", 1)[1] if "." in ticker else ""
    return SUFFIX_HOME_EXCH.get(suffix.upper(), [])


def local_symbol_variants(ticker: str) -> list[str]:
    """Ordered candidate local symbols for OpenFIGI (the variant ladder against
    the documented NVO miss: 'NOVO B'/'NOVOB' instead of the dashed form)."""
    base = ticker.rsplit(".", 1)[0] if "." in ticker else ticker
    variants = [base, base.replace("-", " "), base.replace("-", "")]
    return list(dict.fromkeys(variants))  # order-preserving dedup


def find_home_identity(
    ticker: str, ref_norm: str, *, openfigi: "OpenFIGIClient"
) -> dict | None:
    """Variant ladder + NAME-SANITY-CHECK: accept the first candidate whose
    OpenFIGI issuer name matches the reference (ADR-EU-2). Never 'first answer
    wins' — guards the variant-ladder false hit (ROCHE -> ROCHE BOBOIS).

    None when no candidate matched. That is a legitimate outcome, not an error:
    an unmatched name means we do not know which issuer this is, and the caller
    turns it into a classified `unverifiable_identity` verdict. What stays
    forbidden is the third possibility — returning an unverified match."""
    for exch in home_exch_codes(ticker):
        for cand in local_symbol_variants(ticker):
            ident = openfigi.map_ticker(cand, exch)
            if ident and norm_issuer(issuer_name(ident.get("name", ""))) == ref_norm:
                return ident
    return None


def unverifiable_identity(ticker: str, *, cause: str) -> ResolvedTicker:
    """The verdict for "we do not know which company this ticker is".

    Why this may degrade instead of aborting: the quant half of a dossier hangs
    on the requested ticker itself, not on the OpenFIGI identity. Price,
    valuation and peers are correct whether or not a name match succeeded — only
    the SEC half is missing, and that is exactly what the label says.

    The wording is load-bearing. `not_sec_registrant` means we looked and found
    no registration; this means we never got far enough to look. "ungeprüft,
    nicht widerlegt" keeps the dossier from asserting an absence it did not
    establish.

    NOT CACHED, unlike the three issuer verdicts (see the call sites): this one
    describes the state of our matcher, not the state of the issuer. The matcher
    is being repaired, and a cached "could not verify" would outlive its own
    cause for the whole negative TTL. WARNING, not INFO, for the same reason —
    an issuer without a US line is expected, an unmatched identity is not."""
    logger.warning("eu-adr: %s -> unverifiable identity (%s)", ticker, cause)
    return no_sec_source(
        ticker,
        reason="unverifiable_identity",
        note=(
            f"Kein SEC-Hard-Scuttlebutt: Die Identität von {ticker} liess sich "
            f"nicht verifizieren ({cause}) — ob es eine SEC-Quelle gibt, ist "
            f"damit ungeprüft, nicht widerlegt. Dossier ist quant-only "
            f"(Quant + Bewertung + Peers)."
        ),
    )


def _same_issuer(line_name: str, ident_norm: str) -> bool:
    """Prefix-tolerant issuer match for US lines. ADR line names carry listing
    descriptors the home identity lacks ('ASML HOLDING NV-NY REG SHS',
    'SAP SE-SPONSORED ADR'), so strict norm-equality against the home identity
    ('ASML HOLDING NV') wrongly drops the ADR line. The home-issuer norm is a
    prefix of the ADR-line norm — accept when either is a prefix of the other.

    NO PRODUCTION CALLER LEFT since the `search_issuer` fallback was removed:
    the share-class path needs no name check at all, because every line there
    belongs to the home line's share class by construction. Kept only because
    tests and the `scripts/` diagnostics still exercise it — retiring it is a
    test-side decision, not one to take from here."""
    ln = norm_issuer(issuer_name(line_name))
    return bool(ln) and (ln.startswith(ident_norm) or ident_norm.startswith(ln))


def pick_us_adr_line(lines: list[dict]) -> dict | None:
    """Among the issuer's US-listed lines, prefer the Depositary-Receipt line;
    else the first US line. None if the issuer has no US listing (pure-EU,
    EU-Native gap).

    `lines` comes from `lines_by_share_class`, i.e. every line belongs to the
    home line's share class by construction. A share-class FIGI is a canonical
    identifier, so no name comparison is needed — and none is wanted: the
    optional name filter that used to live here is what produced the ROCHE ->
    ROCHE BOBOIS false-hit channel. It existed for the `search_issuer` fallback,
    whose full-text hits genuinely could belong to a different issuer; with that
    fallback gone, selection is purely US exchange code + DR preference.

    Anchoring on the share class is what makes a US line appear AT ALL for large
    issuers: the single unpaginated /search page returns 100 hits with zero US
    lines for RELX, Standard Chartered and Enel (measured 2026-09-03), so the
    verdict — not just the displayed symbol — came out wrong (`no_us_line` for a
    NYSE-listed 20-F filer).

    Operative output downstream is the CIK — it is identical across an issuer's
    US lines (same SEC registrant) and is authoritative. The chosen ticker also
    serves as adr_ticker, but that stays BEST-EFFORT DISPLAY ONLY: the share
    class contains both the sponsored ADR and the OTC foreign-ordinary 'F' line,
    and the 'F' line can come first (RLXXF for RELX, NONOF for Novo). Same CIK,
    same 20-F — only the displayed symbol differs. A `detect_annual_form` None
    downstream degrades to a quant-only dossier (reason `no_annual_form`) for an
    OTC line whose issuer files no annual form (e.g. RTMVF for Rightmove) — it
    no longer aborts the deep dive."""
    us = [ln for ln in lines if (ln.get("exchCode") or "").strip() in US_EXCH]
    if not us:
        return None
    for ln in us:
        if (ln.get("securityType2") or "") == "Depositary Receipt":
            return ln
    return us[0]


def _classify_us_line(
    ticker: str,
    ident: dict,
    *,
    openfigi: "OpenFIGIClient",
    edgar: "EdgarClient",
) -> ResolvedTicker:
    """Turn a verified home identity into either a filing source (US line ->
    CIK -> annual form) or a structural no-SEC-source verdict.

    The US line is found via the home line's `shareClassFIGI`: one mapping call
    returns every sibling line of the same share class. That replaced the
    full-text `search_issuer`, which reads only the first of a paginated result
    and therefore reported 'no US line' for issuers whose US lines sit on page
    two (RELX, Standard Chartered, Enel — 100 hits, 0 US lines, measured
    2026-09-03). This is a verdict defect, not a display defect.

    A home identity without that anchor raises instead of falling back to the
    search path, and instead of reporting `no_us_line`: see the raise below.

    Every VERDICT here is a statement about the issuer's SEC registration
    status, never about a failed call: transient OpenFIGI/EDGAR errors propagate
    as DataSourceError and are not caught anywhere in this path."""
    ident_name = ident.get("name", "")
    share_class = (ident.get("shareClassFIGI") or "").strip()
    if not share_class:
        # Without the anchor there is nothing to enumerate, so the issuer's US
        # lines are not merely unfound but undeterminable. Returning `no_us_line`
        # here would assert an absence we never established — a verdict dressed
        # up from a blind spot. Raise instead.
        raise DeepDiveError(
            f"{ticker}: home identity '{ident_name}' carries no shareClassFIGI — "
            f"without that anchor the issuer's US lines cannot be determined at "
            f"all; fail-loud, no verdict from an unexamined universe. Measured "
            f"across all 416 dotted EU tickers (2026-09-03) this never occurred: "
            f"if it fires, it is new information, not a known gap."
        )
    # Anchored path: canonical identifier, hence no issuer-name filter.
    us = pick_us_adr_line(openfigi.lines_by_share_class(share_class))
    if us is None:
        return no_sec_source(
            ticker,
            reason="no_us_line",
            note=(
                f"Kein SEC-Hard-Scuttlebutt: {ident_name} hat keine US-Notierung "
                f"und ist damit kein SEC-Registrant — kein 10-K, kein 20-F. Reines "
                f"EU-Listing; Dossier ist quant-only (Quant + Bewertung + Peers)."
            ),
        )
    us_ticker = (us.get("ticker") or "").strip()
    cik = edgar.get_cik(us_ticker)
    if not cik:
        return no_sec_source(
            ticker,
            reason="not_sec_registrant",
            note=(
                f"Kein SEC-Hard-Scuttlebutt: {ident_name} ist kein SEC-Registrant. "
                f"Die einzige US-Linie ({us_ticker}) ist eine OTC-/unsponsored-"
                f"Notierung, die ohne Zutun des Emittenten entstanden ist — sie "
                f"begründet keine SEC-Registrierung (kein CIK in "
                f"company_tickers.json) und damit keine Filing-Pflicht. Kein "
                f"Symbol-Fehler. Dossier ist quant-only (Quant + Bewertung + Peers)."
            ),
        )
    form = edgar.detect_annual_form(cik)
    if form is None:
        return no_sec_source(
            ticker,
            reason="no_annual_form",
            note=(
                f"Kein SEC-Hard-Scuttlebutt: {ident_name} (US-Linie {us_ticker}, "
                f"CIK {cik}) reicht weder 10-K noch 20-F ein. Dossier ist quant-only "
                f"(Quant + Bewertung + Peers)."
            ),
        )
    return ResolvedTicker(
        ticker=ticker, adr_ticker=us_ticker, cik=cik.zfill(10), form_type=form
    )


def _cache_get(
    cache_path: Path, ticker: str, ttl_days: int, negative_ttl_days: int
) -> ResolvedTicker | None:
    """Cache layer 2. Every read goes through .get(): a malformed or partial
    entry must degrade to a miss, never raise a KeyError that escapes the CLI as
    an unhandled exception. The two TTLs differ by design — a no-SEC-source
    verdict ages faster than a positive ADR mapping."""
    if not cache_path.exists():
        return None
    try:
        data = json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError):
        return None  # corrupt cache -> miss (fail-soft, mirrors filing_cache)
    if not isinstance(data, dict):
        return None
    entry = data.get(ticker.upper())
    if not isinstance(entry, dict):
        return None
    try:
        ts = datetime.fromisoformat(entry.get("_cached_at"))
    except (TypeError, ValueError):
        return None  # missing/unparsable timestamp -> miss, never a crash
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - ts).days

    reason = entry.get("no_sec_source_reason")
    if reason is None:
        cik = entry.get("cik")
        form_type = entry.get("form_type")
        if not cik or not form_type:
            return None  # half-written positive entry -> miss, never assert-trip
        if age_days >= ttl_days:
            return None
        return ResolvedTicker(ticker, entry.get("adr_ticker"), cik, form_type)

    # Forward compat: never trust a reason code this build does not understand.
    if reason not in NO_SEC_SOURCE_REASONS:
        return None
    note = entry.get("no_sec_source_note")
    if not note:
        return None
    if age_days >= negative_ttl_days:
        return None
    return no_sec_source(ticker, reason=cast(NoSecSourceReason, reason), note=note)


def _cache_put(cache_path: Path, resolved: ResolvedTicker) -> None:
    """Cache layer 2, write side. Asymmetry to _cache_get by design: reading a
    corrupt cache degrades to None (a miss, so the caller re-resolves), writing
    to one degrades to {} (the unusable content is overwritten). Neither may
    raise — an unhandled TypeError/KeyError here would kill the deep dive with
    no CLI exit code at all, which is exactly the failure class this layer must
    not produce."""
    data: dict = {}
    if cache_path.exists():
        try:
            loaded = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            loaded = None
        # Valid JSON of the wrong top-level type (e.g. a list) is as unusable as
        # invalid JSON — same treatment, never an indexing crash below.
        if isinstance(loaded, dict):
            data = loaded
    # All six keys, None for the absent half: one shape on disk for both verdicts.
    data[resolved.ticker.upper()] = {
        "adr_ticker": resolved.adr_ticker,
        "cik": resolved.cik,
        "form_type": resolved.form_type,
        "no_sec_source_reason": resolved.no_sec_source_reason,
        "no_sec_source_note": resolved.no_sec_source_note,
        "_cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache_path.with_suffix(cache_path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(cache_path)


def resolve_eu_adr(
    ticker: str,
    *,
    openfigi: "OpenFIGIClient",
    edgar: "EdgarClient",
    yfinance: "YFinanceClient",
    cache_path: Path,
    ttl_days: int,
    negative_ttl_days: int,
) -> ResolvedTicker:
    """Live EU-ADR resolution (cache layer 2 + live layer 3). Failure != empty:
    transient OpenFIGI/EDGAR/yfinance errors propagate as DataSourceError. A
    verifiable issuer without an SEC filing source is not a failure — it returns
    a degraded ResolvedTicker that drives a quant-only dossier.

    Three outcomes, three shapes:
      * filing source found -> positive ResolvedTicker, cached;
      * issuer verified, no SEC source -> classified verdict, cached;
      * identity not verifiable (no reference name, no name-matched OpenFIGI hit)
        -> `unverifiable_identity` verdict, NOT cached. Guessing an identity is
        forbidden, but so is aborting over one: the ticker's own quant data is
        unaffected, so the honest outcome is a labelled quant-only dossier.

    The one remaining raise is the missing share-class anchor in
    `_classify_us_line`: there the identity IS verified and only the enumeration
    handle is absent — a different, never-observed case that must stay loud.

    `negative_ttl_days` is keyword-only and required: the TTL asymmetry between a
    positive mapping and a no-source verdict is a policy decision, and a default
    here is how caller and tests drift apart silently."""
    cached = _cache_get(cache_path, ticker, ttl_days, negative_ttl_days)
    if cached is not None:
        return cached

    info = yfinance.get_ticker_info(ticker)  # DataSourceError on transient failure
    ref = info.get("longName") or info.get("shortName")
    if not ref:
        return unverifiable_identity(
            ticker,
            cause=(
                "kein Referenzname von yfinance, gegen den ein OpenFIGI-Treffer "
                "prüfbar wäre"
            ),
        )
    ref_norm = norm_issuer(ref)

    ident = find_home_identity(ticker, ref_norm, openfigi=openfigi)
    if ident is None:
        return unverifiable_identity(
            ticker,
            cause=("keine OpenFIGI-Heimatlinie stimmte mit dem Referenznamen überein"),
        )
    verdict = _classify_us_line(ticker, ident, openfigi=openfigi, edgar=edgar)
    if not verdict.has_filing_source:
        logger.info(
            "eu-adr: %s -> no SEC source (%s)", ticker, verdict.no_sec_source_reason
        )
    _cache_put(cache_path, verdict)
    return verdict
