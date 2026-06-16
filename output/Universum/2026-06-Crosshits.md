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
| Crosshits | 832 | 551 | 281 |

**Review-Flags: 63** (Aufschlüsselung in `2026-06-dropouts.csv`)

> Tool A ist ein Drei-Achsen-Screen: growth, profitability, resilience werden datengedeckt 0–5 bewertet — evidenzpflichtig: jeder Score ≥4.0 zitiert eine Kennzahl. management wird upstream im EDGAR-Gate geprüft, innovation ist auf den Deep Dive verschoben — beide zählen nicht als Crosshit-Treffer. Crosshit = ≥3 der drei aktiven Achsen ≥4.0. Hinweis: Das Gate ist bewusst locker — die Survivor sind durch die Negativ-Filter vorselektiert überdurchschnittlich, daher klumpen die Merit-Scores; gearbeitet wird mit der gerankten Top-Liste, nicht dem Gate-Count. Kalibrierte Selektivität folgt mit sektor-relativem (Perzentil-)Scoring.

*Schwelle: Score ≥4.0 in ≥3 Dimensionen*

| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score |
|---|---|---|---|---|---|---|
| 1 | APH | Amphenol Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 2 | APP | Applovin Corporation | Communication Services | 3 | growth, profitability, resilience | 4.67 |
| 3 | AVGO | Broadcom Inc. | Technology | 3 | growth, profitability, resilience | 4.67 |
| 4 | CME | CME Group Inc. | Financial Services | 3 | growth, profitability, resilience | 4.67 |
| 5 | EQT | EQT Corporation | Energy | 3 | growth, profitability, resilience | 4.67 |
| 6 | EXEL | Exelixis, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.67 |
| 7 | FICO | Fair Isaac Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 8 | HL | Hecla Mining Company | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 9 | LLY | Eli Lilly and Company | Healthcare | 3 | growth, profitability, resilience | 4.67 |
| 10 | MU | Micron Technology, Inc. | Technology | 3 | growth, profitability, resilience | 4.67 |
| 11 | NEM | Newmont Corporation | Basic Materials | 3 | growth, profitability, resilience | 4.67 |
| 12 | NVDA | NVIDIA Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 13 | PLTR | Palantir Technologies Inc. | Technology | 3 | growth, profitability, resilience | 4.67 |
| 14 | RMV.L | RIGHTMOVE PLC ORD 0.1P | Communication Services | 3 | growth, profitability, resilience | 4.67 |
| 15 | SCT.L | SOFTCAT PLC | Technology | 3 | growth, profitability, resilience | 4.67 |
| 16 | SNDK | Sandisk Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 17 | STRL | Sterling Infrastructure, Inc. | Industrials | 3 | growth, profitability, resilience | 4.67 |
| 18 | STX | Seagate Technology Holdings PLC | Technology | 3 | growth, profitability, resilience | 4.67 |
| 19 | WDC | Western Digital Corporation | Technology | 3 | growth, profitability, resilience | 4.67 |
| 20 | AAON | AAON, Inc. | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 21 | AAPL | Apple Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 22 | ABBN.SW | ABB LTD N | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 23 | ADBE | Adobe Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 24 | ADI | Analog Devices, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 25 | ADP | Automatic Data Processing, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 26 | ADSK | Autodesk, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 27 | ADYEN.AS | ADYEN | Technology | 3 | growth, profitability, resilience | 4.33 |
| 28 | ALLE | Allegion plc | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 29 | ALV | Autoliv, Inc. | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 30 | AMAT | Applied Materials, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 31 | AMCR | Amcor plc | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 32 | ANET | Arista Networks, Inc. | Technology | 3 | growth, profitability, resilience | 4.33 |
| 33 | AON | Aon plc | Financial Services | 3 | growth, profitability, resilience | 4.33 |
| 34 | ARGX.BR | ARGENX SE | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 35 | ASML.AS | ASML HOLDING | Technology | 3 | growth, profitability, resilience | 4.33 |
| 36 | AVY | Avery Dennison Corporation | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 37 | AZN.L | ASTRAZENECA PLC ORD SHS $0.25 | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 38 | CAT | Caterpillar, Inc. | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 39 | CBOE | Cboe Global Markets, Inc. | Financial Services | 3 | growth, profitability, resilience | 4.33 |
| 40 | CELH | Celsius Holdings, Inc. | Consumer Defensive | 3 | growth, profitability, resilience | 4.33 |
| 41 | CF | CF Industries Holdings, Inc. | Basic Materials | 3 | growth, profitability, resilience | 4.33 |
| 42 | CNX | CNX Resources Corporation | Energy | 3 | growth, profitability, resilience | 4.33 |
| 43 | CTAS | Cintas Corporation | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 44 | DCI | Donaldson Company, Inc. | Industrials | 3 | growth, profitability, resilience | 4.33 |
| 45 | DECK | Deckers Outdoor Corporation | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 46 | DKS | Dick's Sporting Goods Inc | Consumer Cyclical | 3 | growth, profitability, resilience | 4.33 |
| 47 | DXCM | DexCom, Inc. | Healthcare | 3 | growth, profitability, resilience | 4.33 |
| 48 | EDV.L | ENDEAVOUR MINING PLC ORD USD0.0 | Basic Materials | 3 | growth, profitability, resilience | 4.33 |
| 49 | EXE | Expand Energy Corporation | Energy | 3 | growth, profitability, resilience | 4.33 |
| 50 | EXPD | Expeditors International of Was | Industrials | 3 | growth, profitability, resilience | 4.33 |
