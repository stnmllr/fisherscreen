# Universum 2026-10 — Crosshits

## Lauf-Übersicht 2026-10

- **Stichtag:** 2026-10 · **Universum:** 1322 (S&P 500 / S&P 400 / STOXX 600)
- **STOXX-Quellstufe:** nicht erfasst
- **Datenbasis:** yfinance (Kurs/Vol/Fundamentals) · SEC EDGAR (Filings; DEF-14A/Form-4 nur US-Filer)

| Stufe | rein | raus | übrig |
|---|---|---|---|
| Universum | 1322 | 0 | 1322 |
| Resolution | 1322 | 17 | 1305 |
| Basis-Gates | 1305 | 449 | 856 |
| EDGAR-Gates | 856 | 8 | 848 |
| Scoring | 848 | 0 | 848 |
| Crosshits | 848 | 831 | 17 |

**Review-Flags: 51** (Aufschlüsselung in `2026-10-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score | Stetigkeit | Preisnehmer |
|---|---|---|---|---|---|---|---|---|
| 1 | EDV.L  | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 4.67 | n/a ∅ | ja |
| 2 | FICO ~ | Fair Isaac Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 5 | nein |
| 3 | HL  | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 2.33 | ja |
| 4 | NEM  | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 | 1.33 | ja |
| 5 | NVDA  | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 | 4.0 | nein |
| 6 | PLTR  | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 4.67 | 2.67 | nein |
| 7 | RGLD  | Royal Gold, Inc. | Basic Materials | 3 | growth, profitability, resilience | 4.67 | n/a ↧ | ja |
| 8 | TDG ~ | Transdigm Group Incorporated | Industrials | 3 | growth, profitability, resilience | 4.67 | 4.0 | nein |
| 9 | TPL  | Texas Pacific Land Corporation | Energy | 3 | growth, profitability, resilience | 4.67 | 3.67 | ja |
| 10 | ABNB  | Airbnb, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 | 2.0 | nein |
| 11 | ARGX.BR  | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 12 | CDR.WA  | CDPROJEKT | Communication Services | 3 | growth, profitability, resilience | 4.33 | n/a ∅ | nein |
| 13 | META  | Meta Platforms, Inc. | Communication Services | 3 | growth, profitability, resilience | 4.33 | 3.67 | nein |
| 14 | MU  | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 | 1.33 | ja |
| 15 | SNDK ⚠ | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.33 | n/a ↧ | ja |
| 16 | ADYEN.AS  | ADYEN | Technology | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 17 | ANTO.L  | ANTOFAGASTA PLC ORD 5P | Basic Materials | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | ja |
| 18 | FAST  | Fastenal Company | Industrials | 3 | growth, profitability, resilience | 4.0 | 5 | nein |
| 19 | G24.DE  | Scout24 SE                    N | Communication Services | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |
| 20 | GOOG  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 21 | GOOGL  | Alphabet Inc. | Communication Services | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 22 | MEDP  | Medpace Holdings, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 23 | MNST  | Monster Beverage Corporation | Consumer Defensive | 3 | growth, profitability, resilience | 4.0 | 4.67 | nein |
| 24 | TER  | Teradyne, Inc. | Technology | 3 | growth, profitability, resilience | 4.0 | 2.67 | nein |
| 25 | WISE.L  | WISE GROUP PLC CLS A ORD USD0.0 | Technology | 3 | growth, profitability, resilience | 4.0 | n/a ∅ | nein |

> **Stetigkeit** = vierte Achse ueber bis zu zehn Jahre EDGAR-Jahreszahlen (Rueckgangsjahre, Margeneinbruch vom Hoch, schlechteste Nettomarge). **16 von 25** Titeln dieser Liste sind bewertet; `n/a` heisst nicht bewertbar und wird weder belohnt noch bestraft: `∅` kein SEC-Registrant, `↧` Reihe kuerzer als sieben Jahre, `⊘` kein Konzept getroffen. Bei sieben bis neun Jahren ist der Hoechstwert 4.

> **Preisnehmer** = das Unternehmen verkauft zu einem Preis, den es nicht setzt (Rohstoffe, Speicherchips). In einem Preiszyklus faerben sich alle drei Achsen gleichzeitig gruen, ohne dass sich am Geschaeft etwas geaendert haette. Die Spalte ist eine Kennzeichnung, kein Ausschluss: der Score ist unveraendert, die Liste vollstaendig. Grundlage ist `data/price_takers.json` (yfinance-`industry`, bewusst grob).
