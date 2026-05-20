from __future__ import annotations

import logging
import re

from pydantic import ValidationError

from app.deepdive.fisher_points import FISHER_POINTS
from app.deepdive.valuation_block import render_valuation_block
from app.errors import GeminiError
from app.services.gemini_deepdive_client import DeepDiveSynthesizer
from app.models.deep_dive_record import FisherPoint, QuantSnapshot

logger = logging.getLogger(__name__)

_SECTION_CITE_RE = re.compile(r"(10-K|20-F)\s*§\s*(\d+)", re.IGNORECASE)

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
    'Antworte NUR als JSON: {"points":[{"number":int,"title":str,"rating":int,'
    '"confidence":str,"reasoning":str,"sources":[str]}, ... 15 Einträge]}'
)


def _section_label(key: str) -> str:
    """'20-F_item5' -> '20-F §5' so the header the model sees matches the
    cite format the verification layer expects ('<form> §<item>')."""
    return key.replace("_item", " §", 1)


def _build_user_prompt(
    ticker: str, form_type: str, sections: dict[str, str], quant: QuantSnapshot
) -> str:
    titles = "\n".join(f"{n}. {t}" for n, t in FISHER_POINTS)
    sec_txt = "\n\n".join(
        f"### {_section_label(k)}\n{v}" for k, v in sections.items()
    ) or "(keine Filing-Sections extrahiert)"
    return (
        f"Ticker: {ticker} (Filing-Typ {form_type})\n\n"
        f"Fishers 15 Punkte:\n{titles}\n\n"
        f"Quant-Snapshot (JSON):\n{quant.model_dump_json()}\n\n"
        f"{render_valuation_block(quant)}\n\n"
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
) -> list[FisherPoint]:
    system = _SYSTEM_PROMPT
    user = _build_user_prompt(ticker, form_type, sections, quant)
    data = synthesizer.synthesize(system, user, max_input_tokens)

    raw_points = data.get("points", [])
    if len(raw_points) != 15:
        raise GeminiError(
            f"synthesis returned {len(raw_points)} points, expected 15"
        )

    sent_keys = set(sections.keys())
    points: list[FisherPoint] = []
    for rp in raw_points:
        sources = list(rp.get("sources", []))
        validated = _validate_sources(sources, form_type, sent_keys)
        if validated != sources:
            logger.warning(
                "point %s: hallucinated section cite -> downgraded to Inferenz",
                rp.get("number"),
            )
            rp = {**rp, "sources": validated}
            if rp.get("confidence") == "🟢":
                rp["confidence"] = "🟡"
        # Spec §5 / ADR-3: points 14/15 (Offenheit/Integrität) have no insider
        # or language data in B.1 -> confidence is code-enforced to 🔴 (not left
        # to the model). The B.2/B.4 deferral is surfaced in the dossier
        # source_coverage section (Task 8).
        if rp.get("number") in (14, 15):
            rp = {**rp, "confidence": "🔴"}
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
    sources: list[str], form_type: str, sent_keys: set[str]
) -> list[str]:
    """Any cited filing section not actually sent -> collapse to ['Inferenz']."""
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
        item = m.group(2)
        key = f"{form_type}_item{item}"
        if key not in sent_keys:
            return ["Inferenz"]
    return sources
