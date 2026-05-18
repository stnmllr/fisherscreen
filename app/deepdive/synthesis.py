from __future__ import annotations

import logging
import re
from typing import Any

from app.deepdive.fisher_points import FISHER_POINTS
from app.errors import GeminiError
from app.models.deep_dive_record import FisherPoint, QuantSnapshot

logger = logging.getLogger(__name__)

_SECTION_CITE_RE = re.compile(r"(10-K|20-F)\s*§\s*(\w+)", re.IGNORECASE)

_SYSTEM_PROMPT = (
    "Du bewertest ein Unternehmen gegen Phil Fishers 15 Punkte. Für JEDEN der "
    "15 Punkte: rating 1-5, confidence einer von 🟢/🟡/🔴, reasoning 2-3 Sätze "
    "Prosa (max 70 Wörter), sources als Array von Markern. Marker sind genau: "
    "eine Filing-Section wie '20-F §5' oder '10-K §7' (NUR Sections die im "
    "Input wirklich vorkommen — erfinde KEINE), '[yfinance, 5J]' für Quant, "
    "oder 'Inferenz' wenn du mehrere Quellen ohne direkten Zitat-Pfad "
    "kombinierst. Bei reiner Inferenz ist confidence maximal 🟡. Punkte 14 und "
    "15 (Offenheit/Integrität) ohne Sprach-/Insider-Daten: confidence 🔴. "
    'Antworte NUR als JSON: {"points":[{"number":int,"title":str,"rating":int,'
    '"confidence":str,"reasoning":str,"sources":[str]}, ... 15 Einträge]}'
)


def _build_user_prompt(
    ticker: str, form_type: str, sections: dict[str, str], quant: QuantSnapshot
) -> str:
    titles = "\n".join(f"{n}. {t}" for n, t in FISHER_POINTS)
    sec_txt = "\n\n".join(
        f"### {k}\n{v}" for k, v in sections.items()
    ) or "(keine Filing-Sections extrahiert)"
    return (
        f"Ticker: {ticker} (Filing-Typ {form_type})\n\n"
        f"Fishers 15 Punkte:\n{titles}\n\n"
        f"Quant-Snapshot (JSON):\n{quant.model_dump_json()}\n\n"
        f"Filing-Sections:\n{sec_txt}"
    )


def run_synthesis(
    *,
    ticker: str,
    form_type: str,
    sections: dict[str, str],
    quant: QuantSnapshot,
    synthesizer: Any,
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
        points.append(FisherPoint(**rp))
    return points


def _validate_sources(
    sources: list[str], form_type: str, sent_keys: set[str]
) -> list[str]:
    """Any cited filing section not actually sent -> collapse to ['Inferenz']."""
    for s in sources:
        m = _SECTION_CITE_RE.search(s)
        if not m:
            continue
        item = m.group(2)
        key = f"{form_type}_item{item}"
        if key not in sent_keys:
            return ["Inferenz"]
    return sources
