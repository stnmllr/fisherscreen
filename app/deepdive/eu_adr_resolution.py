from __future__ import annotations

import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, NamedTuple, Sequence, cast

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

# ---------------------------------------------------------------------------
# Issuer-name normalisation
#
# ONE pipeline, run over BOTH sides of every comparison. That symmetry — not
# any particular rule — is what makes the normalisation safe: yfinance and
# OpenFIGI spell the same company differently, and the only thing we can
# guarantee is that whatever we do to one spelling we also do to the other.
# `same_issuer_identity` is therefore the single production comparison, and it
# takes two RAW names rather than a pre-baked key, so a caller cannot normalise
# one side with a stale recipe.
#
# NOT built here, deliberately: prefix tolerance. Measured at +12.6 points, it
# accepts 'ROCHE HOLDING AG' as 'ROCHE BOBOIS SA-UNSPON ADR' — the documented
# false hit that strict equality exists to block. Every rule below is checked
# against that pair plus 'BT Group plc'/'BRITANNIA GROUP PLC' and
# 'Beacon Hill CBO III Ltd'/'GLANBIA PLC'.
# ---------------------------------------------------------------------------

# Letters NFKD does not decompose. They are letters in their own right, not
# accented ones, so the ASCII token class below would drop them without trace
# ('Ørsted' -> 'RSTED') and both sides would disagree in different ways.
#
# There is no correct transliteration, only the one the counterparty happens to
# use — Danish writes Å as AA, Swedish as A, and OpenFIGI is consistent with
# neither. This table is therefore NOT derived from orthography: every entry
# needs a real pair in cache/identity_name_corpus.json that justifies it.
# Justifying pairs (2026-09-04 corpus):
#   Ø/ø -> O : ORSTED.CO 'Ørsted A/S' <-> 'ORSTED A/S'
#              LSG.OL    'Lerøy Seafood Group ASA' <-> 'LEROY SEAFOOD GROUP ASA'
# Æ, ß, Ł, Þ, Ð are in the same NFKD-resistant class but no corpus pair
# spells any of them on one side and its transliteration on the other, so they
# are left out. (Å is NOT in that class, contrary to the brief: NFKD does
# decompose it into A + combining ring, so `_fold` already turns it into A on
# both sides for free.) An unjustified guess is not free: it would make the two sides
# disagree in a NEW way instead of the old one, and the failure would be a
# silent non-match nobody looks at. Absent from the table, they degrade to a
# separator — the name breaks into more tokens and simply fails to match, which
# is `unverifiable_identity`, i.e. honest.
_TRANSLITERATIONS = {"Ø": "O", "ø": "O"}

# A token is a run of characters between whitespace and hyphens; INSIDE it every
# character that is not ASCII alphanumeric is simply dropped. So 'S.A.' -> 'SA',
# "St. James's" -> ['ST', 'JAMESS'], 'B&M' -> 'BM', 'Aena S.M.E.,' -> ['AENA',
# 'SME']. Dropping punctuation is the second-largest measured gain (+17.7
# points): 'St. James's Place plc' and 'ST JAMES'S PLACE PLC' differ in nothing
# else, and 'AENA S.M.E., S.A.' only meets 'AENA SME SA' once the dots are gone
# and the pieces are rejoined rather than split apart.
#
# Whitespace and hyphen separate, other punctuation does not, because the hyphen
# is the one separator that carries meaning here: OpenFIGI appends the share
# class behind it.
_SPAN_RE = re.compile(r"[^\s\-]+")
_KEEP_RE = re.compile(r"[^A-Z0-9]")


class _Token(NamedTuple):
    """A token plus the two pieces of layout we cannot afford to forget.

    `hyphenated`: a hyphen separated it from the token before it. OpenFIGI
    appends the share class after a hyphen ('NOVO NORDISK A/S-B',
    'ASSA ABLOY AB-B'), while a bare letter that belongs to the name arrives
    some other way ('SAINSBURY (J) PLC'). Without this flag the two are
    indistinguishable and one of them gets mangled.

    `start`: offset into the UPPERCASED source string, so `issuer_name` can cut
    the original rather than rejoin tokens and lose its punctuation."""

    text: str
    hyphenated: bool
    start: int


# Listing/trading descriptors, i.e. what an exchange or data vendor adds to a
# name to say WHICH line this is. A positive list, replacing the old "strip a
# trailing '-TOKEN' that contains no space" heuristic — that rule was justified
# with 'COCA-COLA CO' (which it only survives by accident) and it truncated
# 'AIR FRANCE-KLM' to 'AIR FRANCE'.
#
# Both sides need this, not just the OpenFIGI side: yfinance carries LSE listing
# descriptors of its own ('3i Group Ord', 'ANTOFAGASTA PLC ORD 5P',
# 'WISE GROUP PLC CLS A ORD USD0.0').
_LISTING_DESCRIPTORS = frozenset(
    {
        "SHS",
        "SHARES",
        "CLS",
        "CL",
        "CLASS",
        "REG",
        "BR",
        "NY",
        "ADR",
        "SPONSORED",
        "UNSPON",
        "UNSPONSORED",
        "ORD",
    }
)
# Words that mark the token next to them as a share-class letter rather than
# part of the name ('PLC-CL A', 'AB - A SHARES', '-R SHS').
_CLASS_WORDS = frozenset({"CLS", "CL", "CLASS", "SHS", "SHARES"})
# The nominal-value tail LSE names carry: 'ORD 5P', 'ORD USD0.0'. Only stripped
# when it sits directly behind one of the introducers — otherwise the pattern
# would also match the '3I' in '3i Group'.
_NOMINAL_VALUE_RE = re.compile(r"[A-Z]{0,3}\d+[A-Z]{0,2}")
_NOMINAL_INTRODUCERS = frozenset({"ORD", "SHS", "SHARES"})

# Legal forms, written the way a human writes them and tokenised by the same
# pipeline below, so 'N.V.', 'NV' and 'A/S' all land in comparable shape.
# Spelled-out forms are the largest measured single gain (+24.0 points):
# 'Bayer Aktiengesellschaft' vs 'BAYER AG' is the whole German half of the
# corpus, and 'Société Générale Société anonyme' vs 'SOCIETE GENERALE SA' the
# French one.
#
# Corpus-justified additions (pair -> form): BAYN.DE/LXS.DE/SIE.DE
# AKTIENGESELLSCHAFT; GLE.PA SOCIETE ANONYME; TEL2-B.ST (PUBL); GALP.LS/JMT.LS
# SGPS; BATS.L P.L.C.; AML.L HOLDINGS; OERL.SW CORPORATION/CORP; RMS.PA SOCIETE
# EN COMMANDITE PAR ACTIONS; ERIC-B.ST TELEFONAKTIEBOLAGET. SOCIETA PER AZIONI,
# NAAMLOZE VENNOOTSCHAP and PUBLIC LIMITED COMPANY have no corpus pair — they
# are named in the spec and are the exact spelled-out siblings of SPA/NV/PLC,
# which are already here.
_LEGAL_FORM_SOURCES = (
    "AG",
    "AKTIENGESELLSCHAFT",
    "SA",
    "S.A.",
    "SOCIETE ANONYME",
    "SOCIETE EN COMMANDITE PAR ACTIONS",
    "N.V.",
    "NV",
    "NAAMLOZE VENNOOTSCHAP",
    "PLC",
    "P.L.C.",
    "PUBLIC LIMITED COMPANY",
    "SE",
    "SPA",
    "S.P.A.",
    "SOCIETA PER AZIONI",
    "ASA",
    "AB",
    "TELEFONAKTIEBOLAGET",
    "OYJ",
    "A/S",
    "SGPS",
    "PUBL",
    "HOLDING",
    "HOLDINGS",
    "GROUP",
    "INC",
    "LTD",
    "LIMITED",
    "COMPANY",
    "CORPORATION",
    "CORP",
    "HLDG",
    "HLDGS",
)


def _fold(span: str) -> str:
    """One span -> its comparable text: transliterate the letters NFKD cannot
    decompose, fold the diacritics NFKD can (+1.3 points, and free), drop the
    rest. A span made only of punctuation ('&') folds to '' and is discarded by
    the caller."""
    for source, target in _TRANSLITERATIONS.items():
        span = span.replace(source, target)
    decomposed = unicodedata.normalize("NFKD", span)
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return _KEEP_RE.sub("", stripped)


def _tokenise(name: str) -> list[_Token]:
    """Raw name -> comparable tokens, with the layout facts `_Token` documents.

    Spans are scanned on the UPPERCASED source and folded one by one, never on
    the folded whole: folding changes string lengths (NFKD expands, 'ß'.upper()
    is 'SS'), and `_Token.start` has to keep pointing into a string the caller
    can still slice."""
    text = (name or "").upper()
    tokens: list[_Token] = []
    previous_end = 0
    for match in _SPAN_RE.finditer(text):
        folded = _fold(match.group())
        if not folded:
            continue
        gap = text[previous_end : match.start()]
        tokens.append(_Token(folded, "-" in gap and bool(tokens), match.start()))
        previous_end = match.end()
    return tokens


def _is_share_class_letter(token: _Token, left: str, right: str) -> bool:
    """A single letter is a share class when the layout says so: hyphen-attached
    ('AB-B'), or sitting next to a class word ('CL A', 'R SHS'). A single letter
    that arrives any other way belongs to the name — 'SAINSBURY (J) PLC' is
    J Sainsbury, and dropping the J makes it a different company."""
    if len(token.text) != 1 or not token.text.isalpha():
        return False
    return token.hyphenated or left in _CLASS_WORDS or right in _CLASS_WORDS


def _drop_nominal_value_tail(tokens: Sequence[_Token]) -> list[_Token]:
    """'ORD 5P', 'ORD USD0.0' -> 'ORD'. Guarded by the introducer check so the
    pattern cannot eat the '3I' of '3i Group Ord'."""
    cut = len(tokens)
    while cut > 1 and _NOMINAL_VALUE_RE.fullmatch(tokens[cut - 1].text):
        cut -= 1
    if cut == len(tokens) or tokens[cut - 1].text not in _NOMINAL_INTRODUCERS:
        return list(tokens)
    return list(tokens[:cut])


def _drop_listing_descriptors(tokens: Sequence[_Token]) -> list[_Token]:
    """Strip the trailing run of listing descriptors. Runs ONCE, and before the
    legal forms are touched, because a class marker sits OUTSIDE the legal form
    ('NOVO NORDISK A/S-B' = name, form, class). A letter that only becomes
    trailing after the form is stripped is therefore not a class marker but part
    of the name, which is what keeps 'SAINSBURY (J) PLC' intact.

    Never strips the last token: a name reduced to nothing is not a match, it is
    a collision waiting to happen."""
    kept = _drop_nominal_value_tail(tokens)
    just_dropped = ""
    while len(kept) > 1:
        tail = kept[-1]
        if tail.text in _LISTING_DESCRIPTORS or _is_share_class_letter(
            tail, kept[-2].text, just_dropped
        ):
            just_dropped = tail.text
            kept.pop()
            continue
        break
    return kept


# Longest phrase first: 'PUBLIC LIMITED COMPANY' has to win against 'COMPANY',
# or the leftover 'PUBLIC LIMITED' becomes part of the identity.
_LEGAL_FORMS: tuple[tuple[str, ...], ...] = tuple(
    sorted(
        (tuple(t.text for t in _tokenise(source)) for source in _LEGAL_FORM_SOURCES),
        key=len,
        reverse=True,
    )
)


def _drop_legal_forms(tokens: Sequence[str]) -> list[str]:
    """Strip legal forms from BOTH ENDS, repeatedly. Scandinavian names carry
    them in front ('AB SKF', 'AB Volvo', +2.6 points), everyone else behind.

    Edges only, never the middle: a form inside a name is part of the name, and
    unrestricted removal is precisely how the previous substring rule turned
    'CREDIT AGRICOLE SA' into 'CREDITRICOLE' (the ' AG' of 'AGRICOLE').

    `len(kept) > size` rather than `>=` is the emptiness guard: a name that
    consists of nothing but a legal form keeps it. Returning '' here would make
    every such name equal to every other."""
    kept = list(tokens)
    stripping = True
    while stripping:
        stripping = False
        for form in _LEGAL_FORMS:
            size = len(form)
            if len(kept) > size and tuple(kept[-size:]) == form:
                del kept[-size:]
                stripping = True
                break
            if len(kept) > size and tuple(kept[:size]) == form:
                del kept[:size]
                stripping = True
                break
    return kept


def issuer_tokens(name: str) -> tuple[str, ...]:
    """The normalised identity of an issuer name, as tokens.

    Tokens rather than one string because word ORDER is the one difference the
    data sources produce that carries no information: 'Georg Fischer AG' vs
    'FISCHER (GEORG)-REG'. `same_issuer_identity` compares the multiset as a
    fallback (+3.8 points, counter-basket clean); `norm_issuer` joins them for
    the strict key."""
    tokens = _drop_listing_descriptors(_tokenise(name))
    return tuple(_drop_legal_forms([t.text for t in tokens]))


def norm_issuer(name: str) -> str:
    """Normalise an issuer name to a strict-equality key.
    'ROCHE HOLDING AG' -> 'ROCHE'; 'ROCHE BOBOIS SA-UNSPON ADR' -> 'ROCHEBOBOIS'
    (stays distinct -> Bobois noise excluded).

    The spaces go last, after tokenisation has done its work: 'Aena S.M.E., S.A.'
    and 'AENA SME SA' are the same company only once 'S M E' and 'SME' collapse
    to the same key.

    Prefer `same_issuer_identity` for comparisons — it adds the order-insensitive
    arm this key cannot express."""
    return "".join(issuer_tokens(name))


def same_issuer_identity(left: str, right: str) -> bool:
    """THE issuer comparison. Both raw names go through the same normalisation
    here, which is the property the whole design rests on; a caller that
    normalises one side itself can get that wrong, so it is not asked to.

    Two arms, both strict: identical token sequence, or identical token multiset.
    No prefix, no substring, no fuzzy distance. An empty side never matches."""
    left_tokens = issuer_tokens(left)
    right_tokens = issuer_tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return left_tokens == right_tokens or sorted(left_tokens) == sorted(right_tokens)


def issuer_name(figi_name: str) -> str:
    """Human-readable issuer identity: the name with its trailing listing
    descriptors removed ('ROCHE HOLDING AG-BR' -> 'ROCHE HOLDING AG',
    '3i Group Ord' -> '3I GROUP'). Legal forms stay — this is for reading and
    logging, not for comparing.

    Runs the same `_drop_listing_descriptors` the normalisation runs, so
    `norm_issuer(issuer_name(x)) == norm_issuer(x)`: the two-step call that older
    diagnostics use cannot drift from the one-step one.

    Cuts the ORIGINAL string at the first dropped token rather than rejoining
    tokens, so punctuation inside a name survives ('COCA-COLA CO',
    'AIR FRANCE-KLM' — the latter is what the replaced no-space heuristic
    truncated to 'AIR FRANCE')."""
    text = (figi_name or "").upper().strip()
    tokens = _tokenise(text)
    kept = _drop_listing_descriptors(tokens)
    if len(kept) == len(tokens):
        return text
    return text[: tokens[len(kept)].start].strip(" -\t")


def home_exch_codes(ticker: str) -> list[str]:
    suffix = ticker.rsplit(".", 1)[1] if "." in ticker else ""
    return SUFFIX_HOME_EXCH.get(suffix.upper(), [])


def local_symbol_variants(ticker: str) -> list[str]:
    """Ordered candidate local symbols for OpenFIGI (the variant ladder against
    the documented NVO miss: 'NOVO B'/'NOVOB' instead of the dashed form).

    The trailing-slash form comes last and answers a measured miss of its own:
    'BP.L' and 'JD.L' return nothing under any of the three forms above, because
    OpenFIGI carries BP as 'BP/'. The slash is Bloomberg's filler for short LSE
    symbols. It is appended for every exchange rather than only for '.L': the
    ladder stops at the first hit, so a symbol that already resolved never pays
    for it, and an exchange-conditional rule would be a second place where
    exchange knowledge lives.

    What this ladder canNOT do — and must not be extended to try — is a US symbol
    that DIFFERS from the home symbol rather than being spelled differently
    ('WISE.L' -> 'WSE'). That is what the override table is for."""
    base = ticker.rsplit(".", 1)[0] if "." in ticker else ticker
    variants = [
        base,
        base.replace("-", " "),
        base.replace("-", ""),
        base + "/",
    ]
    return list(dict.fromkeys(variants))  # order-preserving dedup


def find_home_identity(
    ticker: str, ref_name: str, *, openfigi: "OpenFIGIClient"
) -> dict | None:
    """Variant ladder + NAME-SANITY-CHECK: accept the first candidate whose
    OpenFIGI issuer name matches the reference (ADR-EU-2). Never 'first answer
    wins' — guards the variant-ladder false hit (ROCHE -> ROCHE BOBOIS).

    Takes the RAW reference name, not a pre-normalised key: normalisation is
    only sound while both sides go through the same function, and a key computed
    by the caller is a second recipe that can age separately. The comparison
    itself is `same_issuer_identity` — strict, and deliberately not
    prefix-tolerant.

    None when no candidate matched. That is a legitimate outcome, not an error:
    an unmatched name means we do not know which issuer this is, and the caller
    turns it into a classified `unverifiable_identity` verdict. What stays
    forbidden is the third possibility — returning an unverified match."""
    for exch in home_exch_codes(ticker):
        for cand in local_symbol_variants(ticker):
            ident = openfigi.map_ticker(cand, exch)
            if ident and same_issuer_identity(ident.get("name", ""), ref_name):
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
    ident = find_home_identity(ticker, ref, openfigi=openfigi)
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
