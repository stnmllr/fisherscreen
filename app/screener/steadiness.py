"""Die vierte Achse: Stetigkeit über zehn Jahre.

Tool A bewertet die drei bestehenden Achsen auf Momentaufnahmen. Der einzige
Zyklik-Dämpfer davor, `consistency_cap`, rechnet über die vier Geschäftsjahre,
die yfinance liefert — drei Übergänge, im Rohstoffboom alle aufwärts. Diese
Achse sieht zehn.

Drei Teilgrößen, alle mit ABSOLUTEN Bändern und ausdrücklich nicht
sektor-relativ: ein Perzentil würde die am wenigsten schwankende Goldmine hoch
bewerten, obwohl alle Goldminen schwanken — die relative Statistik verschluckt
genau das Urteil, das diese Achse fällen soll (Spec §5.1).

  S1  Anzahl der Rückgangsjahre im Fenster
  S2  größter Einbruch der operativen Marge vom bisherigen Hoch, in
      Prozentpunkten. Bewusst kein Streuungsmaß: eine stetig STEIGENDE Marge hat
      eine hohe Standardabweichung und ist das Gegenteil von zyklisch.
  S3  schlechteste Nettomarge. Bewusst nicht die Eigenkapitalrendite: 41 der 610
      gemessenen US-Titel bilanzieren nach Rückkäufen zu wenige Jahre mit
      positivem Eigenkapital, FICO und TDG darunter — und genau die soll die
      Achse oben behalten.

`steadiness = mean(S1, S2, S3)`, gedeckelt nach Fensterlänge. `min` wurde
geprüft und verworfen: es kippt MEDP und GOOG und bringt bei den Preisnehmern
nichts (Kalibrierungsbericht 2026-09-08).

DER NEUTRAL-GRUND IST EIN EIGENES FELD, NIE EIN ZAHLENWERT. Eine echte
Stetigkeit von 3,0 ist ein normales Ergebnis und muss am Gate scheitern; der
Sentinel-3 eines nicht bewertbaren Titels muss übersprungen werden. Beide tragen
dieselbe Zahl. Wer sie am Wert unterscheidet, verwechselt sie — und zwar
zugunsten des zyklischen Titels (Spec §8.1).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from app.services.edgar_annual_series_client import AnnualSeriesRecord

# Fenster: höchstens zehn Jahre, mindestens sieben. Zwischen sieben und neun
# Jahren wird bewertet, aber gedeckelt — sieben gute Jahre ziehen nicht mit zwei
# sauber überstandenen Zyklen gleich (Spec §6).
WINDOW_MAX = 10
WINDOW_MIN = 7
CAP_SHORT_WINDOW = 4

# Sentinel für "nicht bewertbar". Identisch mit dem Wert, den auch ein echt
# gemessener mittelmäßiger Titel tragen kann — siehe Modul-Docstring.
NEUTRAL_SCORE = 3.0

# Neutral-Gründe (Spec §7). `NO_SEC_REGISTRANT` entsteht oberhalb dieser
# Funktion, bei der CIK-Auflösung.
NO_SEC_REGISTRANT = "no_sec_registrant"
SERIES_TOO_SHORT = "series_too_short"
NO_CONCEPT = "no_concept"

# Bänder, an der gemessenen Verteilung festgezogen (Kalibrierung 2026-09-08).
# S3 bei 0 ist keine Kalibrierung, sondern die Definition: ein Verlustjahr im
# Fenster schließt die 4 aus. S2 bei 12 pp liegt knapp über dem Median von
# 9,1 pp — eine 4 heißt "stetiger als der typische Titel".
S1_BANDS: tuple[tuple[int, int], ...] = ((0, 5), (1, 4), (2, 3), (3, 2))
S2_BANDS: tuple[tuple[float, int], ...] = ((5.0, 5), (12.0, 4), (24.0, 3), (48.0, 2))
S3_BANDS: tuple[tuple[float, int], ...] = ((5.0, 5), (0.0, 4), (-5.0, 3), (-15.0, 2))


@dataclass(frozen=True)
class Steadiness:
    """Ergebnis der Achse. `reason is None` heißt: bewertet."""

    score: float
    reason: str | None
    years: tuple[int, ...] = ()
    down_years: int | None = None
    margin_drawdown_pp: float | None = None
    worst_net_margin: float | None = None

    @property
    def assessable(self) -> bool:
        """Das Gate fragt DAS hier, nie den Score."""
        return self.reason is None


def _neutral(reason: str) -> Steadiness:
    return Steadiness(score=NEUTRAL_SCORE, reason=reason)


def _band(
    value: float, bands: Sequence[tuple[float, int]], *, lower_is_better: bool
) -> int:
    for threshold, score in bands:
        if (value <= threshold) if lower_is_better else (value >= threshold):
            return score
    return 1


def window_years(
    revenue: Mapping[int, float],
    operating_income: Mapping[int, float],
    net_income: Mapping[int, float],
) -> list[int]:
    """Die jüngsten bis zu zehn zusammenhängenden Jahre, die alle drei Reihen
    tragen und in denen der Umsatz positiv ist.

    Ein Jahr ohne Umsatz macht Marge und Nettomarge unbestimmbar; es fällt raus
    und beendet damit das Fenster nach hinten, statt eine Lücke zu hinterlassen.
    Eine Lücke wäre schlimmer als ein kurzes Fenster: sie würde zwei Zeiträume
    zu einem zusammenrechnen."""
    common = sorted(
        y
        for y in set(revenue) & set(operating_income) & set(net_income)
        if revenue[y] > 0
    )
    if not common:
        return []
    run = [common[-1]]
    for year in reversed(common[:-1]):
        if year != run[-1] - 1:
            break
        run.append(year)
    run.reverse()
    return run[-WINDOW_MAX:]


def down_years(values: Sequence[float]) -> int:
    """Jahre, in denen der Wert unter dem Vorjahr lag."""
    return sum(1 for previous, current in zip(values, values[1:]) if current < previous)


def margin_drawdown_pp(margins: Sequence[float]) -> float:
    """Größter Rückgang vom bisherigen Hoch, in Prozentpunkten.

    Richtungsabhängig: eine Marge, die nur steigt, hat einen Rückgang von 0."""
    peak = margins[0]
    worst = 0.0
    for margin in margins:
        peak = max(peak, margin)
        worst = max(worst, peak - margin)
    return worst


def compute_steadiness(
    revenue: Mapping[int, float],
    operating_income: Mapping[int, float],
    net_income: Mapping[int, float],
) -> Steadiness:
    """Die Achse aus drei Jahresreihen. Reine Funktion, keine I/O."""
    years = window_years(revenue, operating_income, net_income)
    if len(years) < WINDOW_MIN:
        return _neutral(SERIES_TOO_SHORT)

    revenues = [revenue[y] for y in years]
    margins = [100.0 * operating_income[y] / revenue[y] for y in years]
    net_margins = [100.0 * net_income[y] / revenue[y] for y in years]

    falls = down_years(revenues)
    # Auf die BERICHTETE Genauigkeit runden, BEVOR gebändert wird. Sonst
    # entscheidet Fliesskomma-Rauschen an der Bandkante: 40,0 - 35,000000000004
    # ergibt 5,0000000000036, faellt aus dem "<= 5"-Band und wuerde im Bericht
    # trotzdem als 5,0 stehen. Die angezeigte Genauigkeit ist die entscheidende
    # Genauigkeit -- sonst zeigt die Abnahme aus Spec 10.3 eine andere Zahl, als
    # der Score benutzt hat.
    drawdown = round(margin_drawdown_pp(margins), 1)
    worst_net = round(min(net_margins), 1)

    s1 = _band(float(falls), S1_BANDS, lower_is_better=True)
    s2 = _band(drawdown, S2_BANDS, lower_is_better=True)
    s3 = _band(worst_net, S3_BANDS, lower_is_better=False)

    cap = 5 if len(years) >= WINDOW_MAX else CAP_SHORT_WINDOW
    score = min(cap, round((s1 + s2 + s3) / 3, 2))
    return Steadiness(
        score=score,
        reason=None,
        years=tuple(years),
        down_years=falls,
        margin_drawdown_pp=drawdown,
        worst_net_margin=worst_net,
    )


def steadiness_from_record(record: AnnualSeriesRecord | None) -> Steadiness:
    """Adapter auf den Cache-Extrakt. Ein fehlender oder unbrauchbarer Datensatz
    wird neutral gestellt und behält seinen Grund."""
    if record is None or not record.usable:
        return _neutral(NO_CONCEPT)
    series = {
        key: dict(zip(cov.years, cov.values)) for key, cov in record.concepts.items()
    }
    return compute_steadiness(
        series.get("revenue", {}),
        series.get("operating_income", {}),
        series.get("net_income", {}),
    )
