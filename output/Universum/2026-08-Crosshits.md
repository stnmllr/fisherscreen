# Universum 2026-08 — Crosshits

## Lauf-Übersicht 2026-08

- **Stichtag:** 2026-08 · **Universum:** 1322 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** nicht erfasst
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1322 | 0 | 1322 |
| Resolution | 1322 | 10 | 1312 |
| Basis-Gates | 1312 | 460 | 852 |
| EDGAR-Gates | 852 | 9 | 843 |
| Scoring | 843 | 0 | 843 |
| Crosshits | 843 | 815 | 28 |

**Review-Flags: 53** (Aufschlüsselung in `2026-08-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score |
|---|---|---|---|---|---|---|
| 1 | FICO ~ | Fair Isaac Corporation | Technology | 3 | growth, profitability, resilience | 5.0 |
| 2 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 3 | INDV ~ | Indivior Pharmaceuticals, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 |
| 4 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 5 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 6 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 4.67 |
| 7 | RGLD  | Royal Gold, Inc. | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 8 | TDG ~ | Transdigm Group Incorporated | Industrials | 3 | growth, profitability, resilience | 4.67 |
| 9 | TPL  | Texas Pacific Land Corporation | Energy | 3 | growth, profitability, resilience | 4.67 |
| 10 | ARGX.BR  | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 11 | BKNG ~ | Booking Holdings Inc. Common St | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 12 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 4.33 |
| 13 | EW ~ | Edwards Lifesciences Corporatio | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 14 | FTNT  | Fortinet, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 15 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.33 |
| 16 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 |
| 17 | MU  | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 18 | PLNT ~ | Planet Fitness, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 19 | SNDK ⚠ | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.33 |
| 20 | TRN.MI  | TERNA | Utilities | 3 | growth, profitability, resilience | 4.33 |
| 21 | WISE.L  | WISE GROUP PLC CLS A ORD USD0.0 | Technology | 3 | growth, profitability, resilience | 4.33 |
| 22 | ADYEN.AS  | ADYEN | Technology | 3 | growth, profitability, resilience | 4.0 |
| 23 | FAST  | Fastenal Company | Industrials | 3 | growth, profitability, resilience | 4.0 |
| 24 | G24.DE  | Scout24 SE                    N | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 25 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 26 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 |
| 27 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 |
| 28 | TER  | Teradyne, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 |
