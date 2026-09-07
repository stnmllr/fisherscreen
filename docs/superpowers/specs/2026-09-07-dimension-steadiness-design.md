# Design: vierte Tool-A-Dimension „Stetigkeit"

**Datum:** 2026-09-07, überarbeitet 2026-09-07 (Entscheidungsrunde nach PR #60)
**Status:** Spec, keine Implementierung.

**Entschieden** (in dieser Fassung eingearbeitet): Kennzahlen S1/S2/S3 in ihrer heutigen Form
(§5 — Anzahl Rückgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge; Eigenkapital
entfällt); die Gate-Regel „alle bewertbaren Merit-Achsen, mindestens drei" samt der Auflage,
dass „bewertbar" an einem eigenen Feld hängt (§8, §8.1); die neue Collection
`dev_edgar_annual_series` mit Schlüssel CIK, TTL-Jitter und Negativ-Caching (§9.1.1).

**Offen bis zum Kalibrierungslauf** (§9.2): B1 die Zusammenführung `mean` gegen `min`;
B2 die Schwellen für S2 und S3; B3 ob NVDA und TER fallen dürfen. Für diese drei liefert der
Kalibrierungsbericht Zahlen, **keine Empfehlung**.
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

**Drei Reihen, nicht vier.** Eigenkapital ist entfallen, seit S3 die Nettomarge misst
(Abschnitt 5). Das kostet nichts und spart die größte Namenslücke der Messung:
`StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` betraf 86 Titel.

Ohne die jeweils hinteren Einträge fällt die Abdeckung von 85,1 % auf **59,7 %**. Die Differenz
ist eine Namens-, keine Datenlücke; drei der verbliebenen Tags erklären sie fast vollständig
(`ProfitLoss` 70 Titel, `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…` 59,
`RevenueFromContractWithCustomerIncludingAssessedTax` 21).

> Die Prozentzahlen dieses Abschnitts sind über **vier** Reihen gemessen (Stand der Probe vom
> 2026-09-07) und sind damit eine **Untergrenze** für die Abdeckung über drei: wer alle vier
> hatte, hat auch die drei. Die genaue Drei-Reihen-Quote liefert der Kalibrierungslauf.

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
| S1 | Rückgangsjahre | **Anzahl** der Jahre mit fallendem Umsatz im Fenster (`down_years`) |
| S2 | Margeneinbruch | größter Rückgang der operativen Marge (`operating_income / revenue`) **vom bisherigen Hoch** im Fenster, in Prozentpunkten |
| S3 | Schlechteste Nettomarge | `min(net_income_t / revenue_t)` über das Fenster |

**Zu S1 — gezählt, nicht als Quote gebändert.** `consistency_ratio()` in
`app/screener/growth_consistency.py:11` bleibt die Quelle der Zählung (`down_years` aus
`classify_revenue_trajectory`), aber die Bänder hängen an der **Anzahl**, nicht am Verhältnis.
Grund: bei neun Übergängen ist die Quote quantisiert — 1,00 / 0,89 / 0,78 / 0,67 —, „≥ 0,90 für
die 5" heißt real „null Rückgangsjahre", und ein einziges schlechtes Jahr fällt knapp auf die 4.
Die Anzahl sagt dasselbe, nur ohne die Scheingenauigkeit. Für ein Fenster von 7–9 Jahren gilt
**dieselbe Anzahl-Tabelle**, es wird nicht auf die Fensterlänge umgerechnet: drei schlechte
Jahre sind drei schlechte Jahre.

**Zu S2 — Rückgang vom Hoch, nicht Standardabweichung.** Eine stetig steigende Marge hat eine
hohe Standardabweichung und ist doch das Gegenteil von zyklisch; die Streuung bestraft hier
genau das Falsche. Gesucht ist der Einbruch im Tal, und den misst der maximale Rückgang vom
bisherigen Hoch (`max(peak_bis_t − marge_t)` über das Fenster, Prozentpunkte). Die Kennzahl ist
richtungsabhängig — eine Marge, die nur steigt, hat einen Rückgang von 0.

**Zu S3 — Nettomarge statt Eigenkapitalrendite.** Die ursprüngliche Fassung nahm die
schlechteste Eigenkapitalrendite. Das bricht an den eigenen Abnahmefällen: FICO und TDG haben
durch jahrelange Rückkäufe **negatives Eigenkapital**, wären also nach der „`equity ≤ 0`
überspringen"-Regel neutral gestellt worden — obwohl §10.2 verlangt, dass genau sie oben
bleiben. Die Nettomarge ist gegen die Kapitalstruktur unempfindlich und misst dieselbe Frage:
trägt das Geschäft im schlechtesten Jahr des Fensters noch.

**Folge für die Datengrundlage:** die Eigenkapital-Reihe entfällt. Gebraucht werden nur noch
**drei** Reihen (Umsatz, operatives Ergebnis, Nettogewinn) — §4.1 ist entsprechend gekürzt. Das
ist nebenbei die größte Namenslücke der Messung: `StockholdersEquityIncludingPortionAttributable\
ToNoncontrollingInterest` betraf 86 Titel und wird nicht mehr gebraucht. Die Regel
„`equity ≤ 0` überspringen" entfällt ersatzlos.

Ein Jahr mit `revenue ≤ 0` ist für S2 und S3 nicht bestimmt und wird übersprungen; bleibt das
Fenster darunter unter der Mindestlänge, ist die Dimension neutral (Abschnitt 7).

### 5.1 Absolute Bänder, ausdrücklich keine sektor-relativen Perzentile

> **ENTSCHEIDUNG (1) — bestätigen vor dem Bau.**

Die drei bestehenden Achsen scoren sektor-relativ. Stetigkeit tut das **nicht**. Grund: ein
sektor-relatives Perzentil würde die am wenigsten schwankende Goldmine hoch bewerten, obwohl
alle Goldminen schwanken — die relative Statistik verschluckt genau das Urteil, das die
Dimension fällen soll. Dasselbe Muster hat im Repo schon dreimal dieselbe Antwort erzwungen
(Tier-B Punkt 2: absoluter Below-Median-Gap statt skalen-relativer Norm).

**S1 ist entschieden** — die Anzahl ist keine Verteilungsfrage:

| Score | S1 Rückgangsjahre im Fenster |
|---|---|
| 5 | 0 |
| 4 | 1 |
| 3 | 2 |
| 2 | 3 |
| 1 | mehr als 3 |

**S2 und S3 sind VORSCHLAG und werden durch die Kalibrierung ersetzt** (Abschnitt 9.2). Die
Zahlen unten stehen nur da, damit die Größenordnung nicht offen bleibt — sie sind nicht
gemessen und dürfen nicht implementiert werden, bevor die Verteilung vorliegt:

| Score | S2 Margeneinbruch vom Hoch (pp) — Vorschlag | S3 schlechteste Nettomarge — Vorschlag |
|---|---|---|
| 5 | ≤ 2 | ≥ 10 % |
| 4 | ≤ 5 | ≥ 5 % |
| 3 | ≤ 10 | ≥ 0 % |
| 2 | ≤ 20 | ≥ −10 % |
| 1 | sonst | sonst |

**Zusammenführung offen (B1):** die Spec sah `mean(S1, S2, S3)` vor. Ob das trägt, entscheidet
die Kalibrierung — `mean` lässt eine Kombination 5/4/3 mit genau 4,0 durch, was für eine
Dimension, die Zykliker aussortieren soll, weich sein könnte. Gegenkandidat ist
`min(S1, S2, S3)`. Der Kalibrierungsbericht stellt beide nebeneinander; die Entscheidung fällt
danach, nicht hier. Skala 0–5 wie die übrigen Achsen.

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

> **ENTSCHIEDEN am 2026-09-07: der Hauptvorschlag wird gebaut.** Die Alternative bleibt als
> dokumentierter Rückfall stehen und wird **nicht** implementiert.

Heute: `MERIT_DIMENSIONS` = growth, profitability, resilience; Crosshit = ≥3 von 3 Achsen ≥4,0
(`app/screener/dimensions.py:30`, `crosshits_min_dimensions=3`).

Stetigkeit einfach als vierte Merit-Achse einzuhängen geht in beiden naheliegenden Varianten
schief:

- `min_dimensions = 3` von 4 → **lockerer** als heute. Eine Goldmine dürfte an der Stetigkeit
  scheitern und bliebe Crosshit. Das Gegenteil des Ziels.
- `min_dimensions = 4` von 4 → jeder Titel mit neutraler Stetigkeit fällt heraus. Das sind
  32,6 % des Universums, darunter alle europäischen. Bestrafung durch die Hintertür, im
  Widerspruch zu Abschnitt 7.

**Gebaut wird: Crosshit = ≥4,0 in allen BEWERTBAREN Merit-Achsen, mindestens jedoch in drei.**
Stetigkeit zählt mit, wenn sie bestimmt ist, und wird übersprungen, wenn sie es nicht ist. Damit
gilt für einen Titel mit Historie eine strengere Hürde als heute, für einen ohne Historie
exakt die heutige. Das ist „neutral = weder Vor- noch Nachteil", präzise ausgedrückt.

### 8.1 Auflage: „bewertbar" hängt an einem Feld, nie am Score-Wert

`steadiness == 3.0` darf **niemals** als „nicht bewertbar" gelesen werden. Eine echte Stetigkeit
von 3,0 ist ein normales Messergebnis (etwa 2 Rückgangsjahre, mittlerer Margeneinbruch, magere
Nettomarge) und **muss am Gate scheitern** — sie liegt unter 4,0. Der Sentinel-3 der
Nicht-Bewertbaren sieht identisch aus und muss übersprungen werden. Wer die beiden über den Wert
unterscheidet, verwechselt sie zwangsläufig, und zwar zugunsten des zyklischen Titels.

Deshalb trägt der Record ein **eigenes Feld** — `steadiness_reason` mit den drei Neutral-Gründen
aus Abschnitt 7 (`no_sec_registrant`, `series_too_short`, `no_concept`) und `None`, wenn die
Achse bewertet wurde. Das Gate liest ausschließlich dieses Feld. Dieselbe Trennung gilt für die
Report-Spalte: `n/a` kommt aus dem Grund, nicht aus dem Wert.

Alternative, falls das zu viel Mechanik ist: Stetigkeit wird **nur angezeigt und ins Ranking
gezogen** (Sortierschlüssel vor dem Ø-Score), das Gate bleibt auf den drei bestehenden Achsen.
Schwächer, aber ohne jede Umstellung des Gates — und mit der Preisnehmer-Spalte zusammen
vermutlich schon ausreichend. **Nicht gewählt** — sie steht hier als Rückfall für den Fall, dass
der Regressionslauf (Abschnitt 10) zu viele richtige Titel verliert, und wird sonst nicht
gebaut.

`crosshits_score_threshold` (4,0) bleibt in beiden Fällen unverändert.

## 9. Implementierung

### 9.1 Bausteine

| Neu/geändert | Was |
|---|---|
| `app/services/edgar_annual_series_client.py` | Thin Wrapper um companyfacts. Die Extraktion aus `scripts/probe_edgar_history.py` wandert hierher — sie ist gemessen und getestet, kein Neubau. |
| `app/services/cached_edgar_annual_series.py` | Firestore-Cache, siehe 9.1.1. **Nur den Extrakt speichern** — companyfacts-Rohdokumente sind mehrere MB und sprengen das 1-MiB-Dokumentlimit. |
| `app/screener/steadiness.py` | S1/S2/S3, Bänder, Fenster-Deckel, Neutral-Grund. Reine Funktionen auf Reihen, keine I/O. |
| `app/screener/deterministic_scorer.py` | Achse `steadiness` + Feld `steadiness_reason` (Abschnitt 8.1). |
| `app/screener/dimensions.py` | `MERIT_DIMENSIONS` + Gate-Regel aus Abschnitt 8. |
| `app/output/crosshits_generator.py` | Spalte **Stetigkeit** + Legende. |
| `scripts/backfill_edgar_annual_series.py` | Cache vorwärmen (Vorbild: `scripts/backfill_revenue_series.py`). |
| `app/config.py` | `edgar_annual_series_collection`, `edgar_annual_series_ttl_days`, `edgar_annual_series_negative_ttl_days` — analog `revenue_series_*`. |

#### 9.1.1 Architektur-Entscheidung: neue Collection `dev_edgar_annual_series`

CLAUDE.md verlangt für jede weitere Collection eine ausdrückliche Entscheidung. Hier ist sie.

- **Name `dev_edgar_annual_series`**, nicht `dev_edgar_facts`. „facts" benennt das
  companyfacts-Rohdokument — genau das, was hier ausdrücklich **nicht** gespeichert wird — und
  ist von `dev_edgar_cache` (Restatement-/Going-Concern-Signale) kaum zu unterscheiden. Der Name
  sagt jetzt, was drinsteht: Jahresreihen.
- **Schlüssel: CIK**, nicht Ticker. GOOG und GOOGL teilen sich einen Emittenten und damit ein
  Dokument; über den Ticker geschlüsselt würde dieselbe Reihe zweimal geladen und zweimal
  gespeichert.
- **Inhalt:** nur der Extrakt — je Konzept die Jahre und Werte, plus die Schema-Version der
  Extraktion. Ändert sich die Extraktion, wird der Eintrag verworfen statt still warmgehalten
  (dasselbe Muster wie `EXTRACT_SCHEMA` in der Messprobe).
- **TTL 400 Tage mit Jitter ±60 Tage.** Ohne Jitter läuft alles, was der Backfill an einem Tag
  geschrieben hat, auch an einem Tag ab — und ein einzelner Monatslauf trüge die vollen ~7
  Minuten Nachladen auf einmal, direkt gegen die Deadline aus 9.3. Der Jitter verteilt das über
  ein Vierteljahr.
- **Negativergebnisse werden gecacht**, mit kurzer eigener TTL (30–90 Tage, Vorbild
  `adr_negative_cache_ttl_days`): kein CIK auflösbar, 404 auf companyfacts, kein Konzept
  getroffen. Ohne das laden rund 90 Titel jeden Monat ihr mehrere MB großes Dokument, um erneut
  festzustellen, dass nichts drinsteht. Die kurze TTL ist gewollt asymmetrisch — ein
  Negativergebnis ist eine Aussage über heute, nicht über das Unternehmen.

Die Tabelle „Firestore Collections" in CLAUDE.md wird im selben Zug auf den Ist-Stand gebracht;
sie nannte vier Collections, im Code sind es sechs, und der Stack-Abschnitt sprach von zweien.

### 9.2 Bandkalibrierung vor dem Bau

Die Bänder für S2 und S3 in 5.1 sind ein Vorschlag, keine Messung. S1 ist entschieden (Anzahl
Rückgangsjahre) und nicht kalibrierungspflichtig.

`scripts/calibrate_steadiness_bands.py` (Vorbild `scripts/calibrate_anchor_bands.py`) liest
ausschließlich `cache/edgar_history_coverage.json` — kein Netz, kein Firestore — und liefert:

- die Verteilung von S1, S2 und S3 über die bewertbaren Titel;
- die Teilwerte **und die Jahresreihen im Klartext** für HL, NEM, MU, TPL, MEDP, FAST, FICO,
  NVDA (Abnahme auf Primärevidenz, §10.3);
- `mean(S1,S2,S3)` gegen `min(S1,S2,S3)` nebeneinander, mit der Zahl der Titel ≥ 4,0 je
  Variante (offener Punkt B1).

**Zielkorridor für die Schwellen: 50–65 % der bewertbaren Titel mit Stetigkeit ≥ 4,0.** Die
Dimension soll Zykliker aussortieren, nicht die Hälfte der guten Titel gleich mit. Harte
Nebenbedingungen: HL, NEM und MU müssen unter 4,0 liegen; MEDP, FAST und FICO darüber. TPL
(8 Jahre, Deckel 4) ist der Prüfstein und darf in beide Richtungen ausgehen.

Die Bänder werden an dieser Verteilung festgezogen, nicht an einer Intuition, und die Spec wird
danach mit den gemessenen Werten aktualisiert.

### 9.3 Laufzeit — der operative Engpass

**Das ist die Stelle, an der diese Dimension den Monatslauf gefährden kann.**

Der Monatslauf scort heute kalt in ~23 min. Die Messung von 610 Titeln über companyfacts
dauerte **6,8 min**. Ein kalter Lauf käme damit auf ~30 min = ~1800 s — und die harte
Scheduler-Deadline liegt bei 1800 s; ein Überschreiten löst einen Scheduler-Retry und damit
einen Doppellauf aus (bekanntes Restrisiko, siehe `punkt3-revenue-growth-floor-state`).

Auflagen daraus, nicht verhandelbar:

1. Der Cache wird **vor** der Aktivierung per Backfill-Skript vorgewärmt, nie im Monatslauf
   erstmalig gefüllt.
2. TTL 400 Tage, damit ein Monatslauf im Regelfall gar keine companyfacts-Requests macht —
   **mit Jitter ±60 Tage** (9.1.1). Ein Backfill schreibt alle Einträge am selben Tag; ohne
   Jitter laufen sie auch am selben Tag ab, und dann trägt genau ein Monatslauf die vollen
   ~7 Minuten Nachladen. Der Jitter verteilt die Erneuerung über ein Vierteljahr.
3. Vor dem Scharfschalten ein kalter Dry-Run mit Zeitmessung. Bleibt die Gesamtlaufzeit über
   ~25 min, ist der synchrone Endpunkt der falsche Ort — dann zuerst das offene Ticket
   `2026-06-03-toolA-run-as-cloud-run-job.md` ziehen.

## 10. Testplan

### 10.1 Unit (kein Netz)

- **Extraktion:** die Tests aus `tests/scripts/test_probe_edgar_history.py` wandern mit dem Code
  nach `tests/services/` — inklusive der drei Regressionsfälle (Vergleichsjahre, ASC-606-Wechsel,
  Quartalsstichtag).
- **S1/S2/S3:** Bandgrenzen je einmal von beiden Seiten; Fenster < 7 Jahre → neutral;
  Fenster 7–9 Jahre → Score ≤ 4 auch bei perfekten Eingaben. Für S2 eigens: eine **stetig
  steigende** Marge hat einen Rückgang von 0 und damit die 5 — die Kennzahl ist
  richtungsabhängig, und eine Streuungskennzahl wäre hier zum gegenteiligen Urteil gekommen.
- **Gate — die beiden Dreien:** ein Titel mit **echter** Stetigkeit 3,0 und drei Achsen ≥4,0 ist
  **kein** Crosshit; ein Titel mit **Sentinel**-3 (`steadiness_reason` gesetzt) und drei Achsen
  ≥4,0 **bleibt** einer. Beide tragen denselben Zahlenwert; wird das Gate über den Wert statt
  über den Grund entschieden, fallen sie zusammen — und zwar zugunsten des zyklischen Titels.
  Dieser Test ist der Wächter über Abschnitt 8.1.
- **Report:** neutrale Titel zeigen `n/a` mit Grund-Marker, nie eine 3.

### 10.2 Regression über die 24 Septembertitel

Der Abnahmefall. Erwartung, an der die Dimension gemessen wird:

| Erwartung | Titel |
|---|---|
| **müssen fallen** | HL, NEM, MU — bewertbar und zyklisch |
| **müssen oben bleiben** | MEDP (11 J.), FAST (19 J.), FICO (18 J.) |
| bleiben neutral, unverändert in der Liste, aber als Preisnehmer gekennzeichnet | EDV.L, ANTO.L (kein SEC), RGLD (5 J.), SNDK (4 J.) |
| Prüfstein | TPL (8 J., gedeckelt auf 4) — soll an der Schwankung scheitern |
| **dürfen fallen** (vorläufig, siehe B3) | NVDA, TER — Halbleiter-Zykliker; NVDA hatte FY2020 einen Umsatzrückgang und starke Margenschwankung. Fallen sie, ist das **kein Fehler**. Ob die Erwartung so bleibt, wird am Kalibrierungsergebnis entschieden. |

Wie bei den Ticker-Listen in `tests/output/test_crosshits_generator.py` hängt der Test an den
**Listen**, nicht an einer Anzahl: eine spätere Erweiterung darf ihn nicht rot färben.

**Merksatz zu S1, gegen die Messdaten geprüft:** Newmont hat im Fenster 2016–2025 nur **drei**
Umsatz-Rückgangsjahre (2018, 2022, 2023) — das Fenster liegt fast vollständig in einem
Goldbullenmarkt, in dem der Umsatz von 6,7 auf 22,7 Mrd steigt. S1 allein stellt einen
Preisnehmer also nicht: NEM fällt über S2 und S3, nicht über die Wachstumsstetigkeit. Genau
deshalb hängt die Kalibrierung (B2) an S2 und S3.

> Randnotiz zur Zahl: nach der **neuen** S1-Tabelle sind drei Rückgangsjahre Score **2**, nicht
> 3 — die 3 stammte aus den alten Quotenbändern (6/9 = 0,67 → „≥ 0,60"). Die Aussage bleibt
> dieselbe, der Punkt wird sogar etwas stärker: die Umstellung auf Anzahl verschärft S1 hier um
> eine Stufe. Belastbar wird beides erst mit der Kalibrierung, weil das Fenster dort auf zehn
> Jahre begrenzt wird und NEM 14 Jahre Historie hat.

### 10.3 Abnahme auf Primärevidenz, nicht auf Aggregat

Ein Zähltest beweist nicht, dass der Mechanismus greift. Für **HL, NEM, MU, TPL, MEDP, FAST,
FICO und NVDA** sind die drei Teilwerte **im Klartext** zu lesen — Rückgangsjahre,
Margeneinbruch vom Hoch, schlechteste Nettomarge — samt der zugrundeliegenden Jahresreihen.
Diese acht stehen schon im Kalibrierungsbericht (§9.2), damit die Bänder nicht an einer
Verteilung festgezogen werden, deren Einzelfälle niemand gesehen hat.

Fällt einer aus dem **falschen Grund** — an einer Datenlücke statt an der Schwankung, an einem
verkürzten Fenster statt an der Zyklik —, ist die Dimension nicht abgenommen, auch wenn die
Aggregatzahl stimmt.

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
