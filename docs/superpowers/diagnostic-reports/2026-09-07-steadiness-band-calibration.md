# Kalibrierung der Stetigkeits-Bänder

**Lauf:** 2026-09-07 · **Skript:** `scripts/calibrate_steadiness_bands.py` (unverändert übernommen)
**Eingabe:** `cache/edgar_history_coverage.json`, Schema 2 — kein Netz, kein Firestore, $0
**Spec:** `docs/superpowers/specs/2026-09-07-dimension-steadiness-design.md` §9.2

Dieser Bericht liefert **Zahlen für die offenen Punkte B1, B2 und B3**. Er enthält bewusst
**keine Empfehlung** — die Entscheidung fällt Stephan.

---

## Kurzfassung der Befunde

1. **Bewertbar sind 567 Titel** (≥ 7 Jahre), davon **521 mit ≥ 10 Jahren**. Über drei Reihen
   gerechnet statt vier (Eigenkapital ist entfallen).
2. **Die S3-Entscheidung ist durch die Messung bestätigt, und zwar deutlicher als angenommen:**
   **41 Titel** haben zu wenige Jahre mit positivem Eigenkapital, um eine schlechteste
   EK-Rendite zu bilden — darunter **FICO** (5 Jahre mit Eigenkapital ≤ 0) und **TDG**. Beide
   stehen in der Septemberliste und sollen laut §10.2 oben bleiben; mit der EK-Rendite wären sie
   **neutral** geworden. Mit der Nettomarge sind es **0 unbestimmbare Titel**.
3. **Der Zielkorridor von 50–65 % wird von keiner der drei getesteten Bandtabellen erreicht.**
   Bester Wert über alle Kombinationen: **42 %** (alte Spec-Bänder, Std/EK-Rendite, Mittelwert).
   Unter den **entschiedenen** Kennzahlen (Margenrückgang + Nettomarge, S1 nach Anzahl) sind es
   **23 %** mit Mittelwert und **12 %** mit Minimum. Die vorgeschlagenen Schwellen sind also
   erheblich zu streng für den gewünschten Korridor.
4. **Die harten Nebenbedingungen halten** unter den entschiedenen Kennzahlen: HL, NEM und MU
   liegen bei **1,33** (weit unter 4,0), MEDP bei **4,33**, FAST und FICO bei **5,0**.
5. **B2 und B3 sind gekoppelt.** In jeder Bandkombination, die den Korridor erreicht, steigt
   **NVDA auf ≥ 4,0** und bleibt oben. Wer NVDA fallen sehen will, kommt nicht in den Korridor —
   und umgekehrt.

---

## Die entschiedenen Kennzahlen im Einzelfall

Aus dem ergänzenden Lauf unten, Bänder: S1 nach Anzahl Rückgangsjahre (entschieden),
S2 = Margenrückgang vom Hoch, S3 = schlechteste Nettomarge (beide mit den **vorgeschlagenen**
Schwellen aus §5.1, die laut B2 noch ersetzt werden).

| Ticker | J. | Rückg. | S1 | S2 | S3 | mean | min | Erwartung §10.2 |
|---|---|---|---|---|---|---|---|---|
| HL | 10 | 3 | 2 | 1 | 1 | **1,33** | 1 | muss fallen ✔ |
| NEM | 10 | 3 | 2 | 1 | 1 | **1,33** | 1 | muss fallen ✔ |
| MU | 10 | 3 | 2 | 1 | 1 | **1,33** | 1 | muss fallen ✔ |
| MEDP | 10 | 0 | 5 | 5 | 3 | **4,33** | 3 | muss oben bleiben ✔ |
| FAST | 10 | 0 | 5 | 5 | 5 | **5,0** | 5 | muss oben bleiben ✔ |
| FICO | 10 | 0 | 5 | 5 | 5 | **5,0** | 5 | muss oben bleiben ✔ |
| TPL | 8 | 2 | 2 | 1 | 5 | **2,67** | 1 | Prüfstein — fällt |
| NVDA | 10 | 1 | 4 | 1 | 5 | **3,33** | 1 | darf fallen (B3) |
| TER | 10 | 3 | 2 | 2 | 2 | **2,0** | 2 | darf fallen (B3) |
| TDG | 10 | 2 | 3 | 3 | 5 | 3,67 | 3 | — |
| META | 10 | 1 | 4 | 1 | 5 | 3,33 | 1 | — |
| GOOG | 10 | 0 | 5 | 3 | 5 | 4,33 | 3 | — |
| MNST | 10 | 0 | 5 | 2 | 5 | 4,0 | 2 | — |
| PLTR | 8 | 0 | 5 | 1 | 1 | 2,33 | 1 | — |
| ABNB | 7 | 1 | 4 | 1 | 1 | 2,0 | 1 | — |

**Beobachtung zu TPL, ohne Wertung.** TPL fällt, aber nicht an der Zyklik der Marge im üblichen
Sinn: seine operative Marge liegt über acht Jahre zwischen **86,9 % und 71,8 %**. Der Rückgang
vom Hoch beträgt 15,1 Prozentpunkte — das ist viel in Prozentpunkten und wenig relativ zum
Niveau (17 % des Höchststands). Die Kennzahl misst in Prozentpunkten, also hat ein
Hochmargen-Geschäft mehr Fallhöhe als ein Niedrigmargen-Geschäft. Ob das gewollt ist, ist eine
Entscheidung; hier steht nur, dass es so wirkt. TPL fällt zusätzlich über S1 (zwei
Rückgangsjahre bei sieben Übergängen → Quote 0,71, knapp unter der 0,72-Kante).

**Beobachtung zu NVDA.** Ein Rückgangsjahr (FY2019), schlechteste Nettomarge 16,2 % — beides
gut. Was NVDA drückt, ist allein S2: die operative Marge fällt 2021→2022 von **37,3 % auf
15,7 %** (21,6 pp). Unter jeder Bandtabelle, die den Zielkorridor erreicht, ist dieser Rückgang
verziehen und NVDA steht bei 4,0 bis 4,33.

**Beobachtung zu HL, NEM, MU.** Alle drei fallen mit **1,33**, und zwar über alle drei
Teilgrößen gleichzeitig (2/1/1). Sie fallen nicht knapp und nicht über eine einzelne Kennzahl —
das ist die Primärevidenz, die §10.3 verlangt: der Mechanismus greift aus dem richtigen Grund.
Die Jahresreihen unten zeigen es: NEMs operative Marge schwankt zwischen **−17,2 % und 50,0 %**,
MUs zwischen **−37,0 % und 49,3 %**, HLs zwischen **−6,9 % und 36,2 %**.

---

## B1 — Zusammenführung: `mean` gegen `min`

Anteil der 567 bewertbaren Titel mit Stetigkeit ≥ 4,0:

| Bänder | Kennzahlen | mean | min |
|---|---|---|---|
| Spec 5.1 (alt) | Std / EK-Rendite | 42 % | 29 % |
| Spec 5.1 (alt) | Rückgang / Nettomarge | 27 % | 15 % |
| S1 nach Anzahl | Std / EK-Rendite | 35 % | 20 % |
| **S1 nach Anzahl** | **Rückgang / Nettomarge** (entschieden) | **23 %** | **12 %** |
| lockerer S2 | Rückgang / Nettomarge | 28 % | 14 % |

`min` halbiert den Anteil durchgängig. Bei den Prüftiteln kippt `min` unter anderem **MEDP von
4,33 auf 3** (schlechteste Nettomarge 3,2 % → S3 = 3) und **GOOG von 4,33 auf 3** — beides
Titel, die §10.2 bzw. die Septemberliste oben sehen will.

## B2 — Schwellen für S2 und S3

Die gemessenen Verteilungen über die 521 Titel mit ≥ 10 Jahren:

| Größe | P10 | P25 | P50 | P75 | P90 |
|---|---|---|---|---|---|
| Rückgangsjahre (von 9) | 0 | 1 | 2 | 3 | 4 |
| Margenrückgang vom Hoch (pp) | 2,0 | 4,2 | **9,1** | 21,6 | 50,3 |
| schlechteste Nettomarge (%) | −34,0 | −7,9 | **2,2** | 7,9 | 13,9 |

Der Median-Titel hat 2 Rückgangsjahre (S1 = 3), 9,1 pp Margenrückgang und 2,2 % schlechteste
Nettomarge. Mit den vorgeschlagenen Schwellen ergibt das 3/3/3 = **3,0** — deshalb liegt der
Anteil ≥ 4,0 bei 23 % statt im Korridor.

**Nachschlagetabelle** (vollständig unten): welcher Anteil sich ergibt, wenn man die
Score-4-Kanten von S2 und S3 verschiebt, S1 nach Anzahl festgehalten, Mittelwert. „Harte
Bedingungen" = HL/NEM/MU unter 4,0 **und** MEDP/FAST/FICO ab 4,0.

| S2-Kante (pp) | S3-Kante (%) | Anteil ≥ 4,0 | harte Bedingungen | TPL | NVDA | TER |
|---|---|---|---|---|---|---|
| 10 | 0,0 | 38 % | erfüllt | 3,33 | 3,67 | 2,67 |
| 12 | −2,0 | 43 % | erfüllt | 3,33 | 4,0 | 2,67 |
| 15 | −5,0 | **50 %** | erfüllt | 3,33 | 4,0 | 3,33 |
| 20 | −5,0 | **54 %** | erfüllt | 3,67 | 4,0 | 3,33 |
| 25 | −2,0 | **51 %** | erfüllt | 3,67 | 4,33 | 3,0 |
| 25 | −5,0 | **57 %** | erfüllt | 3,67 | 4,33 | 3,33 |

Die harten Bedingungen halten in **jeder** Zeile der Tabelle. TPL und TER bleiben in jeder Zeile
unter 4,0. Die Kombinationen, die den Korridor erreichen, verlangen eine S3-Kante im negativen
Bereich — ein Titel dürfte also im schlechtesten Jahr des Fensters Verlust machen und trotzdem
die 4 bekommen.

## B3 — NVDA und TER

| | S1 | S2 | S3 | mean (vorgeschlagene Schwellen) | im Korridor (S2 ≥ 12 pp) |
|---|---|---|---|---|---|
| NVDA | 4 (1 Rückgangsjahr) | 1 (21,6 pp) | 5 (16,2 %) | 3,33 → fällt | **4,0–4,33 → bleibt** |
| TER | 2 (3 Rückgangsjahre) | 2 (13,7 pp) | 2 (−2,5 %) | 2,0 → fällt | 2,67–3,33 → fällt |

**TER fällt in jeder getesteten Kombination.** **NVDA fällt nur, solange die S2-Kante enger als
etwa 12 pp ist** — also nur außerhalb des Zielkorridors. Das ist die Kopplung aus Befund 5.

---

## Vollständige Ausgabe des Kalibrierungslaufs

`uv run python scripts\calibrate_steadiness_bands.py`

```
bewertbar (>= 7 J.): 567, davon >= 10 J.: 521
S3 (EK-Rendite) unbestimmbar wegen equity <= 0: 41 -> AAL, ABNB, APP, BJ, BROS, CHH, CNM, DASH, DBX, DOCN, DPZ, FICO, HCA, HIMS, HLT, HOOD, LII, LOW, LYV, MCD, MO, MP, MSCI, MSI, NTNX

== Verteilung (Titel mit >= 10 Jahren) ==
Groesse                               P10      P25      P50      P75      P90
S1 Anteil Nicht-Rueckgang            0.56     0.67     0.78     0.89     1.00
Rueckgangsjahre (von 9)                 0        1        2        3        4
S2 Margen-Std (pp)                    1.5      2.3      4.2      9.3     18.1
S2' Margen-Drawdown (pp)              2.0      4.2      9.1     21.6     50.3
S3 schlechteste EK-Rendite %        -54.6    -10.8      3.7     11.8     20.1
S3' schlechteste Nettomarge %       -34.0     -7.9      2.2      7.9     13.9

== Wie viele Titel bekaemen Stetigkeit >= 4,0? (Gate-Relevanz) ==
Baender                                           std/roe         drawdown/roe        std/netmargin   drawdown/netmargin
Spec 5.1                              237/567 (42%) n/a 41  165/567 (29%) n/a 41  229/567 (40%) n/a 0  155/567 (27%) n/a 0
S1 nach Rueckgangsjahren (0/1/2/3)    199/567 (35%) n/a 41  142/567 (25%) n/a 41  187/567 (33%) n/a 0  133/567 (23%) n/a 0
lockerer S2 (4/8/12/18)               213/567 (38%) n/a 41  166/567 (29%) n/a 41  210/567 (37%) n/a 0  156/567 (28%) n/a 0

== Preisnehmer, Positivfaelle, Prueftitel (Spec 5.1-Baender, Mittelwert) ==
Ticker    J. down    S1    Std     DD    wROE    wNM | Score  min | DD/NM
HL        10    3  0.67   12.8   23.9    -5.6  -14.1 |  2.33    2 |  1.33
NEM       10    3  0.67   19.1   55.1    -8.6  -21.1 |   2.0    1 |  1.33
MU        10    3  0.67   22.4   86.3   -13.2  -37.5 |  1.67    1 |  1.33
RGLD     -- nicht bewertbar (kein SEC / < 7 J. / Umsatzluecke)
TPL        8    2  0.71    4.8   15.1    33.0   58.2 |     4    3 |  2.67
SNDK     -- nicht bewertbar (kein SEC / < 7 J. / Umsatzluecke)
EDV.L    -- nicht bewertbar (kein SEC / < 7 J. / Umsatzluecke)
ANTO.L   -- nicht bewertbar (kein SEC / < 7 J. / Umsatzluecke)
MEDP      10    0  1.00    2.8    1.2     2.2    3.2 |  4.33    3 |  4.33
FAST      10    0  1.00    0.3    0.8    25.8   12.6 |     5    5 |     5
FICO      10    0  1.00   11.2    2.6     n/a   12.3 |   n/a    2 |     5
NVDA      10    1  0.89   15.1   21.6    19.8   16.2 |  3.33    1 |  3.33
TER       10    3  0.67    9.3   13.7    -2.4   -2.5 |  2.67    2 |   2.0
TDG       10    2  0.78    4.1    9.1     n/a   13.7 |   n/a    4 |  3.67
META      10    1  0.89    6.7   24.9    17.3   19.9 |   4.0    3 |  3.33
GOOG      10    0  1.00    4.1    6.2     8.3   11.4 |  4.33    4 |  4.33
MNST      10    0  1.00    3.9   10.5    17.0   18.9 |  4.67    4 |   4.0
PLTR       8    0  1.00   51.1   29.8     n/a -106.7 |   n/a    1 |  2.33
ABNB       7    1  0.83   43.1   95.8     n/a -135.7 |   n/a    1 |   2.0

== Primaerevidenz: Jahresreihen (Umsatz / operative Marge %) ==
- HL: Umsatz 2016: 0.65 Mrd, 2017: 0.58 Mrd, 2018: 0.57 Mrd, 2019: 0.67 Mrd, 2020: 0.69 Mrd, 2021: 0.81 Mrd, 2022: 0.72 Mrd, 2023: 0.72 Mrd, 2024: 0.93 Mrd, 2025: 1.42 Mrd
  HL: op. Marge 2016: 16.9%, 2017: 10.4%, 2018: -6.9%, 2019: -6.9%, 2020: 9.7%, 2021: 10.3%, 2022: -1.7%, 2023: -6.2%, 2024: 11.4%, 2025: 36.2%
- NEM: Umsatz 2016: 6.71 Mrd, 2017: 7.38 Mrd, 2018: 7.25 Mrd, 2019: 9.74 Mrd, 2020: 11.50 Mrd, 2021: 12.22 Mrd, 2022: 11.91 Mrd, 2023: 11.81 Mrd, 2024: 18.68 Mrd, 2025: 22.67 Mrd
  NEM: op. Marge 2016: -3.3%, 2017: 14.5%, 2018: 10.2%, 2019: 37.9%, 2020: 27.3%, 2021: 9.1%, 2022: -0.4%, 2023: -17.2%, 2024: 24.5%, 2025: 50.0%
- MU: Umsatz 2016: 12.40 Mrd, 2017: 20.32 Mrd, 2018: 30.39 Mrd, 2019: 23.41 Mrd, 2020: 21.43 Mrd, 2021: 27.70 Mrd, 2022: 30.76 Mrd, 2023: 15.54 Mrd, 2024: 25.11 Mrd, 2025: 37.38 Mrd
  MU: op. Marge 2016: 1.4%, 2017: 28.9%, 2018: 49.3%, 2019: 31.5%, 2020: 14.0%, 2021: 22.7%, 2022: 31.5%, 2023: -37.0%, 2024: 5.2%, 2025: 26.1%
- TPL: Umsatz 2018: 0.30 Mrd, 2019: 0.49 Mrd, 2020: 0.30 Mrd, 2021: 0.45 Mrd, 2022: 0.67 Mrd, 2023: 0.63 Mrd, 2024: 0.71 Mrd, 2025: 0.80 Mrd
  TPL: op. Marge 2018: 86.9%, 2019: 81.5%, 2020: 71.8%, 2021: 80.4%, 2022: 84.3%, 2023: 77.0%, 2024: 76.4%, 2025: 74.2%
- MEDP: Umsatz 2016: 0.42 Mrd, 2017: 0.44 Mrd, 2018: 0.70 Mrd, 2019: 0.86 Mrd, 2020: 0.93 Mrd, 2021: 1.14 Mrd, 2022: 1.46 Mrd, 2023: 1.89 Mrd, 2024: 2.11 Mrd, 2025: 2.53 Mrd
  MEDP: op. Marge 2016: 12.5%, 2017: 14.9%, 2018: 14.3%, 2019: 14.8%, 2020: 18.0%, 2021: 17.4%, 2022: 19.1%, 2023: 17.9%, 2024: 21.2%, 2025: 21.1%
- FAST: Umsatz 2016: 3.96 Mrd, 2017: 4.39 Mrd, 2018: 4.97 Mrd, 2019: 5.33 Mrd, 2020: 5.65 Mrd, 2021: 6.01 Mrd, 2022: 6.98 Mrd, 2023: 7.35 Mrd, 2024: 7.55 Mrd, 2025: 8.20 Mrd
  FAST: op. Marge 2016: 20.1%, 2017: 20.1%, 2018: 20.1%, 2019: 19.8%, 2020: 20.2%, 2021: 20.3%, 2022: 20.8%, 2023: 20.8%, 2024: 20.0%, 2025: 20.2%
- FICO: Umsatz 2016: 0.88 Mrd, 2017: 0.93 Mrd, 2018: 1.03 Mrd, 2019: 1.16 Mrd, 2020: 1.29 Mrd, 2021: 1.32 Mrd, 2022: 1.38 Mrd, 2023: 1.51 Mrd, 2024: 1.72 Mrd, 2025: 1.99 Mrd
  FICO: op. Marge 2016: 19.2%, 2017: 19.5%, 2018: 17.0%, 2019: 21.9%, 2020: 22.9%, 2021: 38.4%, 2022: 39.4%, 2023: 42.5%, 2024: 42.7%, 2025: 46.5%
  FICO: 5 Jahr(e) mit Eigenkapital <= 0
- NVDA: Umsatz 2016: 6.91 Mrd, 2017: 9.71 Mrd, 2018: 11.72 Mrd, 2019: 10.92 Mrd, 2020: 16.68 Mrd, 2021: 26.91 Mrd, 2022: 26.97 Mrd, 2023: 60.92 Mrd, 2024: 130.50 Mrd, 2025: 215.94 Mrd
  NVDA: op. Marge 2016: 28.0%, 2017: 33.0%, 2018: 32.5%, 2019: 26.1%, 2020: 27.2%, 2021: 37.3%, 2022: 15.7%, 2023: 54.1%, 2024: 62.4%, 2025: 60.4%
```

## Ergänzend berechnet (nicht Teil des Skript-Outputs)

Das Skript druckt die Aggregate nur für den **Mittelwert**. Für B1 fehlte die `min`-Variante, für B2 die Empfindlichkeit der Schwellen. Beides ist unten aus den Funktionen desselben Skripts berechnet — `compute()`, `score()` und `band()` importiert, das Skript selbst unverändert.

```
== ERGAENZEND: min(S1,S2,S3) statt mean, Anteil >= 4,0 ==
Baender                                           std/roe         drawdown/roe        std/netmargin   drawdown/netmargin
Spec 5.1                              163/567 (29%) n/a 41   97/567 (17%) n/a 41  147/567 (26%) n/a 0   84/567 (15%) n/a 0
S1 nach Rueckgangsjahren (0/1/2/3)    114/567 (20%) n/a 41   69/567 (12%) n/a 41  111/567 (20%) n/a 0   66/567 (12%) n/a 0
lockerer S2 (4/8/12/18)               121/567 (21%) n/a 41   81/567 (14%) n/a 41  118/567 (21%) n/a 0   79/567 (14%) n/a 0

== ERGAENZEND: Prueftitel unter den ENTSCHIEDENEN Kennzahlen (drawdown/netmargin, S1 nach Anzahl) ==
Ticker    J. down  S1  S2  S3 |  mean  min
HL        10    3   2   1   1 |  1.33    1
NEM       10    3   2   1   1 |  1.33    1
MU        10    3   2   1   1 |  1.33    1
TPL        8    2   2   1   5 |  2.67    1
MEDP      10    0   5   5   3 |  4.33    3
FAST      10    0   5   5   5 |     5    5
FICO      10    0   5   5   5 |     5    5
NVDA      10    1   4   1   5 |  3.33    1
TER       10    3   2   2   2 |   2.0    2
TDG       10    2   3   3   5 |  3.67    3
META      10    1   4   1   5 |  3.33    1
GOOG      10    0   5   3   5 |  4.33    3
MNST      10    0   5   2   5 |   4.0    2
PLTR       8    0   5   1   1 |  2.33    1
ABNB       7    1   4   1   1 |   2.0    1
```

```
bewertbare Titel: 567   Zielkorridor: 50-65 % mit >= 4,0
Nachschlagetabelle, KEINE Empfehlung. S1 = entschiedene Anzahl-Baender.

 S2 Score-4-Kante (pp)  S3 Score-4-Kante (%)  Anteil >=4,0  Harte Bedingungen   TPL  NVDA   TER
                     5                   5.0           22%           erfuellt   3.0  3.33   2.0
                     5                   2.0           26%           erfuellt   3.0  3.33  2.33
                     5                   0.0           29%           erfuellt   3.0  3.33  2.33
                     5                  -2.0           31%           erfuellt   3.0  3.33  2.33
                     5                  -5.0           33%           erfuellt   3.0  3.33  2.67
                     8                   5.0           28%           erfuellt  3.33  3.67  2.33
                     8                   2.0           33%           erfuellt  3.33  3.67  2.67
                     8                   0.0           35%           erfuellt  3.33  3.67  2.67
                     8                  -2.0           38%           erfuellt  3.33  3.67  2.67
                     8                  -5.0           41%           erfuellt  3.33  3.67   3.0
                    10                   5.0           30%           erfuellt  3.33  3.67  2.33
                    10                   2.0           35%           erfuellt  3.33  3.67  2.67
                    10                   0.0           38%           erfuellt  3.33  3.67  2.67
                    10                  -2.0           41%           erfuellt  3.33  3.67  2.67
                    10                  -5.0           44%           erfuellt  3.33  3.67   3.0
                    12                   5.0           32%           erfuellt  3.33   4.0  2.33
                    12                   2.0           38%           erfuellt  3.33   4.0  2.67
                    12                   0.0           41%           erfuellt  3.33   4.0  2.67
                    12                  -2.0           43%           erfuellt  3.33   4.0  2.67
                    12                  -5.0           47%           erfuellt  3.33   4.0   3.0
                    15                   5.0           34%           erfuellt  3.33   4.0  2.67
                    15                   2.0           39%           erfuellt  3.33   4.0   3.0
                    15                   0.0           43%           erfuellt  3.33   4.0   3.0
                    15                  -2.0           46%           erfuellt  3.33   4.0   3.0
                    15                  -5.0           50%           erfuellt  3.33   4.0  3.33
                    20                   5.0           36%           erfuellt  3.67   4.0  2.67
                    20                   2.0           41%           erfuellt  3.67   4.0   3.0
                    20                   0.0           45%           erfuellt  3.67   4.0   3.0
                    20                  -2.0           48%           erfuellt  3.67   4.0   3.0
                    20                  -5.0           54%           erfuellt  3.67   4.0  3.33
                    25                   5.0           38%           erfuellt  3.67  4.33  2.67
                    25                   2.0           44%           erfuellt  3.67  4.33   3.0
                    25                   0.0           48%           erfuellt  3.67  4.33   3.0
                    25                  -2.0           51%           erfuellt  3.67  4.33   3.0
                    25                  -5.0           57%           erfuellt  3.67  4.33  3.33
```

---

## Was dieser Bericht nicht sagt

- **Keine Empfehlung zu B1, B2, B3.** Die Zahlen stehen nebeneinander, die Wahl nicht.
- Die Nachschlagetabelle spannt S2- und S3-Bänder **um ihre Score-4-Kante herum** auf (S2: 0,4× / 1× / 2× / 4× der Kante; S3: Kante +5 / Kante / −5 / −15 Prozentpunkte). Das ist dieselbe Form wie der Vorschlag in §5.1, aber eine Form**annahme** — eine anders geschnittene Bandfamilie käme zu anderen Anteilen.
- Das Fenster ist auf zehn Jahre gekappt. NEM etwa hat 14 Jahre Historie; die vier ältesten (2012–2015, drei Rückgangsjahre in Folge) liegen außerhalb und gehen in keine Zahl ein.
- Gemessen ist die Verteilung über die **bewertbaren** Titel. Die 275 neutralen Titel (kein SEC-Registrant, Reihe zu kurz, kein Konzept) kommen in keiner Quote vor.
