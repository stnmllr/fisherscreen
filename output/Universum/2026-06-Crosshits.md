# Universum 2026-06 — Crosshits

## Lauf-Übersicht 2026-06

- **Stichtag:** 2026-06 · **Universum:** 1322 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** nicht erfasst
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1322 | 0 | 1322 |
| Resolution | 1322 | 8 | 1314 |
| Basis-Gates | 1314 | 474 | 840 |
| EDGAR-Gates | 840 | 8 | 832 |
| Scoring | 832 | 0 | 832 |
| Crosshits | 832 | 807 | 25 |

**Review-Flags: 63** (Aufschlüsselung in `2026-06-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score |
|---|---|---|---|---|---|---|
| 1 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 5.0 |
| 2 | FICO ~ | Fair Isaac Corporation | Technology | 3 | growth, profitability, resilience | 5.0 |
| 3 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 4 | INDV ~ | Indivior Pharmaceuticals, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 |
| 5 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 6 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 7 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 4.67 |
| 8 | RGLD  | Royal Gold, Inc. | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 9 | TDG ~ | Transdigm Group Incorporated | Industrials | 3 | growth, profitability, resilience | 4.67 |
| 10 | TPL  | Texas Pacific Land Corporation | Energy | 3 | growth, profitability, resilience | 4.67 |
| 11 | ARGX.BR ~ | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 12 | BKNG ~ | Booking Holdings Inc. Common St | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 13 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 14 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.33 |
| 15 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 |
| 16 | PLNT ~ | Planet Fitness, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 17 | SNDK ⚠ | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.33 |
| 18 | ADYEN.AS  | ADYEN | Technology | 3 | growth, profitability, resilience | 4.0 |
| 19 | EQT  | EQT Corporation | Energy | 3 | growth, profitability, resilience | 4.0 |
| 20 | G24.DE  | Scout24 SE                    N | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 21 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 22 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 23 | MSCI ~ | MSCI Inc. | Financial Services | 3 | growth, profitability, resilience | 4.0 |
| 24 | PTC  | PTC Inc. | Technology | 3 | growth, profitability, resilience | 4.0 |
| 25 | TER  | Teradyne, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 |
