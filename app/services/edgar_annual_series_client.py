"""Jahresreihen aus der SEC-XBRL-companyfacts-API.

Liefert die drei Reihen, die die Stetigkeits-Dimension braucht — Umsatz,
operatives Ergebnis, Nettogewinn — als Jahr->Wert-Folgen aus den 10-K-Fakten
eines Emittenten. Ein Request je CIK: companyfacts bündelt alle Konzepte und
alle Jahre in einem Dokument.

Eigenkapital ist bewusst NICHT dabei. Die Stetigkeit misst die schlechteste
Nettomarge, nicht die schlechteste Eigenkapitalrendite: 41 der 610 gemessenen
US-Titel haben zu wenige Jahre mit positivem Eigenkapital, darunter FICO (fünf
solche Jahre) und TDG — beides Titel, die nach Rückkäufen negativ bilanzieren
und die die Dimension ausdrücklich oben behalten soll. Siehe Spec §5.

Die Extraktion stammt unverändert aus `scripts/probe_edgar_history.py`; sie ist
an 610 Titeln gemessen und trägt drei Regressionsfälle, die jede naive Lesart
still verkürzt hätte (siehe DIE DREI FALLEN unten). Das Skript importiert sie
jetzt von hier, damit es genau eine Implementierung gibt.

DIE DREI FALLEN — jede erzeugt plausible, aber zu kurze Reihen:

1. `fy`/`fp` benennen das MELDENDE FILING, nicht die Periode des Wertes. Ein
   FY2025-10-K trägt seine Vergleichsjahre FY2023 und FY2024 ebenfalls mit
   `fy=2025, fp=FY`. Nach `fy` zu deduplizieren zieht drei echte Jahre zu einem
   zusammen. Geschlüsselt wird deshalb nach der Periode selbst.
2. ASC 606 hat die meisten US-Filer um 2018 von `Revenues` auf
   `RevenueFromContractWithCustomerExcludingAssessedTax` umgestellt. Wer den
   ersten Tag nimmt, der überhaupt Daten trägt, bekommt bei Agilent
   (CIK 1090872) eine Reihe, die 2017 endet — 9 Jahre statt 19. Die
   Kandidaten-Tags eines Konzepts werden deshalb zu EINER Reihe verschmolzen.
3. Ein 10-K taggt auch Quartals-Bilanzstichtage. Akamais `2022-03-31`
   (CIK 1086222) trägt das Geschäftsjahr-Etikett 2021 und verdrängt als
   späteres Datum den echten Jahresabschluss — aus 20 Jahren werden 4. Die
   Reihe wird auf den Jahresabschluss-Jahrestag verankert.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, Iterable, Protocol, Sequence

if TYPE_CHECKING:
    from app.services.edgar_client import EdgarClient

# Version der Extraktionslogik. Hochzählen, sobald sich ändert, WAS aus
# companyfacts gelesen wird — gecachte Extrakte werden dann verworfen statt
# still warmgehalten. Ein warmer Cache, der eine Verhaltensänderung maskiert,
# hat in diesem Projekt schon einmal eine Verifikation wertlos gemacht.
EXTRACTION_SCHEMA = 2

# Nur der Jahresabschluss zählt. 20-F wird bewusst NICHT mitgezählt: ein
# US-notierter Foreign Private Issuer meldet unter ifrs-full mit anderen Tags,
# das wäre eine zweite Extraktion mit eigener Konzeptliste (Spec §3).
ANNUAL_FORMS = ("10-K", "10-K/A")

# Eine Jahresperiode. 52/53-Wochen-Geschäftsjahre (Handel) schwanken um einige
# Tage; ein Rumpfjahr nach Umstellung des Geschäftsjahresendes fällt raus.
DURATION_MIN_DAYS = 340
DURATION_MAX_DAYS = 400

# Abstand zwischen zwei aufeinanderfolgenden Jahresenden. Großzügiger als das
# Periodenfenster, weil hier zwei Stichtage verglichen werden, keine Dauer.
GAP_MIN_DAYS = 300
GAP_MAX_DAYS = 430

# Wie weit ein Stichtag vom Jahresabschluss-Jahrestag abweichen darf (Falle 3).
# 45 Tage lassen 52/53-Wochen-Geschäftsjahre und Jahreswechsel-Stichtage durch,
# ein Quartal nicht.
ANNIVERSARY_TOLERANCE_DAYS = 45

TAXONOMY = "us-gaap"

# Die drei Konzepte der Stetigkeits-Dimension samt Kandidaten-Tags, in
# Definitionsrangfolge (Spec §4.1). Die hinteren Einträge sind keine Zierde:
# ohne sie fällt die Abdeckung von 85,1 % auf 59,7 % — eine Namens-, keine
# Datenlücke.
CONCEPTS: dict[str, list[str]] = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "RevenueFromContractWithCustomerIncludingAssessedTax",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ],
    "operating_income": [
        "OperatingIncomeLoss",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItems"
        "NoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAnd"
        "IncomeLossFromEquityMethodInvestments",
    ],
    "net_income": [
        "NetIncomeLoss",
        "ProfitLoss",
        "NetIncomeLossAvailableToCommonStockholdersBasic",
        "IncomeLossFromContinuingOperations",
    ],
}

# Grund, aus dem eine Reihe unbrauchbar ist. Er wird als eigenes Feld geführt
# und NIE aus einem Zahlenwert abgeleitet (Spec §8.1). Ein 404 auf companyfacts
# — der Emittent hat gar keine XBRL-Fakten — ist der Extremfall desselben
# Befunds und trägt denselben Grund, damit der Report bei den drei Marken aus
# Spec §7 bleibt.
NO_CONCEPT = "no_concept"


@dataclass(frozen=True)
class ConceptCoverage:
    """Eine Jahresreihe eines Konzepts, ältestes Jahr zuerst.

    `naive_fy_count` trägt keine Produktivlogik: es ist die Zahl, die eine
    `fy`-basierte Lesart geliefert hätte (Falle 1), und dient der Messprobe als
    Beleg dafür, dass die Perioden-Schlüsselung nötig ist.
    """

    concept: str | None
    unit: str | None
    years: tuple[int, ...]
    values: tuple[float, ...]
    contiguous: int
    restatements: int
    naive_fy_count: int


EMPTY_COVERAGE = ConceptCoverage(
    concept=None,
    unit=None,
    years=(),
    values=(),
    contiguous=0,
    restatements=0,
    naive_fy_count=0,
)


@dataclass(frozen=True)
class AnnualSeriesRecord:
    """Die Jahresreihen eines Emittenten, wie sie aus companyfacts kommen.

    Kein Fenster, kein Schnitt über gemeinsame Jahre — das entscheidet die
    Stetigkeits-Berechnung, nicht der Datenzugriff.
    """

    cik: str
    entity: str
    concepts: dict[str, ConceptCoverage]
    reason: str | None

    @property
    def usable(self) -> bool:
        """Alle drei Reihen vorhanden. Wie lang sie sein müssen, entscheidet
        die Fensterregel weiter oben im Stapel."""
        return self.reason is None


class EdgarAnnualSeriesClient(Protocol):
    def get_annual_series(self, cik: str) -> AnnualSeriesRecord: ...


class EdgarAnnualSeriesClientImpl:
    """Dünner Wrapper: ein companyfacts-Abruf, dann reine Extraktion.

    Der HTTP-Zugriff läuft über den injizierten `EdgarClient`, nicht über ein
    eigenes httpx — so teilen sich alle SEC-Aufrufe eines Prozesses denselben
    Rate Limiter und denselben User-Agent.
    """

    def __init__(self, edgar: "EdgarClient") -> None:
        self._edgar = edgar

    def get_annual_series(self, cik: str) -> AnnualSeriesRecord:
        facts = self._edgar.get_company_facts(cik)
        return build_annual_series(cik, facts)


def build_annual_series(cik: str, facts: dict[str, Any]) -> AnnualSeriesRecord:
    """companyfacts-Dokument -> die drei Jahresreihen. Reine Funktion."""
    concepts = {
        key: extract_concept(facts, candidates) for key, candidates in CONCEPTS.items()
    }
    missing = any(cov.concept is None for cov in concepts.values())
    return AnnualSeriesRecord(
        cik=cik,
        entity=str(facts.get("entityName", "")),
        concepts=concepts,
        reason=NO_CONCEPT if missing else None,
    )


# --------------------------------------------------------------------------
# Extraktion — reine Logik, kein Netz
# --------------------------------------------------------------------------


def fiscal_label(end: date) -> int:
    """Geschäftsjahr-Etikett eines Periodenendes. Ein Handelsjahr, das am
    31.01.2025 schließt, ist Geschäftsjahr 2024. Nur Anzeige — die
    Zusammenhangsprüfung rechnet auf den Stichtagen selbst."""
    return end.year if end.month >= 6 else end.year - 1


def contiguous_run(ends: Sequence[date]) -> int:
    """Länge der Kette aufeinanderfolgender Jahre, die am JÜNGSTEN Stichtag
    endet. Eine Lücke davor beendet die Kette — zehn Jahre mit Loch in der
    Mitte sind keine zehn Jahre Historie."""
    if not ends:
        return 0
    ordered = sorted(ends)
    run = 1
    for newer, older in zip(reversed(ordered), reversed(ordered[:-1])):
        gap = (newer - older).days
        if GAP_MIN_DAYS <= gap <= GAP_MAX_DAYS:
            run += 1
        else:
            break
    return run


def taxonomies(facts: dict[str, Any]) -> list[str]:
    return sorted(facts.get("facts", {}))


def available_tags(facts: dict[str, Any], taxonomy: str) -> list[str]:
    return sorted(facts.get("facts", {}).get(taxonomy, {}))


def _parse_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def _annual_entries(entries: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Jahres-Fakten aus 10-K/10-K/A, je mit Perioden-Schlüssel und Stichtag."""
    out: list[dict[str, Any]] = []
    for entry in entries:
        if entry.get("form") not in ANNUAL_FORMS:
            continue
        end = _parse_date(entry.get("end", ""))
        if end is None:
            continue
        start_raw = entry.get("start")
        if start_raw is None:  # Bestandsgroesse: Stichtag
            out.append({"key": ("i", end), "end": end, "entry": entry})
            continue
        start = _parse_date(start_raw)
        if start is None:
            continue
        if not DURATION_MIN_DAYS <= (end - start).days <= DURATION_MAX_DAYS:
            continue
        out.append({"key": ("d", start, end), "end": end, "entry": entry})
    return out


def _anniversary_distance(end: date, anchor: date) -> int:
    """Abstand in Tagen zum nächsten Jahrestag des Anker-Stichtags."""
    best = 10**6
    for year in (end.year - 1, end.year, end.year + 1):
        try:
            anniversary = date(year, anchor.month, anchor.day)
        except ValueError:  # 29. Februar in einem Nicht-Schaltjahr
            anniversary = date(year, anchor.month, anchor.day - 1)
        best = min(best, abs((end - anniversary).days))
    return best


def _negated(filed: str) -> tuple[int, ...]:
    """Sortierschlüssel, der ein späteres `filed` nach vorne holt, damit
    `min()` über (priority, filed-absteigend) gebildet werden kann."""
    return tuple(-ord(c) for c in filed)


def _coverage_for(
    pooled: list[dict[str, Any]], candidates: Sequence[str]
) -> ConceptCoverage:
    # 1. Perioden-Bucket: dieselbe Periode, in mehreren Filings gemeldet --
    #    und moeglicherweise unter mehreren Tags.
    buckets: dict[Any, list[dict[str, Any]]] = {}
    for item in pooled:
        buckets.setdefault(item["key"], []).append(item)

    chosen: list[dict[str, Any]] = []
    for items in buckets.values():
        # 2. Gewinner: der frueheste Kandidat der Liste, darin das spaeteste
        #    `filed` -- die Korrektur schlaegt das Original.
        winner = min(
            items, key=lambda i: (i["priority"], _negated(i["entry"].get("filed", "")))
        )
        val = winner["entry"].get("val")
        if val is None:
            continue
        # 3. Restatement nur INNERHALB eines Tags. Zwei Tags koennen dieselbe
        #    Periode mit verschiedener Definition melden (Gesamtumsatz gegen
        #    Umsatz aus Vertraegen) -- das ist keine Korrektur.
        same_tag = {i["entry"].get("val") for i in items if i["tag"] == winner["tag"]}
        chosen.append(
            {
                "label": fiscal_label(winner["end"]),
                "end": winner["end"],
                "val": float(val),
                "restated": 1 if len(same_tag) > 1 else 0,
                "tag": winner["tag"],
                "unit": winner["unit"],
                "priority": winner["priority"],
            }
        )

    # 4. Auf den Jahresabschluss verankern. Der juengste Stichtag gibt den
    #    Jahrestag vor; was mehr als ANNIVERSARY_TOLERANCE_DAYS davon abweicht,
    #    ist kein Jahresabschluss und faellt raus, statt um ein Etikett zu
    #    konkurrieren.
    if not chosen:
        return EMPTY_COVERAGE
    anchor = max(chosen, key=lambda r: r["end"])["end"]
    for row in chosen:
        row["offset"] = _anniversary_distance(row["end"], anchor)
    chosen = [r for r in chosen if r["offset"] <= ANNIVERSARY_TOLERANCE_DAYS]

    # 5. Ein Geschaeftsjahr-Etikett, ein Wert: der Stichtag, der dem Jahrestag am
    #    naechsten liegt.
    per_label: dict[int, dict[str, Any]] = {}
    for row in chosen:
        held = per_label.get(row["label"])
        if held is None or (-row["offset"], row["end"], -row["priority"]) > (
            -held["offset"],
            held["end"],
            -held["priority"],
        ):
            per_label[row["label"]] = row
    if not per_label:
        return EMPTY_COVERAGE

    ordered = [per_label[label] for label in sorted(per_label)]
    contributing = [c for c in candidates if any(r["tag"] == c for r in ordered)]
    naive = {
        i["entry"].get("fy")
        for i in pooled
        if i["entry"].get("fp") == "FY" and i["entry"].get("fy") is not None
    }
    return ConceptCoverage(
        concept="+".join(contributing),
        unit=ordered[-1]["unit"],
        years=tuple(row["label"] for row in ordered),
        values=tuple(row["val"] for row in ordered),
        contiguous=contiguous_run([row["end"] for row in ordered]),
        restatements=sum(row["restated"] for row in ordered),
        naive_fy_count=len(naive),
    )


def extract_concept(
    facts: dict[str, Any],
    candidates: Sequence[str],
    *,
    taxonomy: str = TAXONOMY,
) -> ConceptCoverage:
    """Abdeckung EINES Konzepts über alle seine Kandidatenbezeichnungen.

    Die Kandidaten werden zusammengeführt, nicht der Reihe nach probiert
    (Falle 2). Bei Überschneidung gewinnt der früher gelistete Kandidat — die
    Reihenfolge der Liste ist die Definitionsrangfolge."""
    node = facts.get("facts", {}).get(taxonomy, {})
    pooled: list[dict[str, Any]] = []
    for priority, name in enumerate(candidates):
        units = node.get(name, {}).get("units", {})
        if not units:
            continue
        unit = "USD" if "USD" in units else sorted(units)[0]
        for item in _annual_entries(units[unit]):
            pooled.append({**item, "tag": name, "priority": priority, "unit": unit})
    if not pooled:
        return EMPTY_COVERAGE
    return _coverage_for(pooled, candidates)


def coverage_to_dict(coverage: ConceptCoverage) -> dict[str, Any]:
    """Für die Persistenz: nur der Extrakt, nie das companyfacts-Rohdokument
    (mehrere MB, sprengt das 1-MiB-Dokumentlimit von Firestore).

    Tupel werden zu Listen: Firestore kennt keine Tupel und gäbe sie beim Lesen
    ohnehin als Listen zurück. Die Umwandlung hier explizit zu machen hält
    Schreib- und Leseform gleich, statt sie erst im Speicher auseinanderlaufen
    zu lassen."""
    payload = asdict(coverage)
    payload["years"] = list(coverage.years)
    payload["values"] = list(coverage.values)
    return payload


def coverage_from_dict(payload: dict[str, Any]) -> ConceptCoverage:
    """Gegenstück zu `coverage_to_dict`."""
    return ConceptCoverage(
        concept=payload.get("concept"),
        unit=payload.get("unit"),
        years=tuple(payload.get("years") or ()),
        values=tuple(float(v) for v in payload.get("values") or ()),
        contiguous=int(payload.get("contiguous", 0)),
        restatements=int(payload.get("restatements", 0)),
        naive_fy_count=int(payload.get("naive_fy_count", 0)),
    )


def record_to_dict(record: AnnualSeriesRecord) -> dict[str, Any]:
    return {
        "schema": EXTRACTION_SCHEMA,
        "cik": record.cik,
        "entity": record.entity,
        "reason": record.reason,
        "concepts": {k: coverage_to_dict(v) for k, v in record.concepts.items()},
    }


def record_from_dict(payload: dict[str, Any]) -> AnnualSeriesRecord:
    return AnnualSeriesRecord(
        cik=str(payload.get("cik", "")),
        entity=str(payload.get("entity", "")),
        concepts={
            k: coverage_from_dict(v) for k, v in (payload.get("concepts") or {}).items()
        },
        reason=payload.get("reason"),
    )
