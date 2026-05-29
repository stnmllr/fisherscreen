from __future__ import annotations

import logging
import re
from datetime import date

from pydantic import ValidationError

from app.deepdive.fisher_points import FISHER_POINTS
from app.deepdive.valuation_block import render_valuation_block
from app.errors import GeminiError
from app.services.gemini_deepdive_client import DeepDiveSynthesizer
from app.models.deep_dive_record import FisherPoint, QuantSnapshot

logger = logging.getLogger(__name__)

# Single source of truth for the vintage cap. The numeric threshold lives ONLY
# here — the prompt references the concept semantically ("Filing-Alter"), never
# the number, so the rule and the soft prompt nudge cannot drift apart.
VINTAGE_THRESHOLD_DAYS = 180
VINTAGE_SENSITIVE_POINTS = frozenset({5, 6, 12})


def _today() -> date:
    """Return today's date. Indirection makes synthesis-time date patchable in tests."""
    return date.today()


_SECTION_CITE_RE = re.compile(r"(10-K|20-F)\s*§\s*(\d+[A-Z]?)", re.IGNORECASE)

# A filing-form token ('10-K'/'20-F') NOT in the strict '<form> §<item>' cite
# form: a real section cited in the wrong format (e.g. "20-F Item 5"). Detected
# on the RAW string — _norm_marker would fold "20-F" to "20f..." and lose the
# boundary. No quant/soft vocab marker contains these tokens, so false-positive
# risk is ~0.
_FILING_FORM_RE = re.compile(r"\b(10-K|20-F)\b", re.IGNORECASE)

# Body-heading guard (F4 defense-in-depth): a cited section body must START
# with the expected "ITEM N" heading, within a 300-char page-header tolerance.
# {item} is filled via .format(); the {{...}} is a literal regex quantifier.
_BODY_HEADING_PAT = r"^[\s\S]{{0,300}}?\bITEM\s+{item}\b"

# 2a.1c — source-marker vocabulary. The model invents non-section markers that
# reference real quant material (e.g. "Quant-Snapshot", "Forward-Estimates").
# Known quant sub-markers are canonicalized to a single quant marker; genuinely
# unknown markers collapse to "Inferenz" with a warning. The vocabulary is an
# EXPLICIT set (NOT derived from QuantSnapshot.model_fields): Gemini sees the
# rendered valuation block, not field names, so a field rename must never
# silently drop a still-emitted marker. The warning log drives growth: a new
# marker fires once, then gets one line added here.
_CANONICAL_QUANT = "yfinance, 5J"

_QUANT_MARKER_VOCAB = (
    "Quant-Snapshot",
    "forward_estimates",
    "peer_comparison",
    "historical_series",
    "trend_metrics",
    "Bewertung",
    "Bewertung & Kapitalstruktur",
)
_SOFT_MARKER_VOCAB = ("yfinance, 5J", "Marktkontext", "Inferenz")


def _norm_marker(s: str) -> str:
    """Fold a marker to a comparison key: lowercase + strip + collapse the
    capture-class separators (whitespace, _, -, &, comma). The comma is in the
    class so the canonical 'yfinance, 5J' folds to the same key its lookup uses
    (Bug 1)."""
    return re.sub(r"[\s_\-&,]+", "", s.strip().lower())


# key -> canonical display form. Built via _norm_marker over BOTH vocabularies,
# so keys and canonical strings are consistent by construction (no hand-typed
# key can drift from its source string).
_MARKER_CANON: dict[str, str] = {}
for _m in _SOFT_MARKER_VOCAB:
    _MARKER_CANON[_norm_marker(_m)] = _m
for _m in _QUANT_MARKER_VOCAB:
    _MARKER_CANON[_norm_marker(_m)] = _CANONICAL_QUANT


def _normalize_sources(sources: list[str]) -> list[str]:
    """Enforce the source-marker vocabulary (2a.1c). Runs BEFORE _validate_sources.

    - Filing-section cites (_SECTION_CITE_RE.search) pass through untouched. This
      guard MUST precede _norm_marker: otherwise '20-F §4B' folds to '20f§4b',
      misses the vocabulary, and collapses to Inferenz before _validate_sources
      ever sees it (destroys grounding — Lesson w / 1.5.2).
      .search (not .fullmatch) so a cite EMBEDDED in a longer string (e.g.
      "10-K §7 (S. 12)") is still recognized and passed through — matching how
      _validate_sources recognizes cites.
    - Misformatted filing cites (_FILING_FORM_RE.search but no § form, e.g.
      "20-F Item 5"): a real section cited in the WRONG format — the
      format-drift / 1.5.2 class. Logged with the SPECIFIC "not validatable"
      diagnostic (distinct from the generic "not in controlled vocabulary" of an
      invented marker), then collapsed to "Inferenz". NOT rewritten into a § cite
      — rewriting is explicitly rejected; remediation is a prompt/header nudge.
    - Known quant sub-markers -> _CANONICAL_QUANT; known soft markers -> their
      canonical form. Neither carries a confidence impact.
    - Anything else -> 'Inferenz' + warning (the warning is the catalogue-growth
      signal).
    - Order-preserving dedup at the end, so two distinct unknowns collapse to
      ['Inferenz'] and the FisherPoint validator's exact == ['Inferenz'] cap
      can fire."""
    out: list[str] = []
    for s in sources:
        if _SECTION_CITE_RE.search(s):
            out.append(s)
            continue
        if _FILING_FORM_RE.search(s):
            # §-less but filing-form-bearing: a real section cited in the wrong
            # format ("20-F Item 5" not "20-F §5"). This is the format-drift /
            # 1.5.2 class, whose remediation is a prompt/header nudge — NOT a
            # vocabulary catalogue add. Keep the SPECIFIC diagnostic, collapse to
            # Inferenz (no raw leak), and do NOT rewrite it into a § cite.
            logger.warning(
                "source %r looks like a filing cite but is not in the "
                "'<form> §<item>' format — not validatable", s
            )
            out.append("Inferenz")
            continue
        canon = _MARKER_CANON.get(_norm_marker(s))
        if canon is not None:
            out.append(canon)
        else:
            logger.warning(
                "source %r not in controlled vocabulary -> Inferenz", s
            )
            out.append("Inferenz")
    # order-preserving dedup (so two distinct unknowns collapse to ['Inferenz']
    # and the FisherPoint == ['Inferenz'] cap can fire)
    return list(dict.fromkeys(out))


_SYSTEM_PROMPT = (
    "Du bewertest ein Unternehmen gegen Phil Fishers 15 Punkte als kritischer "
    "Analyst, nicht als Werbetexter. Für JEDEN der 15 Punkte: rating 1-5, "
    "confidence 🟢/🟡/🔴, reasoning 2-3 Sätze Prosa (max 70 Wörter), sources-Array.\n"
    "STERNE-RUBRIK (relativ, nicht absolut): 5 = belegbar ÜBERLEGEN gegenüber "
    "den relevanten Konkurrenten der Branche; 4 = klar überdurchschnittlich; "
    "3 = solide/marktüblich; 2 = unterdurchschnittlich; 1 = schwach. 'Gut in "
    "absoluten Zahlen' ist NICHT 5, wenn ein direkter Wettbewerber stärker ist.\n"
    "VERTEILUNG: typische Verteilung für ein gutes, aber nicht außergewöhnliches "
    "Unternehmen liegt bei höchstens 4 von 15 Punkten mit 5 Sternen (Heuristik) "
    "und mindestens 3 Punkten mit ≤3 Sternen. HARTER CAP (nicht verhandelbar): "
    "MAXIMAL 5 von 15 Punkten dürfen ⭐⭐⭐⭐⭐ tragen — keine Ausnahme. JEDER "
    "⭐⭐⭐⭐⭐-Punkt MUSS im reasoning konkret benennen, gegenüber welchem "
    "Konkurrenten oder Branchen-Standard die Überlegenheit belegt ist "
    "(Reichweite oder absolute Zahl allein reicht NICHT). Prüfe am Ende: wenn "
    "du keinen Punkt unter 4 Sternen hast, ist deine Analyse vermutlich zu "
    "freundlich — gehe die schwächsten Punkte erneut durch.\n"
    "ABGRENZUNG (verwandte Punkte müssen UNTERSCHIEDLICH argumentieren, kein "
    "Recycling): P2 = Wille, NEUE Felder zu erschließen ≠ P3 = Output pro F&E-"
    "Dollar. P4 = Vertriebs-WIRKSAMKEIT (nicht bloße Reichweite/Länderzahl) ≠ "
    "P11 = struktureller Wettbewerbsvorteil/Burggraben. P5 = Margenhöhe ≠ P6 = "
    "Maßnahmen zur Margen-ERHALTUNG. P12 = langfristige Gewinnpriorisierung ≠ "
    "P13 = Finanzierung ohne Verwässerung. Reichweite ('170 Länder') ist KEIN "
    "Wirksamkeitsbeleg.\n"
    "BEAR-CASE-PFLICHT: das reasoning muss explizit ein konkretes Gegenargument, "
    "Risiko oder Schwächezeichen benennen — eingeleitet durch Wörter wie "
    "'allerdings', 'jedoch', 'Risiko', 'unter Druck', 'Schwäche', oder "
    "Vergleichbares. Ein reasoning ohne erkennbares Gegenargument ist "
    "unvollständig; setze in diesem Fall confidence eine Stufe herab.\n"
    "WETTBEWERB: bei den Punkten 4, 5, 6, 11, 12 musst du den/die relevanten "
    "Hauptkonkurrenten benennen und einordnen. Nenne Konkurrenten nur "
    "namentlich, wenn sie im Filing-Volltext oder in den Quants vorkommen. "
    "Sonst formuliere generisch ('der dominante US-Wettbewerber', 'klinisch "
    "überlegene Konkurrenzprodukte') und markiere Marktkontext. Erfinde "
    "keine Konkurrenznamen. Hast du keine harte Quelle, halte confidence ≤ 🟡 "
    "— erfinde dafür NIEMALS eine Filing-Section.\n"
    # P13-Nudge — between WETTBEWERB and CONFIDENCE for context flow.
    # Position is not asserted by tests (deliberately — would be brittle).
    "P13 (Wachstum ohne Verwässerung) — KONKRET: FCF-Yield aus dem "
    "Bewertungsblock und Shares-Outstanding-Trend aus dem Quant-Snapshot "
    "sind die zwei Schlüssel-Indikatoren. Positiver FCF-Yield + stabiler/"
    "sinkender Share-Count = Verwässerungs-Frage praktisch entschieden "
    "(eher ⭐⭐⭐⭐ / 🟢). Negativer FCF-Yield ODER steigende Shares = "
    "Verwässerungs-Risiko, prüfe Schulden-/Equity-Mix. Wenn FCF-Yield "
    "verfügbar ist, muss der Wert im reasoning genannt sein. Bei "
    "n/a-Werten nenne das stattdessen explizit und begründe in 1 Satz, "
    "warum (z.B. fehlende Cashflow-Daten im Filing).\n"
    "CONFIDENCE: 🟢 NUR wenn die Kernaussage direkt aus einer harten Quelle "
    "(Filing-Section oder Quant) belegbar ist. Inferenz, Allgemeinwissen oder "
    "Marktkontext ⇒ höchstens 🟡. Punkte 14 und 15 ohne Sprach-/Insider-Daten "
    "⇒ 🔴.\n"
    "SOURCES: Marker sind genau (jeweils OHNE eckige Klammern — der Renderer "
    "wrappt automatisch): eine Filing-Section wie '20-F §5' oder '10-K §7' "
    "(NUR Sections die im Input wirklich vorkommen — erfinde KEINE), "
    "'yfinance, 5J' für Quant, 'Marktkontext' für Wettbewerbs-/Branchen-"
    "einordnung ohne Quelle, oder 'Inferenz' für kombinierte Quellen ohne "
    "direkten Zitat-Pfad. Bei reiner Inferenz confidence ≤ 🟡.\n"
    "VINTAGE: Enthält der Input oben einen 'Aktualitäts-Hinweis', benenne das "
    "Filing-Alter ausdrücklich im reasoning der dort genannten Punkte als "
    "Einschränkung der Aktualität der Stichtagskennzahlen. Ohne solchen Hinweis "
    "erwähne das Filing-Alter NICHT.\n"
    'Antworte NUR als JSON: {"points":[{"number":int,"title":str,"rating":int,'
    '"confidence":str,"reasoning":str,"sources":[str]}, ... 15 Einträge]}'
)


def _section_label(key: str) -> str:
    """'20-F_item5' -> '20-F §5' so the header the model sees matches the
    cite format the verification layer expects ('<form> §<item>')."""
    return key.replace("_item", " §", 1)


def _days_since_filing(filing_date: str | None) -> int | None:
    """Days between the SEC filing_date and today (_today(), patchable).

    THE single day count for synthesis time: the vintage line, the staleness
    hint and the confidence cap all read from this one function, so they cannot
    drift apart on a future refactor. None if filing_date is absent or not an
    ISO date — fail-soft, mirroring DeepDiveRecord.days_since_filing. Computed
    here (not via the DeepDiveRecord property) because the record does not exist
    yet at synthesis time.
    """
    if filing_date is None:
        return None
    try:
        parsed = date.fromisoformat(filing_date)
    except ValueError:
        return None
    return (_today() - parsed).days


def _format_vintage_line(filing_date: str | None, days: int | None) -> str:
    """Render the compact filing-vintage anchor for the synthesis prompt.

    Format (valid date): 'Filing-Stand: YYYY-MM-DD (vor N Tagen)'
    Format (missing/unparseable): 'Filing-Stand: unbekannt'

    `days` is passed in from the single _days_since_filing computation rather
    than parsed again here; days is None iff filing_date is missing or not an
    ISO date.
    """
    if days is None:
        return "Filing-Stand: unbekannt"
    return f"Filing-Stand: {filing_date} (vor {days} Tagen)"


def _format_vintage_hint(days: int | None) -> str:
    """Code-emitted staleness signal for the synthesis prompt (1.1b candidate 3).

    Emitted ONLY when the filing is past the vintage threshold. The model reacts
    to this signal's presence instead of judging staleness itself — the MSFT
    acceptance run showed the model never reads a ~10-month-old annual 10-K as
    'veraltet', so a subjective gate never fired. The threshold and the affected
    point set stay single-sourced in the code constants; the concrete day count
    is rendered so the wording survives a future threshold change. Empty string
    when the filing is fresh or undated — which makes the anti-over-mention
    property structural (the prompt simply has no hint to pick up), not wording.
    """
    if days is None or days <= VINTAGE_THRESHOLD_DAYS:
        return ""
    points = ", ".join(str(n) for n in sorted(VINTAGE_SENSITIVE_POINTS))
    return (
        f"Aktualitäts-Hinweis: Dieses Filing ist {days} Tage alt; seine "
        f"Stichtagskennzahlen (Punkte {points}) sind möglicherweise nicht "
        f"mehr tagesaktuell."
    )


def _build_user_prompt(
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    filing_date: str | None = None,
) -> str:
    titles = "\n".join(f"{n}. {t}" for n, t in FISHER_POINTS)
    sec_txt = "\n\n".join(
        f"### {_section_label(k)}\n{v}" for k, v in sections.items()
    ) or "(keine Filing-Sections extrahiert)"
    days = _days_since_filing(filing_date)
    vintage = _format_vintage_line(filing_date, days)
    hint = _format_vintage_hint(days)
    vintage_block = f"{vintage}\n{hint}" if hint else vintage
    return (
        f"Ticker: {ticker} (Filing-Typ {form_type})\n\n"
        f"Fishers 15 Punkte:\n{titles}\n\n"
        f"Quant-Snapshot (JSON):\n{quant.model_dump_json()}\n\n"
        f"{render_valuation_block(quant)}\n\n"
        f"{vintage_block}\n\n"
        f"Filing-Sections:\n{sec_txt}"
    )


def run_synthesis(
    *,
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    synthesizer: DeepDiveSynthesizer,
    max_input_tokens: int,
    filing_date: str | None = None,
) -> list[FisherPoint]:
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(ticker, form_type, sections, quant, filing_date)
    data = synthesizer.synthesize(system, user, max_input_tokens)

    raw_points = data.get("points", [])
    if len(raw_points) != 15:
        raise GeminiError(
            f"synthesis returned {len(raw_points)} points, expected 15"
        )

    sent_keys = set(sections.keys())
    days = _days_since_filing(filing_date)
    points: list[FisherPoint] = []
    for rp in raw_points:
        sources = list(rp.get("sources", []))
        normalized = _normalize_sources(sources)
        validated = _validate_sources(normalized, form_type, sent_keys, sections)
        rp = {**rp, "sources": validated}
        # The confidence downgrade keys on a SECTION collapse (validated differs
        # from the already-normalized list), NOT on mere canonicalization —
        # otherwise every quant-citing point would be falsely demoted from 🟢.
        if validated != normalized:
            logger.warning(
                "point %s: hallucinated section cite -> downgraded to Inferenz",
                rp.get("number"),
            )
            if rp.get("confidence") == "🟢":
                rp["confidence"] = "🟡"
        # Spec §5 / ADR-3: points 14/15 (Offenheit/Integrität) have no insider
        # or language data in B.1 -> confidence is code-enforced to 🔴 (not left
        # to the model). The B.2/B.4 deferral is surfaced in the dossier
        # source_coverage section (Task 8).
        if rp.get("number") in (14, 15):
            rp = {**rp, "confidence": "🔴"}
        # Vintage cap: a stale cited filing caps the model's confidence to 🟡
        # for the vintage-sensitive points {5,6,12}. The == "🟢" guard against
        # the CURRENT (end) value makes this order-independent and only-lowering:
        # it never raises 🔴/🟡, and is robust if enforcement steps get reordered.
        if (
            days is not None
            and days > VINTAGE_THRESHOLD_DAYS
            and rp.get("number") in VINTAGE_SENSITIVE_POINTS
            and rp.get("confidence") == "🟢"
        ):
            rp = {**rp, "confidence": "🟡"}
        try:
            points.append(FisherPoint(**rp))
        except ValidationError as exc:
            raise GeminiError(
                f"synthesis point {rp.get('number')} violates the contract: {exc}"
            ) from exc

    five_star_count = sum(1 for p in points if p.rating == 5)
    low_rating_count = sum(1 for p in points if p.rating <= 3)
    if five_star_count > 5:
        logger.warning(
            f"synthesis: sterne-inflation — {five_star_count}/15 punkte ⭐⭐⭐⭐⭐ "
            f"(soll: ≤5). prüfe ob analyse zu freundlich."
        )
    if low_rating_count < 2:
        logger.warning(
            f"synthesis: keine schwachen punkte — nur {low_rating_count}/15 mit ≤⭐⭐⭐. "
            f"prüfe ob bear-cases ernst genommen wurden."
        )
    return points


def _validate_sources(
    sources: list[str],
    form_type: str,
    sent_keys: set[str],
    sections: dict[str, str],
) -> list[str]:
    """Collapse a point's sources to ['Inferenz'] when a cited filing section
    is either not actually sent or carries a mis-labeled body. F4 defense-in-
    depth: a sent section is only accepted if its body starts (within a
    300-char page-header tolerance) with the expected 'ITEM N' heading."""
    for s in sources:
        m = _SECTION_CITE_RE.search(s)
        if not m:
            if "10-K" in s or "20-F" in s:
                logger.warning(
                    "source %r looks like a filing cite but is not in the "
                    "'<form> §<item>' format — not validatable",
                    s,
                )
            continue
        # .upper() so a lowercase "§1a" still keys "10-K_item1A".
        item_full = m.group(2).upper()
        numeric_part = re.match(r"\d+", item_full).group(0)
        key_full = f"{form_type}_item{item_full}"
        key_numeric = f"{form_type}_item{numeric_part}"
        if key_full in sent_keys:
            # 10-K §1A/§7A: distinct SEC item, suffix kept.
            key, item_for_body_check = key_full, item_full
        elif key_numeric in sent_keys:
            # 20-F §4B/§5C: sub-paragraph -> falls back to the parent item.
            key, item_for_body_check = key_numeric, numeric_part
        else:
            return ["Inferenz"]
        body = sections.get(key, "")
        pat = re.compile(
            _BODY_HEADING_PAT.format(item=re.escape(item_for_body_check)),
            re.IGNORECASE,
        )
        if not pat.match(body):
            logger.warning(
                "cite %s: body does not start with expected ITEM %s heading "
                "within 300-char tolerance — downgraded to Inferenz",
                s,
                item_for_body_check,
            )
            return ["Inferenz"]
    return sources
