# Design: vierte Tool-A-Dimension „Stetigkeit"

**Datum:** 2026-09-07
**Status:** Spec, keine Implementierung. Zwei Punkte sind vor dem Bau zu entscheiden
(Abschnitt 5 und 8), einer ist vor dem Aktivieren zu messen (Abschnitt 9).
**Vorlauf:** `docs/superpowers/diagnostic-reports/2026-09-07-edgar-history-coverage.md`
**Branch:** `feature/tool-a-cyclicals`

---

## 1. Problem

Tool A bewertet growth, profitability und resilience auf Momentaufnahmen: ein Jahr
Umsatzwachstum, die aktuelle operative Marge, die aktuelle Eigenkapitalrendite, die aktuelle
Verschuldung. Der einzige Zyklik-Dämpfer ist `consistency_cap()` in
`app/screener/growth_consistency.py:24`, und der rechnet über die vier Geschäftsjahre, die
yfinance liefert — drei Übergänge. In einem Rohstoffboom zeigen alle drei nach oben, der Cap
steht auf 5, und der Dämpfer feuert genau dort nicht, wo er gebraucht wird.

Ergebnis im Septemberlauf: acht der 24 Crosshits sind Preisnehmer — Gold (EDV.L, HL, NEM,
RGLD), Kupfer (ANTO.L), Landbesitz (TPL), Speicher (MU, SNDK). Aus Fisher-Sicht sind das keine
Kandidaten: Punkt 1 und 2 fragen nach Produkten mit Wachstumspotenzial und einer Führung, die
neue Ertragsquellen erschließt, nicht nach einem Zykluskamm.

## 2. Ziel

Eine vierte Dimension **Stetigkeit**, die über zehn Jahre misst, ob ein Geschäft durch einen
Zyklus trägt. Sie ergänzt die drei bestehenden Achsen, ersetzt keine, und **schließt keinen
Titel aus** — ein Titel ohne Datengrundlage wird neutral gestellt und gekennzeichnet, nicht
bestraft.

## 3. Nicht-Ziele

- Kein Composite-Score über alle Dimensionen (V3-Entscheidung, unverändert).
- Keine EU-Quellenschicht. ESAP kommt September 2027; bis dahin bleiben die 233 Nicht-SEC-Titel
  (27,6 % des gescorten Universums) ohne Stetigkeit. Das ist eine bekannte Asymmetrie, kein
  offener Punkt.
- Keine 20-F-/`ifrs-full`-Auswertung. Wäre eine eigene Konzeptliste, eigener Aufwand, eigene
  Entscheidung.
- Kein Ersatz für die Preisnehmer-Kennzeichnung. Die Messung zeigt, dass fünf der acht
  gemeldeten Fälle von dieser Dimension **nicht erreicht** werden (Abschnitt 10).

## 4. Datengrundlage

SEC XBRL companyfacts, `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`.
Ein Request je Titel, Formulare `10-K` und `10-K/A`, Taxonomie `us-gaap`.

**Gemessen (2026-09-07, 610 US-Titel, 0 Fehler):** 519 Titel (85,1 %) tragen alle vier
benötigten Reihen über ≥10 zusammenhängende Jahre; 568 (93,1 %) über ≥7.

### 4.1 Konzeptliste — die erweiterte, nicht die naheliegende

| Größe | Kandidaten, in dieser Rangfolge |
|---|---|
| Umsatz | `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`, `RevenueFromContractWithCustomerIncludingAssessedTax`, `SalesRevenueGoodsNet`, `SalesRevenueServicesNet` |
| Operatives Ergebnis | `OperatingIncomeLoss`, `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest`, `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` |
| Nettogewinn | `NetIncomeLoss`, `ProfitLoss`, `NetIncomeLossAvailableToCommonStockholdersBasic`, `IncomeLossFromContinuingOperations` |
| Eigenkapital | `StockholdersEquity`, `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` |

Ohne die jeweils hinteren Einträge fällt die Abdeckung von 85,1 % auf **59,7 %**. Die Differenz
ist eine Namens-, keine Datenlücke; vier Tags erklären sie fast vollständig
(`StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` 86 Titel, `ProfitLoss`
70, `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…` 59,
`RevenueFromContractWithCustomerIncludingAssessedTax` 21).

> **Diese Reihen sind für die FORM einer Zeitreihe bestimmt, nicht für ihr NIVEAU.**
> `Revenues` und `RevenueFromContractWithCustomerExcludingAssessedTax` dürfen in einer
> Stetigkeitsmessung zusammenlaufen, weil dort Schwankung und Vorzeichen der Veränderung zählen.
> Für eine **Bewertungskennzahl** — Kursziel, Multiple, EV-Vergleich — dürfen sie das nicht: dort
> ist der absolute Wert die Aussage, und ein Definitionswechsel mitten in der Reihe verfälscht
> ihn. Wer diese Reihen später für eine Bewertung wiederverwenden will, braucht eine eigene,
> definitionsreine Extraktion.

### 4.2 Drei Fallen, die in der Probe bereits aufgetreten sind

Alle drei sind in `scripts/probe_edgar_history.py` gelöst und durch Tests gepinnt. Die
Implementierung **übernimmt diese Extraktion, sie schreibt sie nicht neu**.

1. **`fy` ist das Jahr des Filings, nicht der Periode.** Ein FY2025-10-K meldet FY2023 und
   FY2024 als Vergleichsjahre ebenfalls mit `fy=2025, fp=FY`. Nach `fy` zu deduplizieren zieht
   drei Jahre zu einem zusammen. Geschlüsselt wird nach der Periode (`(start, end)` bzw. `end`),
   pro Bucket gewinnt das späteste `filed`.
2. **ASC 606.** Die meisten US-Filer wechselten um 2018 von `Revenues` auf
   `RevenueFromContractWithCustomerExcludingAssessedTax`. Wer den ersten Tag nimmt, der Daten
   trägt, misst bei Agilent 9 Jahre statt 19. Kandidaten werden zu **einer** Reihe
   zusammengeführt; bei Überschneidung gewinnt der früher gelistete Tag.
3. **Quartals-Bilanzstichtage in 10-Ks.** Akamais `2022-03-31` trägt das Geschäftsjahr-Etikett
   2021 und verdrängte dort den echten Jahresabschluss — aus 20 Jahren wurden 4. Die Reihe wird
   auf den Jahresabschluss-Jahrestag verankert (±45 Tage).

## 5. Kennzahlen

Fenster: die jüngsten bis zu zehn **zusammenhängenden** Geschäftsjahre. Eine Lücke beendet das
Fenster; zehn Jahre mit Loch in der Mitte sind keine zehn Jahre.

| # | Kennzahl | Berechnung |
|---|---|---|
| S1 | Wachstumsstetigkeit | `consistency_ratio(revenues)` — `(Übergänge − Rückgangsjahre) / Übergänge` |
| S2 | Margenschwankung | Standardabweichung der jährlichen operativen Marge (`operating_income / revenue`) in **Prozentpunkten** |
| S3 | Schlechteste Eigenkapitalrendite | `min(net_income_t / equity_t)` über das Fenster |

**S1 existiert bereits.** `consistency_ratio()` in `app/screener/growth_consistency.py:11` nimmt
eine Umsatzreihe entgegen und ist quellenblind — sie sieht heute nur vier Jahre. Es ist keine
neue Kennzahl nötig, nur eine längere Reihe.

**Zu S3:** Eigenkapital ist eine Bestandsgröße zum Stichtag; gerechnet wird mit dem
Jahresendwert, nicht mit einem Durchschnitt. Für eine Stetigkeitsaussage genügt das, und es hält
die Reihe bei genau einem Wert pro Jahr. Jahre mit `equity ≤ 0` liefern keine sinnvolle Rendite
und werden übersprungen; besteht das Fenster danach aus weniger als der Mindestzahl Jahre, ist
S3 nicht bestimmt und die Dimension neutral (Abschnitt 7).

### 5.1 Absolute Bänder, ausdrücklich keine sektor-relativen Perzentile

> **ENTSCHEIDUNG (1) — bestätigen vor dem Bau.**

Die drei bestehenden Achsen scoren sektor-relativ. Stetigkeit tut das **nicht**. Grund: ein
sektor-relatives Perzentil würde die am wenigsten schwankende Goldmine hoch bewerten, obwohl
alle Goldminen schwanken — die relative Statistik verschluckt genau das Urteil, das die
Dimension fällen soll. Dasselbe Muster hat im Repo schon dreimal dieselbe Antwort erzwungen
(Tier-B Punkt 2: absoluter Below-Median-Gap statt skalen-relativer Norm).

Vorschlag, **kalibrierungspflichtig** (Abschnitt 9):

| Score | S1 Wachstumsstetigkeit | S2 Margenschwankung (pp) | S3 schlechteste EK-Rendite |
|---|---|---|---|
| 5 | ≥ 0,90 | ≤ 3 | ≥ 10 % |
| 4 | ≥ 0,75 | ≤ 6 | ≥ 5 % |
| 3 | ≥ 0,60 | ≤ 10 | ≥ 0 % |
| 2 | ≥ 0,45 | ≤ 15 | ≥ −10 % |
| 1 | sonst | sonst | sonst |

`steadiness = round(mean(S1, S2, S3), 2)`, Skala 0–5 wie die übrigen Achsen.

## 6. Fensterlänge: abgestuft ab sieben Jahren, mit Deckel

Eine harte Zehn-Jahres-Hürde vergrößert den Neutral-Topf ohne Not. Von den 18 SEC-Titeln der
Septemberliste erreichen 13 zehn Jahre, aber **16** erreichen sieben. Die drei zusätzlichen sind
TPL (8), PLTR (8) und ABNB (7).

| zusammenhängende Jahre | Verhalten |
|---|---|
| ≥ 10 | bewertet, Höchstwert 5 |
| 7–9 | bewertet, **Höchstwert 4** |
| < 7 | nicht bewertet → neutral (Abschnitt 7) |

Der Deckel ist dasselbe Muster wie `consistency_cap()`: sieben gute Jahre ziehen nicht mit zwei
sauber überstandenen Zyklen gleich. TPL ist der Prüfstein — acht Jahre Öl-Royalties reichen, um
die Schwankung zu sehen, und genau die soll die Dimension finden.

Nur RGLD (5) und SNDK (4) bleiben damit neutral, und das zu Recht: eine Reihe, die kürzer ist
als der Zyklus, kann über den Zyklus nichts sagen.

## 7. Titel ohne Datengrundlage: neutral, aber sichtbar

Neutral heißt Sentinel **3** — dieselbe Konvention wie für `management`/`innovation` und für ein
fehlendes Perzentil (`app/screener/deterministic_scorer.py`). Bei einem Crosshit-Schwellwert von
4,0 kann eine 3 eine Achse nie qualifizieren: der Titel wird weder gehoben noch gesenkt.

**Bedingung, unter der die Dimension überhaupt Sinn ergibt: „neutral" darf nicht wie
„unauffällig" aussehen.** Ohne sichtbare Kennzeichnung verschiebt die Dimension das Problem,
statt es zu lösen — und zwar unsichtbar. Deshalb:

- Eigene Spalte **Stetigkeit** in der Crosshits-Tabelle. Ein bewerteter Titel zeigt seinen
  Score, ein neutraler zeigt **`n/a`** — nicht die 3.
- Ein Marker unterscheidet die drei Gründe: `∅` = kein SEC-Registrant, `↧` = Reihe zu kurz
  (< 7 Jahre), `⊘` = kein Konzept getroffen. Der Marker steht neben dem `n/a`, nicht neben dem
  Ticker: die vorhandenen Ticker-Marker (`⌖ ⚠ ~`) haben eine andere Bedeutungsebene und dürfen
  nicht verwässert werden.
- Die Legende unter der Tabelle nennt beide Fälle im Klartext.

Der Bericht muss außerdem die Grundgesamtheit nennen: bei der abgestuften Regel bekommen
**568 von 843** gescorten Titeln (67,4 %) eine echte Stetigkeit, 275 sind neutral. Eine Spalte,
die für ein Drittel des Universums `n/a` zeigt, muss diesen Anteil ausweisen, sonst liest man
sie falsch.

## 8. Gewichtung und Crosshit-Schwellwert

> **ENTSCHEIDUNG (2) — die eigentliche Weiche. Vor dem Bau zu treffen.**

Heute: `MERIT_DIMENSIONS` = growth, profitability, resilience; Crosshit = ≥3 von 3 Achsen ≥4,0
(`app/screener/dimensions.py:30`, `crosshits_min_dimensions=3`).

Stetigkeit einfach als vierte Merit-Achse einzuhängen geht in beiden naheliegenden Varianten
schief:

- `min_dimensions = 3` von 4 → **lockerer** als heute. Eine Goldmine dürfte an der Stetigkeit
  scheitern und bliebe Crosshit. Das Gegenteil des Ziels.
- `min_dimensions = 4` von 4 → jeder Titel mit neutraler Stetigkeit fällt heraus. Das sind
  32,6 % des Universums, darunter alle europäischen. Bestrafung durch die Hintertür, im
  Widerspruch zu Abschnitt 7.

**Vorschlag: Crosshit = ≥4,0 in allen BEWERTBAREN Merit-Achsen, mindestens jedoch in drei.**
Stetigkeit zählt mit, wenn sie bestimmt ist, und wird übersprungen, wenn sie es nicht ist. Damit
gilt für einen Titel mit Historie eine strengere Hürde als heute, für einen ohne Historie
exakt die heutige. Das ist „neutral = weder Vor- noch Nachteil", präzise ausgedrückt.

Alternative, falls das zu viel Mechanik ist: Stetigkeit wird **nur angezeigt und ins Ranking
gezogen** (Sortierschlüssel vor dem Ø-Score), das Gate bleibt auf den drei bestehenden Achsen.
Schwächer, aber ohne jede Umstellung des Gates — und mit der Preisnehmer-Spalte zusammen
vermutlich schon ausreichend. Ich empfehle den Hauptvorschlag; die Alternative ist der Rückfall,
wenn der Regressionslauf (Abschnitt 10) zu viele richtige Titel verliert.

`crosshits_score_threshold` (4,0) bleibt in beiden Fällen unverändert.

## 9. Implementierung

### 9.1 Bausteine

| Neu/geändert | Was |
|---|---|
| `app/services/edgar_facts_client.py` | Thin Wrapper um companyfacts. Die Extraktion aus `scripts/probe_edgar_history.py` wandert hierher — sie ist gemessen und getestet, kein Neubau. |
| `app/services/cached_edgar_facts.py` | Firestore-Cache, TTL 400 Tage (wie `revenue_series_cache`: Jahresdaten ändern sich jährlich). **Nur den Extrakt speichern** — companyfacts-Rohdokumente sind mehrere MB und sprengen das 1-MiB-Dokumentlimit. |
| `app/screener/steadiness.py` | S1/S2/S3, Bänder, Fenster-Deckel, Neutral-Sentinel. Reine Funktionen auf Reihen, keine I/O. |
| `app/screener/deterministic_scorer.py` | Achse `steadiness` ergänzen. |
| `app/screener/dimensions.py` | `MERIT_DIMENSIONS` + Gate-Regel aus Abschnitt 8. |
| `app/output/crosshits_generator.py` | Spalte **Stetigkeit** + Legende. |
| `scripts/backfill_edgar_facts.py` | Cache vorwärmen (Vorbild: `scripts/backfill_revenue_series.py`). |
| `data/`/Firestore | Neue Collection `dev_edgar_facts`. **CLAUDE.md verlangt dafür eine ausdrückliche Architektur-Entscheidung** — sie ist mit dieser Spec zu treffen, nicht implizit. |

### 9.2 Bandkalibrierung vor dem Bau

Die Bänder in 5.1 sind ein Vorschlag, keine Messung. Vor der Implementierung ein
Kalibrierungsskript (Vorbild `scripts/calibrate_anchor_bands.py`) über die bereits gemessenen
Reihen in `cache/edgar_history_coverage.json`: Verteilung von S1/S2/S3 über die 519 bewertbaren
Titel, dazu die Werte der acht Preisnehmer und der drei Positivfälle im Klartext. Die Bänder
werden an dieser Verteilung festgezogen, nicht an einer Intuition.

### 9.3 Laufzeit — der operative Engpass

**Das ist die Stelle, an der diese Dimension den Monatslauf gefährden kann.**

Der Monatslauf scort heute kalt in ~23 min. Die Messung von 610 Titeln über companyfacts
dauerte **6,8 min**. Ein kalter Lauf käme damit auf ~30 min = ~1800 s — und die harte
Scheduler-Deadline liegt bei 1800 s; ein Überschreiten löst einen Scheduler-Retry und damit
einen Doppellauf aus (bekanntes Restrisiko, siehe `punkt3-revenue-growth-floor-state`).

Auflagen daraus, nicht verhandelbar:

1. Der Cache wird **vor** der Aktivierung per Backfill-Skript vorgewärmt, nie im Monatslauf
   erstmalig gefüllt.
2. TTL 400 Tage, damit ein Monatslauf im Regelfall gar keine companyfacts-Requests macht.
3. Vor dem Scharfschalten ein kalter Dry-Run mit Zeitmessung. Bleibt die Gesamtlaufzeit über
   ~25 min, ist der synchrone Endpunkt der falsche Ort — dann zuerst das offene Ticket
   `2026-06-03-toolA-run-as-cloud-run-job.md` ziehen.

## 10. Testplan

### 10.1 Unit (kein Netz)

- **Extraktion:** die Tests aus `tests/scripts/test_probe_edgar_history.py` wandern mit dem Code
  nach `tests/services/` — inklusive der drei Regressionsfälle (Vergleichsjahre, ASC-606-Wechsel,
  Quartalsstichtag).
- **S1/S2/S3:** Bandgrenzen je einmal von beiden Seiten; `equity ≤ 0` wird übersprungen;
  Fenster < 7 Jahre → neutral; Fenster 7–9 Jahre → Score ≤ 4 auch bei perfekten Eingaben.
- **Gate:** ein Titel mit neutraler Stetigkeit verhält sich exakt wie heute; ein Titel mit
  Stetigkeit 3,0 und drei Achsen ≥4,0 ist **kein** Crosshit mehr.
- **Report:** neutrale Titel zeigen `n/a` mit Grund-Marker, nie eine 3.

### 10.2 Regression über die 24 Septembertitel

Der Abnahmefall. Erwartung, an der die Dimension gemessen wird:

| Erwartung | Titel |
|---|---|
| fallen deutlich | HL, NEM, MU — bewertbar und zyklisch |
| bleiben oben | MEDP (11 J.), FAST (19 J.), FICO (18 J.) |
| bleiben neutral, unverändert in der Liste, aber als Preisnehmer gekennzeichnet | EDV.L, ANTO.L (kein SEC), RGLD (5 J.), SNDK (4 J.) |
| Prüfstein | TPL (8 J., gedeckelt auf 4) — soll an der Schwankung scheitern |

Wie bei den Ticker-Listen in `tests/output/test_crosshits_generator.py` hängt der Test an den
**Listen**, nicht an einer Anzahl: eine spätere Erweiterung darf ihn nicht rot färben.

### 10.3 Abnahme auf Primärevidenz, nicht auf Aggregat

Ein Zähltest beweist nicht, dass der Mechanismus greift. Vor dem Merge sind für HL, NEM, MU und
TPL die drei Teilwerte **im Klartext** zu lesen — Wachstumsstetigkeit, Margen-Standardabweichung,
schlechteste EK-Rendite, samt der zugrundeliegenden Jahresreihen. Fällt einer der vier aus dem
falschen Grund (etwa an einer Datenlücke statt an der Schwankung), ist die Dimension nicht
abgenommen, auch wenn die Zahl stimmt.

## 11. Was diese Dimension nicht leistet

Von den acht gemeldeten Preisnehmern erreicht sie **drei** (HL, NEM, MU). Fünf bleiben
unberührt: EDV.L und ANTO.L sind keine SEC-Registranten, RGLD, SNDK und TPL haben eine zu junge
XBRL-Historie — Sandisk ist ein Spin-off von 2025, Texas Pacific Land wurde 2021 aus einem Trust
in eine Corporation umgewandelt. (TPL wird bewertet, aber gedeckelt; ob es fällt, entscheidet
erst die Kalibrierung.)

Das ist kein Argument gegen die Dimension — sie adressiert die allgemeine Ursache. Es heißt nur,
dass sie den gemeldeten Fall **nicht allein löst**. Die Preisnehmer-Kennzeichnung
(`data/price_takers.json`, seit 2026-09-07 live) hängt am yfinance-Feld `industry`, ist von
EDGAR unabhängig und erreicht deshalb auch EDV.L und ANTO.L. Die beiden sind komplementär, nicht
alternativ: die eine benennt die Anfälligkeit, die andere misst, ob sie sich realisiert hat.
