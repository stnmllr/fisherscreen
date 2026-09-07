# EDGAR companyfacts — Abdeckungsmessung Jahreshistorie

**Erzeugt:** 2026-09-07 · **Basis:** gescorte Titel des Laufs 2026-09 (843), rekonstruiert aus `2026-09-dropouts.csv` + `2026-09-Crosshits.md`, gegen `funnel_summary.json` geprueft

Frage: reichen die SEC-XBRL-Jahresdaten fuer eine vierte Tool-A-Dimension **Stetigkeit** ueber zehn Jahre?

## Grundgesamtheit

| | Anzahl |
|---|---|
| Titel im Lauf 2026-09 (gescort) | 843 |
| davon US-Titel (kein `.` im Symbol) | 610 |
| davon Nicht-SEC-Titel (uebersprungen) | 233 |
| US-Titel mit companyfacts gemessen | 607 |
| US-Titel ohne CIK in company_tickers.json | 3 |
| US-Titel mit CIK, aber ohne companyfacts (404) | 0 |

**Requests:** 610 (ein companyfacts-Abruf je Titel, plus einmal company_tickers.json) · **Laufzeit:** 6.8 min · **Kosten:** $0 · **transiente Fehler:** 0

## Abdeckung je Konzept

Gezaehlt werden **zusammenhaengende** Geschaeftsjahre, die am juengsten vorhandenen Jahr enden. Bezugsgroesse ist `US-Titel mit companyfacts gemessen` (607).

| Konzept | >=10 Jahre | >=7 Jahre | <7 Jahre | kein Konzept |
|---|---|---|---|---|
| Umsatz | 505 (83.2%) | 55 (9.1%) | 41 (6.8%) | 6 (1.0%) |
| Operatives Ergebnis | 474 (78.1%) | 45 (7.4%) | 36 (5.9%) | 52 (8.6%) |
| Nettogewinn | 470 (77.4%) | 56 (9.2%) | 70 (11.5%) | 11 (1.8%) |
| Eigenkapital | 492 (81.1%) | 50 (8.2%) | 51 (8.4%) | 14 (2.3%) |
| Gesamtvermoegen | 522 (86.0%) | 42 (6.9%) | 42 (6.9%) | 1 (0.2%) |

Die Spalten sind disjunkt: `>=7` meint sieben bis neun Jahre, nicht "mindestens sieben".

## Was die Stetigkeits-Dimension wirklich braucht

Die drei vorgeschlagenen Kriterien (Jahre mit Umsatzwachstum, Schwankung der operativen Marge, schlechteste Eigenkapitalrendite) brauchen **vier Reihen gleichzeitig**: Umsatz, operatives Ergebnis, Nettogewinn, Eigenkapital. Eine Reihe allein genuegt nicht.

| Anspruch | Konzeptliste | US-Titel | Anteil gemessene | Anteil aller US-Titel |
|---|---|---|---|---|
| alle vier Reihen >=10 Jahre | Auftrag | 364 | 60.0% | 59.7% |
| alle vier Reihen >=10 Jahre | erweitert | 519 | 85.5% | 85.1% |
| alle vier Reihen >=7 Jahre | Auftrag | 437 | 72.0% | 71.6% |
| alle vier Reihen >=7 Jahre | erweitert | 568 | 93.6% | 93.1% |

`Auftrag` ist die Konzeptliste aus der Aufgabenstellung. `erweitert` nimmt je Konzept zusaetzliche us-gaap-Tags dazu, die dieselbe Groesse unter anderem Namen fuehren (`ALTERNATIVES` im Skript) — die Differenz ist der Preis der Namensluecke, nicht der Datenluecke.

### Was die erweiterte Liste je Konzept bringt

| Konzept | >=10 Jahre (Auftrag) | >=10 Jahre (erweitert) | Differenz |
|---|---|---|---|
| Umsatz | 505 (83.2%) | 525 (86.5%) | +20 |
| Operatives Ergebnis | 474 (78.1%) | 529 (87.1%) | +55 |
| Nettogewinn | 470 (77.4%) | 532 (87.6%) | +62 |
| Eigenkapital | 492 (81.1%) | 542 (89.3%) | +50 |
| Gesamtvermoegen | 522 (86.0%) | 522 (86.0%) | +0 |

Die Tags, die den Unterschied machen, nach Haeufigkeit:

- **Umsatz:** `RevenueFromContractWithCustomerIncludingAssessedTax` (21), `SalesRevenueGoodsNet` (8), `SalesRevenueServicesNet` (3)
- **Operatives Ergebnis:** `IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest` (59), `IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments` (36)
- **Nettogewinn:** `ProfitLoss` (68), `NetIncomeLossAvailableToCommonStockholdersBasic` (14)
- **Eigenkapital:** `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` (79)

## Perioden- gegen fy-Schluessel (Umsatz)

Der Auftrag sah Deduplizierung ueber `fy` vor. In companyfacts benennt `fy` aber das Geschaeftsjahr des **meldenden Filings**: der FY2025-10-K traegt FY2023 und FY2024 ebenfalls mit `fy=2025, fp=FY`. Beide Lesarten nebeneinander, damit die Abweichung pruefbar ist:

| Lesart | Mittelwert Jahre | Titel mit >=10 |
|---|---|---|
| Perioden-Schluessel (verwendet) | 14.4 | 505 (84.0%) |
| `fy`-Schluessel (verworfen) | 12.6 | 417 (69.4%) |

## Gegenprobe: die 24 Crosshits des Septemberlaufs

Der eigentliche Abnahmetest. `PT` markiert die acht von Hand benannten Preisnehmer. `Jahre` ist die kuerzeste der vier benoetigten Reihen (erweiterte Konzeptliste) — sie bestimmt, ob ein Titel eine echte Stetigkeit bekommt oder nach dem Vorschlag "neutral, nicht bestrafen" durchgereicht wird.

| Ticker | PT | Jahre (Auftragsliste) | Jahre (erweitert) | Folge |
|---|---|---|---|---|
| EDV.L | **PT** | — | — | kein SEC-Registrant → neutral |
| FICO |  | 18 | 18 | bewertbar |
| HL | **PT** | 6 | 15 | bewertbar |
| NEM | **PT** | 0 | 14 | bewertbar |
| NVDA |  | 19 | 19 | bewertbar |
| PLTR |  | 8 | 8 | zu kurz → neutral |
| RGLD | **PT** | 5 | 5 | zu kurz → neutral |
| TDG |  | 18 | 18 | bewertbar |
| TPL | **PT** | 8 | 8 | zu kurz → neutral |
| ABNB |  | 7 | 7 | zu kurz → neutral |
| ARGX.BR |  | — | — | kein SEC-Registrant → neutral |
| META |  | 15 | 15 | bewertbar |
| MU | **PT** | 16 | 17 | bewertbar |
| SNDK | **PT** | 4 | 4 | zu kurz → neutral |
| ADYEN.AS |  | — | — | kein SEC-Registrant → neutral |
| ANTO.L | **PT** | — | — | kein SEC-Registrant → neutral |
| FAST |  | 19 | 19 | bewertbar |
| G24.DE |  | — | — | kein SEC-Registrant → neutral |
| GOOG |  | 13 | 13 | bewertbar |
| GOOGL |  | 13 | 13 | bewertbar |
| MEDP |  | 11 | 11 | bewertbar |
| MNST |  | 0 | 18 | bewertbar |
| TER |  | 18 | 18 | bewertbar |
| WISE.L |  | — | — | kein SEC-Registrant → neutral |

**13 von 24** Titeln bekaemen eine echte Stetigkeit. Von den acht Preisnehmern blieben **5 unbewertet**: `EDV.L`, `RGLD`, `TPL`, `SNDK`, `ANTO.L`.

## Primaer-Evidenz (Stichprobe)

Ein Aggregat beweist nicht, dass der Mechanismus greift. Drei Reihen im Klartext, gegen die Filings pruefbar:

- **FAST** (FASTENAL CO) — Konzept `RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet`, 
  19 zusammenhaengende Jahre, 1 Restatement(s), Einheit USD
  <br>2007: 2.06 Mrd, 2008: 2.34 Mrd, 2009: 1.93 Mrd, 2010: 2.27 Mrd, 2011: 2.77 Mrd, 2012: 3.13 Mrd, 2013: 3.33 Mrd, 2014: 3.73 Mrd, 2015: 3.87 Mrd, 2016: 3.96 Mrd, 2017: 4.39 Mrd, 2018: 4.97 Mrd, 2019: 5.33 Mrd, 2020: 5.65 Mrd, 2021: 6.01 Mrd, 2022: 6.98 Mrd, 2023: 7.35 Mrd, 2024: 7.55 Mrd, 2025: 8.20 Mrd
- **NEM** (NEWMONT CORPORATION) — Konzept `Revenues+RevenueFromContractWithCustomerExcludingAssessedTax`, 
  14 zusammenhaengende Jahre, 2 Restatement(s), Einheit USD
  <br>2012: 9.96 Mrd, 2013: 8.41 Mrd, 2014: 6.82 Mrd, 2015: 6.08 Mrd, 2016: 6.71 Mrd, 2017: 7.38 Mrd, 2018: 7.25 Mrd, 2019: 9.74 Mrd, 2020: 11.50 Mrd, 2021: 12.22 Mrd, 2022: 11.91 Mrd, 2023: 11.81 Mrd, 2024: 18.68 Mrd, 2025: 22.67 Mrd
- **XOM** (Exxon Mobil Corporation) — Konzept `None`, 
  kein Umsatzkonzept getroffen; vorhandene Tags (Auswahl): AccruedIncomeTaxesCurrent, AccumulatedOtherComprehensiveIncomeLossNetOfTax, Assets, AssetsCurrent, ComprehensiveIncomeNetOfTax, ComprehensiveIncomeNetOfTaxAttributableToNoncontrollingInterest, ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest, DeferredIncomeTaxLiabilitiesNet, EquityMethodInvestments, IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest, IncomeTaxExpenseBenefit, IncreaseDecreaseInOtherCurrentAssetsAndLiabilitiesNet

## Titel ohne greifendes Umsatzkonzept

6 Titel. Die Spalte `vorhandene us-gaap-Tags` zeigt, welcher Fallback fehlt (Banken und Versicherer melden Zinsertrag statt Umsatz).

| Ticker | Name | Tags gesamt | vorhandene us-gaap-Tags (Auswahl) |
|---|---|---|---|
| AAON | AAON, INC. | 402 | `AccruedIncomeTaxes`, `AccruedIncomeTaxesCurrent`, `AccruedSalesCommissionCurrent`, `AmortizationOfIntangibleAssets`, `Assets`, `AssetsCurrent`, `BusinessAcquisitionsProFormaNetIncomeLoss`, `BusinessAcquisitionsProFormaRevenue` |
| APA | APA CORPORATION | 360 | `AccretionExpenseIncludingAssetRetirementObligations`, `AccruedIncomeTaxesCurrent`, `AccumulatedOtherComprehensiveIncomeLossDefinedBenefitPensionAndOtherPostretirementPlansNetOfTax`, `AccumulatedOtherComprehensiveIncomeLossNetOfTax`, `AmortizationOfDebtDiscountPremium`, `AssetImpairmentCharges`, `AssetRetirementObligation`, `AssetRetirementObligationAccretionExpense` |
| CRWD | CROWDSTRIKE HOLDINGS, INC. | 448 | `AccretionAmortizationOfDiscountsAndPremiumsInvestments`, `AccruedIncomeTaxesCurrent`, `AccruedSalesCommissionCurrent`, `AccumulatedOtherComprehensiveIncomeLossNetOfTax`, `AllowanceForDoubtfulAccountsPremiumsAndOtherReceivables`, `AmortizationOfIntangibleAssets`, `Assets`, `AssetsCurrent` |
| ODFL | OLD DOMINION FREIGHT LINE, INC. | 300 | `AccruedIncomeTaxesCurrent`, `AmortizationOfIntangibleAssets`, `Assets`, `AssetsCurrent`, `AssetsFairValueDisclosure`, `CapitalLeasedAssetsGross`, `CapitalLeasesBalanceSheetAssetsByMajorClassNet`, `CapitalLeasesLesseeBalanceSheetAssetsByMajorClassAccumulatedDeprecation` |
| SJM | The J. M. Smucker Company | 509 | `AccruedIncomeTaxesCurrent`, `AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax`, `AccumulatedOtherComprehensiveIncomeLossCumulativeChangesInNetGainLossFromCashFlowHedgesEffectNetOfTax`, `AccumulatedOtherComprehensiveIncomeLossDefinedBenefitPensionAndOtherPostretirementPlansNetOfTax`, `AccumulatedOtherComprehensiveIncomeLossForeignCurrencyTranslationAdjustmentNetOfTax`, `AccumulatedOtherComprehensiveIncomeLossNetOfTax`, `AdjustmentToAdditionalPaidInCapitalIncomeTaxEffectFromShareBasedCompensationNet`, `AmortizationOfIntangibleAssets` |
| XOM | Exxon Mobil Corporation | 94 | `AccruedIncomeTaxesCurrent`, `AccumulatedOtherComprehensiveIncomeLossNetOfTax`, `Assets`, `AssetsCurrent`, `ComprehensiveIncomeNetOfTax`, `ComprehensiveIncomeNetOfTaxAttributableToNoncontrollingInterest`, `ComprehensiveIncomeNetOfTaxIncludingPortionAttributableToNoncontrollingInterest`, `DeferredIncomeTaxLiabilitiesNet` |

## US-Titel ohne CIK in `company_tickers.json`

`BLD`, `EA`, `GTLS`

## Nicht-SEC-Titel im Universum

233 der 843 gescorten Titel (27.6%) tragen ein Boersensuffix und sind keine SEC-Registranten — sie kaemen ueber EDGAR ohnehin nicht.

## Abdeckung je Titel

Zusammenhaengende Geschaeftsjahre je Konzept. `R` = Restatements auf der Umsatzreihe (Perioden mit mehr als einem gemeldeten Wert).

| Ticker | Umsatz | Op. Ergebnis | Nettogewinn | Eigenkapital | Vermoegen | R | Umsatzkonzept |
|---|---|---|---|---|---|---|---|
| A | 19 | 19 | 6 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AAL | 13 | 18 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AAON | 0 | 17 | 17 | 0 | 16 | 0 | — |
| AAPL | 19 | 19 | 19 | 20 | 18 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ABBV | 15 | 15 | 12 | 14 | 14 | 0 | Revenues+SalesRevenueNet |
| ABNB | 7 | 7 | 7 | 8 | 6 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ABT | 19 | 19 | 15 | 19 | 19 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ACI | 11 | 11 | 11 | 9 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ACN | 18 | 18 | 18 | 17 | 17 | 2 | Revenues |
| ADBE | 19 | 19 | 19 | 20 | 18 | 2 | Revenues |
| ADI | 19 | 19 | 17 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ADP | 19 | 0 | 19 | 18 | 19 | 7 | Revenues |
| ADSK | 19 | 19 | 19 | 20 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AEE | 19 | 19 | 11 | 18 | 18 | 3 | Revenues |
| AEIS | 17 | 17 | 16 | 18 | 16 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AEP | 19 | 19 | 7 | 18 | 18 | 4 | Revenues |
| AIT | 18 | 18 | 18 | 19 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AJG | 18 | 0 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AKAM | 11 | 19 | 19 | 20 | 18 | 0 | Revenues |
| ALB | 18 | 18 | 18 | 17 | 17 | 3 | Revenues+SalesRevenueNet |
| ALGM | 7 | 7 | 7 | 7 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ALGN | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ALK | 18 | 18 | 18 | 19 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ALLE | 14 | 14 | 14 | 11 | 13 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ALV | 10 | 18 | 18 | 17 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| AM | 11 | 10 | 3 | 7 | 10 | 0 | Revenues |
| AMAT | 19 | 19 | 19 | 19 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AMCR | 10 | 10 | 10 | 9 | 9 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AMD | 16 | 18 | 16 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AME | 4 | 19 | 19 | 19 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AMG | 10 | 10 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| AMGN | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AMZN | 19 | 19 | 19 | 20 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ANET | 14 | 14 | 14 | 15 | 13 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ANF | 18 | 18 | 13 | 19 | 17 | 0 | Revenues+SalesRevenueNet |
| AON | 19 | 19 | 7 | 18 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AOS | 10 | 16 | 18 | 13 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| APA | 0 | 7 | 3 | 6 | 7 | 0 | — |
| APD | 19 | 19 | 19 | 20 | 18 | 3 | Revenues+SalesRevenueNet |
| APG | 8 | 8 | 8 | 7 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| APH | 10 | 19 | 12 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| APO | 6 | 0 | 6 | 5 | 5 | 0 | Revenues |
| APP | 7 | 7 | 7 | 8 | 6 | 2 | Revenues |
| APPF | 13 | 13 | 13 | 14 | 12 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| APTV | 10 | 16 | 16 | 15 | 15 | 0 | Revenues |
| AR | 15 | 15 | 4 | 16 | 14 | 0 | Revenues |
| ARES | 14 | 0 | 12 | 12 | 14 | 2 | Revenues |
| ARWR | 15 | 16 | 16 | 16 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ASH | 12 | 12 | 6 | 11 | 12 | 6 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ATI | 10 | 19 | 19 | 18 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ATO | 10 | 18 | 18 | 19 | 17 | 0 | Revenues |
| ATR | 18 | 18 | 6 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| AVGO | 10 | 10 | 3 | 3 | 9 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AVNT | 10 | 17 | 17 | 18 | 17 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AVTR | 9 | 9 | 9 | 10 | 8 | 0 | Revenues |
| AVY | 18 | 0 | 10 | 19 | 17 | 4 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| AWK | 8 | 18 | 18 | 19 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| AXTA | 12 | 12 | 12 | 11 | 11 | 4 | Revenues |
| AYI | 10 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BALL | 10 | 16 | 4 | 19 | 17 | 0 | SalesRevenueNet |
| BAX | 19 | 13 | 19 | 18 | 18 | 8 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| BBY | 13 | 13 | 13 | 8 | 18 | 4 | Revenues+SalesRevenueNet |
| BDC | 10 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BDX | 19 | 19 | 14 | 18 | 18 | 7 | Revenues+SalesRevenueNet |
| BEN | 19 | 19 | 19 | 20 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BF-B | 10 | 18 | 18 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| BIIB | 19 | 15 | 19 | 16 | 18 | 2 | Revenues |
| BILL | 9 | 9 | 9 | 10 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| BJ | 10 | 10 | 10 | 11 | 9 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| BKH | 18 | 18 | 11 | 19 | 17 | 3 | Revenues+SalesRevenueNet |
| BKNG | 18 | 18 | 3 | 18 | 17 | 0 | Revenues+SalesRevenueNet |
| BKR | 11 | 10 | 11 | 10 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| BLK | 4 | 4 | 4 | 3 | 3 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BMRN | 18 | 18 | 18 | 19 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BMY | 19 | 0 | 19 | 18 | 18 | 0 | Revenues+SalesRevenueNet |
| BR | 18 | 18 | 9 | 19 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BRKR | 17 | 17 | 16 | 16 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BRO | 18 | 0 | 18 | 17 | 17 | 4 | Revenues |
| BROS | 7 | 7 | 7 | 6 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| BSX | 19 | 19 | 0 | 5 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| BSY | 8 | 8 | 8 | 3 | 7 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BURL | 15 | 0 | 15 | 16 | 14 | 0 | Revenues |
| BWA | 15 | 19 | 19 | 18 | 18 | 4 | Revenues |
| BWXT | 17 | 17 | 17 | 16 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| BYD | 4 | 17 | 17 | 16 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CACI | 18 | 18 | 18 | 14 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CAG | 15 | 18 | 19 | 17 | 18 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CARR | 8 | 8 | 4 | 0 | 7 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CART | 5 | 5 | 5 | 6 | 4 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CASY | 18 | 0 | 18 | 19 | 17 | 0 | Revenues+SalesRevenueNet |
| CAT | 19 | 19 | 4 | 0 | 19 | 0 | Revenues |
| CAVA | 5 | 5 | 5 | 6 | 4 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CBOE | 9 | 17 | 3 | 14 | 16 | 2 | Revenues |
| CBT | 18 | 18 | 18 | 17 | 17 | 2 | Revenues+SalesRevenueNet |
| CCK | 18 | 13 | 18 | 17 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CCL | 12 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CDNS | 18 | 18 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CDW | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CELH | 9 | 11 | 11 | 12 | 11 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CF | 19 | 19 | 5 | 18 | 18 | 2 | Revenues+SalesRevenueNet |
| CGNX | 18 | 18 | 18 | 19 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CHD | 10 | 18 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CHDN | 15 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CHE | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| CHH | 18 | 18 | 18 | 19 | 17 | 5 | Revenues |
| CHRD | 5 | 5 | 5 | 18 | 16 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CHTR | 16 | 16 | 16 | 15 | 15 | 0 | Revenues |
| CIEN | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| CL | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CLH | 18 | 18 | 10 | 11 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CMCSA | 19 | 19 | 19 | 18 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CME | 19 | 19 | 19 | 20 | 18 | 0 | Revenues |
| CMG | 10 | 18 | 18 | 19 | 17 | 0 | Revenues |
| CMI | 19 | 19 | 4 | 18 | 18 | 0 | Revenues+SalesRevenueNet |
| CMS | 18 | 18 | 18 | 17 | 17 | 2 | Revenues |
| CNH | 6 | 0 | 6 | 0 | 5 | 0 | Revenues |
| CNM | 7 | 7 | 7 | 5 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CNP | 19 | 19 | 19 | 19 | 18 | 2 | Revenues |
| COHR | 18 | 13 | 18 | 17 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| COIN | 7 | 7 | 7 | 8 | 6 | 0 | Revenues |
| COKE | 17 | 17 | 17 | 16 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| COLM | 10 | 17 | 3 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| COO | 18 | 18 | 18 | 19 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| COP | 19 | 0 | 19 | 18 | 18 | 2 | Revenues+SalesRevenueNet |
| COTY | 10 | 15 | 15 | 14 | 14 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CPB | 9 | 18 | 18 | 17 | 17 | 0 | Revenues |
| CPRT | 10 | 17 | 17 | 5 | 16 | 0 | Revenues+SalesRevenueNet |
| CR | 5 | 5 | 5 | 4 | 4 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CRH | 5 | 5 | 5 | 4 | 4 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| CRL | 18 | 18 | 13 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CRM | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CROX | 17 | 17 | 17 | 17 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CRS | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CRUS | 17 | 17 | 17 | 18 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CRWD | 0 | 9 | 9 | 8 | 8 | 0 | — |
| CSCO | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CSGP | 17 | 17 | 17 | 17 | 16 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CSL | 18 | 18 | 17 | 18 | 17 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CSX | 19 | 19 | 19 | 0 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CTAS | 18 | 18 | 17 | 16 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| CTSH | 19 | 19 | 19 | 20 | 18 | 2 | Revenues+SalesRevenueNet |
| CVLT | 18 | 18 | 18 | 19 | 17 | 2 | Revenues |
| CVX | 19 | 0 | 19 | 19 | 18 | 0 | Revenues |
| CW | 18 | 18 | 18 | 17 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| CXT | 18 | 18 | 18 | 17 | 17 | 7 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| D | 19 | 19 | 19 | 20 | 18 | 5 | Revenues+SalesRevenueNet |
| DAL | 17 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| DAR | 18 | 18 | 18 | 19 | 17 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DASH | 8 | 8 | 8 | 9 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DBX | 10 | 10 | 10 | 11 | 9 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DD | 11 | 0 | 11 | 10 | 11 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DDOG | 9 | 9 | 9 | 10 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DECK | 10 | 12 | 11 | 13 | 13 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DG | 10 | 17 | 11 | 18 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DGX | 19 | 19 | 19 | 18 | 18 | 4 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DHI | 17 | 0 | 10 | 17 | 17 | 0 | Revenues |
| DHR | 19 | 19 | 19 | 18 | 18 | 9 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DIS | 9 | 9 | 9 | 8 | 8 | 1 | Revenues |
| DKS | 18 | 18 | 3 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DLB | 18 | 18 | 18 | 17 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| DLTR | 10 | 18 | 18 | 10 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| DOCN | 7 | 7 | 7 | 8 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DOCS | 7 | 7 | 7 | 8 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DOCU | 10 | 10 | 10 | 11 | 9 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DOV | 19 | 19 | 19 | 7 | 18 | 7 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DPZ | 17 | 17 | 17 | 16 | 16 | 0 | Revenues |
| DRI | 19 | 14 | 19 | 20 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DT | 9 | 9 | 9 | 10 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DTM | 7 | 7 | 7 | 5 | 7 | 0 | Revenues |
| DUK | 10 | 19 | 19 | 18 | 18 | 3 | Revenues+SalesRevenueNet |
| DUOL | 6 | 6 | 6 | 7 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| DVA | 10 | 19 | 19 | 18 | 18 | 0 | Revenues |
| DVN | 19 | 6 | 19 | 18 | 18 | 6 | Revenues |
| DXCM | 17 | 17 | 17 | 8 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| DY | 8 | 0 | 8 | 9 | 9 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| EBAY | 18 | 19 | 19 | 19 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ECL | 19 | 19 | 5 | 18 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ED | 17 | 17 | 17 | 16 | 16 | 1 | Revenues |
| EFX | 10 | 18 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| EHC | 10 | 8 | 18 | 19 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| EIX | 19 | 19 | 3 | 6 | 18 | 2 | Revenues |
| EL | 18 | 18 | 12 | 13 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ELAN | 10 | 0 | 10 | 11 | 9 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ELF | 7 | 7 | 7 | 8 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| EME | 18 | 18 | 18 | 17 | 17 | 4 | Revenues+SalesRevenueNet |
| EMR | 19 | 0 | 19 | 18 | 18 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ENS | 12 | 18 | 18 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| ENSG | 10 | 17 | 17 | 18 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ENTG | 17 | 17 | 17 | 2 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| EOG | 19 | 19 | 19 | 7 | 18 | 2 | Revenues |
| EPAM | 16 | 16 | 16 | 17 | 15 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| EQT | 10 | 19 | 13 | 18 | 18 | 0 | Revenues |
| ES | 17 | 17 | 15 | 16 | 16 | 0 | Revenues |
| ESAB | 6 | 6 | 6 | 5 | 5 | 0 | Revenues |
| ETN | 16 | 10 | 8 | 15 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ETR | 10 | 19 | 17 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| EVRG | 10 | 10 | 10 | 9 | 9 | 0 | Revenues |
| EW | 18 | 10 | 5 | 18 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| EXC | 18 | 18 | 5 | 17 | 17 | 6 | Revenues |
| EXE | 4 | 4 | 4 | 18 | 18 | 6 | Revenues |
| EXEL | 17 | 17 | 17 | 10 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| EXLS | 10 | 17 | 17 | 16 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| EXP | 10 | 16 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| EXPD | 19 | 19 | 19 | 18 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| EXPE | 18 | 18 | 18 | 17 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| EXPO | 17 | 17 | 17 | 18 | 16 | 0 | Revenues |
| FANG | 9 | 16 | 16 | 14 | 15 | 0 | Revenues |
| FAST | 19 | 19 | 19 | 20 | 18 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FCFS | 17 | 0 | 17 | 16 | 16 | 3 | Revenues |
| FCN | 18 | 18 | 18 | 19 | 17 | 0 | Revenues |
| FCX | 15 | 19 | 0 | 18 | 18 | 0 | Revenues+SalesRevenueNet |
| FDS | 17 | 17 | 17 | 18 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| FDX | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| FE | 19 | 19 | 19 | 18 | 18 | 3 | Revenues+SalesRevenueNet |
| FFIV | 18 | 18 | 18 | 0 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FHI | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| FICO | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FIS | 10 | 19 | 19 | 18 | 18 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax |
| FIVE | 16 | 16 | 16 | 17 | 15 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FIX | 17 | 17 | 13 | 16 | 16 | 2 | Revenues+SalesRevenueNet |
| FLS | 19 | 19 | 19 | 17 | 18 | 0 | Revenues+SalesRevenueNet |
| FND | 11 | 11 | 11 | 12 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FOUR | 8 | 8 | 6 | 7 | 7 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| FOX | 10 | 0 | 0 | 9 | 9 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| FOXA | 10 | 0 | 0 | 9 | 9 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| FSLR | 18 | 19 | 19 | 20 | 18 | 3 | Revenues+SalesRevenueNet |
| FTI | 11 | 11 | 11 | 11 | 11 | 3 | Revenues+SalesRevenueNet |
| FTNT | 17 | 17 | 17 | 18 | 16 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| FTV | 12 | 12 | 4 | 11 | 12 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| G | 10 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GAP | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+SalesRevenueNet |
| GATX | 18 | 0 | 18 | 18 | 17 | 4 | Revenues |
| GD | 19 | 19 | 19 | 20 | 18 | 4 | Revenues |
| GDDY | 10 | 13 | 13 | 12 | 12 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| GE | 19 | 6 | 19 | 20 | 18 | 16 | Revenues |
| GEF | 10 | 17 | 17 | 16 | 16 | 2 | SalesRevenueNet |
| GEHC | 5 | 5 | 5 | 4 | 4 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| GEN | 19 | 19 | 18 | 18 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| GEV | 4 | 4 | 4 | 3 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| GGG | 18 | 18 | 11 | 4 | 17 | 0 | Revenues+SalesRevenueNet |
| GHC | 18 | 18 | 18 | 8 | 17 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GILD | 19 | 19 | 19 | 18 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| GIS | 10 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GLW | 10 | 19 | 19 | 18 | 18 | 0 | Revenues |
| GM | 16 | 16 | 16 | 16 | 16 | 2 | Revenues |
| GME | 10 | 19 | 19 | 4 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GMED | 16 | 16 | 16 | 17 | 15 | 0 | Revenues+SalesRevenueNet |
| GNRC | 14 | 17 | 17 | 18 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| GNTX | 9 | 18 | 18 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| GOOG | 13 | 13 | 13 | 14 | 12 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GOOGL | 13 | 13 | 13 | 14 | 12 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GPC | 10 | 12 | 13 | 18 | 20 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| GPN | 10 | 10 | 10 | 10 | 10 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GRMN | 19 | 19 | 17 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| GWRE | 16 | 16 | 0 | 17 | 15 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| GWW | 19 | 19 | 19 | 19 | 19 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| GXO | 7 | 7 | 7 | 6 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| H | 17 | 0 | 17 | 16 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| HAE | 5 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| HAL | 11 | 19 | 19 | 18 | 18 | 0 | Revenues+SalesRevenueNet |
| HALO | 17 | 17 | 17 | 18 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| HAS | 16 | 18 | 18 | 13 | 17 | 5 | Revenues+SalesRevenueNet |
| HCA | 7 | 0 | 17 | 16 | 16 | 0 | Revenues |
| HD | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| HGV | 11 | 0 | 11 | 12 | 10 | 0 | Revenues |
| HII | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+SalesRevenueNet |
| HIMS | 7 | 7 | 7 | 8 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| HL | 6 | 18 | 18 | 19 | 17 | 0 | Revenues |
| HLI | 8 | 13 | 7 | 2 | 13 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| HLNE | 10 | 0 | 11 | 10 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| HLT | 14 | 14 | 14 | 13 | 13 | 3 | Revenues |
| HON | 19 | 4 | 19 | 18 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| HOOD | 7 | 0 | 7 | 7 | 6 | 2 | Revenues |
| HPE | 13 | 13 | 13 | 12 | 12 | 2 | Revenues |
| HQY | 14 | 14 | 14 | 15 | 13 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| HRB | 5 | 7 | 5 | 6 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| HSIC | 15 | 18 | 18 | 17 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| HSY | 19 | 14 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| HUBB | 18 | 18 | 18 | 17 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| HWM | 10 | 11 | 19 | 18 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| HXL | 10 | 18 | 3 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| IBKR | 18 | 0 | 7 | 17 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| IBM | 19 | 0 | 11 | 18 | 18 | 4 | Revenues |
| ICE | 15 | 15 | 15 | 14 | 14 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| IDA | 18 | 18 | 18 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IDCC | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IDXX | 18 | 18 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IEX | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+SalesRevenueNet |
| IFF | 10 | 17 | 11 | 17 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ILMN | 18 | 18 | 18 | 19 | 17 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| INCY | 17 | 17 | 10 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| INDV | 4 | 4 | 4 | 5 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| INGR | 10 | 18 | 14 | 17 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| INTC | 19 | 19 | 19 | 20 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| INTU | 18 | 18 | 18 | 19 | 17 | 7 | Revenues+SalesRevenueNet |
| IP | 19 | 7 | 19 | 18 | 18 | 8 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IPGP | 17 | 17 | 17 | 17 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IQV | 15 | 15 | 15 | 2 | 15 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| IR | 11 | 11 | 11 | 7 | 11 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ISRG | 19 | 19 | 19 | 20 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IT | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ITW | 19 | 19 | 0 | 0 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| IVZ | 19 | 19 | 18 | 18 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| J | 12 | 19 | 19 | 20 | 18 | 0 | Revenues |
| JAZZ | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| JBHT | 10 | 18 | 18 | 19 | 17 | 0 | Revenues |
| JCI | 19 | 9 | 19 | 20 | 18 | 10 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| JKHY | 18 | 18 | 18 | 19 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| JNJ | 10 | 6 | 16 | 0 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| KBR | 19 | 19 | 18 | 18 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| KDP | 18 | 18 | 18 | 17 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| KEX | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| KEYS | 7 | 13 | 4 | 12 | 12 | 0 | Revenues+SalesRevenueNet |
| KKR | 10 | 0 | 17 | 9 | 4 | 2 | Revenues |
| KLAC | 18 | 6 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| KMB | 19 | 19 | 19 | 18 | 18 | 5 | Revenues+SalesRevenueNet |
| KMI | 17 | 17 | 17 | 16 | 16 | 2 | Revenues |
| KNF | 5 | 5 | 5 | 6 | 5 | 0 | Revenues |
| KO | 10 | 19 | 19 | 18 | 18 | 2 | Revenues |
| KR | 10 | 19 | 19 | 18 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| KTOS | 17 | 17 | 16 | 2 | 16 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| KVUE | 5 | 5 | 5 | 6 | 4 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| LDOS | 10 | 10 | 10 | 19 | 17 | 5 | Revenues |
| LECO | 15 | 18 | 8 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| LEN | 18 | 12 | 18 | 17 | 17 | 1 | Revenues |
| LFUS | 9 | 17 | 6 | 16 | 16 | 0 | Revenues+SalesRevenueNet |
| LHX | 6 | 6 | 7 | 7 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| LII | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+SalesRevenueNet |
| LIN | 10 | 10 | 10 | 9 | 9 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| LITE | 5 | 14 | 13 | 14 | 13 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LIVN | 10 | 10 | 10 | 11 | 11 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| LLY | 19 | 0 | 19 | 16 | 18 | 4 | Revenues |
| LNT | 18 | 18 | 18 | 19 | 17 | 4 | Revenues |
| LNTH | 13 | 13 | 9 | 14 | 12 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| LOPE | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LOW | 19 | 12 | 14 | 15 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LRCX | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LSCC | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LSTR | 17 | 18 | 18 | 17 | 17 | 2 | Revenues |
| LULU | 18 | 18 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| LUV | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| LVS | 18 | 18 | 18 | 17 | 18 | 4 | Revenues+SalesRevenueNet |
| LYV | 17 | 17 | 17 | 16 | 16 | 3 | Revenues |
| M | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MA | 19 | 19 | 7 | 18 | 18 | 2 | Revenues+SalesRevenueNet |
| MANH | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MAR | 19 | 19 | 19 | 18 | 18 | 2 | Revenues |
| MAT | 19 | 19 | 19 | 20 | 18 | 4 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MCD | 19 | 19 | 19 | 20 | 18 | 4 | Revenues |
| MCHP | 19 | 19 | 19 | 20 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MCO | 19 | 19 | 19 | 18 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| MDLZ | 19 | 19 | 19 | 18 | 18 | 4 | Revenues |
| MDT | 14 | 14 | 14 | 15 | 13 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MEDP | 11 | 11 | 11 | 12 | 11 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| META | 16 | 16 | 16 | 15 | 15 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| MGM | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MIDD | 18 | 18 | 18 | 19 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MKC | 18 | 18 | 18 | 8 | 17 | 2 | Revenues+SalesRevenueNet |
| MKSI | 18 | 18 | 18 | 19 | 17 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MLI | 10 | 18 | 18 | 17 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| MLM | 18 | 18 | 18 | 17 | 17 | 9 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MMM | 19 | 19 | 19 | 18 | 18 | 2 | Revenues+SalesRevenueNet |
| MNST | 10 | 18 | 0 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| MO | 19 | 19 | 19 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MOG-A | 18 | 17 | 18 | 18 | 17 | 2 | Revenues+SalesRevenueNet |
| MORN | 18 | 18 | 11 | 9 | 17 | 2 | Revenues+SalesRevenueNet |
| MP | 7 | 7 | 7 | 8 | 7 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| MRK | 10 | 0 | 19 | 18 | 18 | 4 | Revenues |
| MRSH | 4 | 19 | 19 | 0 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| MSA | 18 | 12 | 18 | 13 | 17 | 2 | Revenues |
| MSCI | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| MSFT | 19 | 19 | 19 | 19 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MSI | 19 | 19 | 19 | 18 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| MTD | 18 | 0 | 18 | 19 | 17 | 0 | Revenues+SalesRevenueNet |
| MTDR | 16 | 16 | 16 | 17 | 15 | 2 | Revenues |
| MTN | 17 | 17 | 17 | 16 | 16 | 0 | Revenues+SalesRevenueNet |
| MTSI | 16 | 16 | 16 | 17 | 15 | 2 | Revenues+SalesRevenueNet |
| MTZ | 17 | 0 | 17 | 16 | 16 | 2 | Revenues |
| MU | 17 | 17 | 17 | 16 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| MUR | 19 | 11 | 19 | 19 | 18 | 8 | Revenues |
| MZTI | 10 | 18 | 18 | 19 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| NBIX | 17 | 17 | 17 | 18 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NCLH | 7 | 15 | 15 | 14 | 14 | 0 | Revenues |
| NDAQ | 18 | 18 | 18 | 17 | 17 | 7 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NDSN | 18 | 18 | 18 | 18 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NEE | 6 | 19 | 18 | 20 | 18 | 0 | Revenues |
| NEM | 14 | 0 | 19 | 18 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NEU | 18 | 18 | 18 | 18 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NFG | 10 | 18 | 18 | 3 | 17 | 0 | Revenues |
| NFLX | 19 | 19 | 19 | 20 | 18 | 0 | Revenues |
| NI | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NJR | 7 | 18 | 18 | 18 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| NKE | 19 | 0 | 19 | 20 | 18 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NOC | 19 | 19 | 19 | 19 | 18 | 2 | Revenues+SalesRevenueNet |
| NOV | 19 | 19 | 19 | 18 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NOVT | 17 | 17 | 17 | 16 | 16 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NOW | 14 | 14 | 14 | 15 | 15 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NSC | 19 | 19 | 9 | 10 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NTAP | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NTNX | 11 | 11 | 11 | 12 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NVDA | 19 | 19 | 19 | 20 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NVST | 9 | 9 | 9 | 8 | 9 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| NVT | 10 | 10 | 10 | 0 | 10 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| NWE | 5 | 5 | 5 | 6 | 5 | 0 | Revenues |
| NWS | 15 | 0 | 15 | 14 | 14 | 4 | Revenues |
| NWSA | 15 | 0 | 15 | 14 | 14 | 4 | Revenues |
| NXPI | 9 | 9 | 9 | 8 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| NXST | 16 | 17 | 17 | 18 | 16 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| NYT | 18 | 18 | 18 | 17 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| OC | 14 | 12 | 18 | 17 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ODFL | 0 | 18 | 18 | 19 | 17 | 0 | — |
| OGE | 18 | 18 | 5 | 17 | 17 | 0 | Revenues |
| OKTA | 10 | 11 | 11 | 12 | 10 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| OLED | 17 | 17 | 17 | 18 | 16 | 2 | Revenues |
| OLLI | 10 | 13 | 13 | 14 | 12 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ON | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ONTO | 17 | 17 | 17 | 18 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| OPCH | 10 | 15 | 15 | 20 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ORCL | 19 | 19 | 19 | 18 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ORLY | 18 | 18 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| OSK | 4 | 4 | 8 | 5 | 5 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| OTIS | 8 | 8 | 8 | 7 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| OVV | 9 | 9 | 9 | 10 | 8 | 0 | Revenues |
| OXY | 19 | 0 | 17 | 9 | 18 | 8 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PANW | 15 | 15 | 15 | 14 | 14 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| PATH | 7 | 7 | 7 | 8 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PAYX | 19 | 19 | 3 | 20 | 18 | 4 | Revenues |
| PCAR | 18 | 0 | 19 | 19 | 18 | 0 | Revenues |
| PCG | 19 | 19 | 3 | 18 | 18 | 0 | Revenues |
| PCTY | 15 | 15 | 15 | 16 | 14 | 0 | Revenues |
| PEG | 19 | 19 | 19 | 9 | 18 | 3 | Revenues |
| PEGA | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PEN | 13 | 13 | 13 | 14 | 12 | 0 | Revenues+SalesRevenueNet |
| PEP | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+SalesRevenueNet |
| PFE | 10 | 0 | 19 | 18 | 18 | 8 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PG | 19 | 19 | 19 | 0 | 19 | 3 | Revenues+SalesRevenueNet |
| PH | 19 | 18 | 17 | 18 | 19 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PHM | 18 | 0 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| PINS | 9 | 9 | 9 | 10 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PKG | 18 | 18 | 18 | 19 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PLNT | 13 | 13 | 13 | 11 | 12 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PLTR | 8 | 8 | 8 | 9 | 7 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PM | 19 | 19 | 19 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PNR | 18 | 18 | 18 | 5 | 17 | 5 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PNW | 18 | 18 | 3 | 17 | 17 | 2 | Revenues+SalesRevenueNet |
| PODD | 17 | 17 | 17 | 18 | 16 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| POOL | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+SalesRevenueNet |
| POR | 10 | 18 | 9 | 6 | 17 | 0 | Revenues |
| POST | 10 | 16 | 16 | 17 | 15 | 2 | Revenues |
| PPG | 19 | 15 | 19 | 18 | 18 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PPL | 17 | 19 | 10 | 16 | 18 | 5 | Revenues |
| PR | 9 | 9 | 9 | 10 | 10 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PSKY | 2 | 2 | 2 | 2 | 2 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PSN | 9 | 9 | 9 | 8 | 8 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PTC | 18 | 18 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| PWR | 10 | 19 | 9 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| PYPL | 13 | 13 | 13 | 14 | 12 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| Q | 3 | 0 | 0 | 2 | 2 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| QCOM | 19 | 19 | 19 | 14 | 18 | 4 | Revenues |
| QLYS | 16 | 16 | 16 | 17 | 15 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| R | 18 | 0 | 18 | 19 | 17 | 5 | Revenues |
| RBA | 10 | 13 | 13 | 12 | 12 | 2 | Revenues |
| RBC | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+SalesRevenueNet |
| RCL | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| REGN | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| RGLD | 5 | 5 | 5 | 5 | 5 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| RH | 10 | 16 | 16 | 17 | 15 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| RL | 17 | 18 | 18 | 18 | 17 | 4 | Revenues+SalesRevenueNet |
| RMBS | 10 | 18 | 14 | 19 | 17 | 0 | SalesRevenueNet |
| RMD | 18 | 18 | 18 | 16 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ROK | 19 | 3 | 19 | 20 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ROL | 10 | 7 | 7 | 18 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| ROP | 19 | 19 | 19 | 13 | 18 | 3 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ROST | 18 | 4 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| RPM | 18 | 0 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| RRC | 19 | 0 | 18 | 19 | 18 | 7 | Revenues |
| RRX | 7 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| RSG | 19 | 19 | 19 | 18 | 18 | 5 | Revenues+SalesRevenueNet |
| RTX | 19 | 19 | 19 | 18 | 18 | 6 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| RVTY | 18 | 18 | 18 | 19 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| SARO | 4 | 4 | 4 | 5 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SBUX | 19 | 19 | 19 | 20 | 18 | 0 | Revenues+SalesRevenueNet |
| SCI | 18 | 18 | 18 | 17 | 17 | 4 | Revenues+SalesRevenueNet |
| SEIC | 18 | 18 | 18 | 9 | 16 | 0 | Revenues |
| SFM | 10 | 15 | 15 | 15 | 14 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SGI | 18 | 18 | 18 | 15 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SHC | 7 | 6 | 7 | 6 | 6 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SHW | 19 | 14 | 19 | 14 | 19 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SJM | 0 | 18 | 18 | 19 | 18 | 0 | — |
| SLAB | 18 | 18 | 3 | 18 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| SLB | 19 | 11 | 19 | 18 | 18 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SLGN | 18 | 12 | 8 | 8 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| SMG | 18 | 18 | 18 | 15 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| SNA | 18 | 18 | 18 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| SNDK | 4 | 4 | 4 | 5 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SNPS | 18 | 18 | 18 | 17 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SO | 19 | 19 | 3 | 14 | 18 | 0 | Revenues |
| SOLS | 3 | 0 | 3 | 2 | 2 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SOLV | 4 | 4 | 4 | 5 | 3 | 0 | Revenues |
| SON | 18 | 18 | 18 | 17 | 17 | 5 | Revenues+SalesRevenueNet |
| SPGI | 19 | 19 | 19 | 18 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SPXC | 19 | 19 | 12 | 18 | 18 | 11 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| SR | 7 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| SRE | 16 | 0 | 5 | 17 | 17 | 2 | Revenues |
| SSD | 18 | 18 | 13 | 18 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ST | 17 | 17 | 17 | 18 | 16 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| STE | 10 | 10 | 10 | 9 | 9 | 4 | Revenues |
| STRL | 17 | 17 | 6 | 16 | 16 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| STX | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| STZ | 10 | 18 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SW | 4 | 4 | 4 | 3 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| SWK | 18 | 12 | 18 | 17 | 17 | 8 | Revenues+SalesRevenueNet |
| SYK | 19 | 19 | 19 | 13 | 18 | 1 | Revenues+SalesRevenueNet |
| SYNA | 18 | 18 | 18 | 19 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| T | 19 | 19 | 19 | 0 | 18 | 4 | Revenues |
| TAP | 10 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TDG | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+SalesRevenueNet |
| TDY | 18 | 18 | 17 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TECH | 18 | 18 | 17 | 19 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TEL | 19 | 19 | 12 | 10 | 18 | 5 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TER | 18 | 18 | 18 | 19 | 17 | 2 | Revenues |
| TEVA | 11 | 11 | 11 | 10 | 10 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TEX | 19 | 19 | 19 | 12 | 18 | 9 | Revenues+SalesRevenueNet |
| TGT | 19 | 10 | 6 | 18 | 18 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| THC | 10 | 18 | 3 | 17 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TJX | 11 | 9 | 14 | 15 | 18 | 0 | Revenues+SalesRevenueNet |
| TKO | 5 | 5 | 3 | 4 | 4 | 2 | Revenues |
| TKR | 10 | 18 | 18 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TLN | 2 | 2 | 2 | 3 | 3 | 0 | Revenues |
| TMO | 19 | 19 | 3 | 19 | 18 | 5 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TMUS | 18 | 18 | 18 | 19 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TNL | 18 | 18 | 18 | 17 | 17 | 1 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TOL | 1 | 18 | 18 | 17 | 17 | 0 | Revenues |
| TPL | 8 | 8 | 8 | 9 | 7 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax |
| TPR | 19 | 19 | 19 | 20 | 19 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TREX | 17 | 17 | 17 | 18 | 16 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TRGP | 10 | 17 | 17 | 16 | 17 | 2 | Revenues |
| TRMB | 18 | 18 | 18 | 17 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TROW | 10 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TSCO | 9 | 18 | 18 | 19 | 17 | 0 | Revenues |
| TSLA | 17 | 17 | 17 | 18 | 16 | 2 | Revenues |
| TT | 19 | 19 | 19 | 18 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TTD | 10 | 12 | 12 | 13 | 11 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| TTEK | 10 | 18 | 0 | 16 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TTWO | 17 | 17 | 17 | 17 | 17 | 1 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TWLO | 12 | 12 | 12 | 13 | 11 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| TXN | 19 | 19 | 19 | 18 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| TXNM | 10 | 18 | 10 | 17 | 17 | 0 | Revenues |
| TXT | 18 | 0 | 18 | 19 | 17 | 0 | Revenues |
| TYL | 17 | 17 | 17 | 18 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| UAL | 18 | 18 | 18 | 19 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| UBER | 9 | 9 | 9 | 8 | 8 | 2 | Revenues |
| UHS | 16 | 18 | 18 | 17 | 17 | 4 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ULS | 4 | 4 | 4 | 3 | 3 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| ULTA | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+SalesRevenueNet |
| UNP | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| UPS | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| URI | 17 | 17 | 17 | 16 | 16 | 0 | Revenues+SalesRevenueNet |
| UTHR | 18 | 18 | 5 | 18 | 17 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| V | 19 | 19 | 19 | 6 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| VC | 10 | 0 | 15 | 16 | 16 | 0 | Revenues+SalesRevenueNet |
| VEEV | 15 | 15 | 15 | 16 | 14 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| VICR | 17 | 17 | 17 | 16 | 16 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| VLTO | 5 | 5 | 5 | 4 | 5 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| VMC | 19 | 19 | 19 | 20 | 18 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| VMI | 18 | 18 | 5 | 17 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| VNOM | 3 | 3 | 3 | 2 | 2 | 0 | Revenues |
| VRSK | 10 | 17 | 17 | 18 | 16 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| VRSN | 19 | 19 | 6 | 18 | 18 | 4 | Revenues |
| VRT | 9 | 7 | 9 | 10 | 9 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| VRTX | 18 | 18 | 17 | 16 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| VST | 9 | 9 | 9 | 10 | 10 | 0 | Revenues |
| VTRS | 8 | 8 | 0 | 2 | 7 | 0 | Revenues |
| VVV | 11 | 11 | 11 | 12 | 10 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| VZ | 19 | 19 | 19 | 0 | 18 | 0 | Revenues |
| WAB | 18 | 18 | 18 | 19 | 17 | 3 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WAT | 19 | 19 | 4 | 19 | 18 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WBD | 19 | 19 | 19 | 9 | 18 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WCC | 18 | 18 | 18 | 17 | 17 | 2 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WDAY | 16 | 16 | 16 | 17 | 15 | 4 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| WDC | 10 | 19 | 19 | 20 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax |
| WEC | 15 | 19 | 9 | 11 | 18 | 0 | Revenues |
| WEX | 18 | 18 | 18 | 18 | 17 | 2 | Revenues+SalesRevenueNet |
| WFRD | 11 | 14 | 14 | 13 | 13 | 0 | Revenues+SalesRevenueNet |
| WH | 10 | 10 | 10 | 11 | 10 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| WING | 13 | 13 | 13 | 14 | 12 | 0 | Revenues+SalesRevenueNet |
| WM | 19 | 19 | 19 | 18 | 18 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| WMB | 19 | 19 | 19 | 18 | 18 | 2 | Revenues |
| WMG | 14 | 14 | 14 | 15 | 15 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax |
| WMS | 10 | 14 | 14 | 13 | 14 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| WMT | 19 | 19 | 19 | 18 | 18 | 4 | Revenues |
| WSM | 18 | 17 | 18 | 19 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WSO | 18 | 18 | 18 | 17 | 17 | 0 | Revenues |
| WST | 18 | 18 | 8 | 9 | 17 | 0 | Revenues+RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WTRG | 19 | 18 | 19 | 19 | 19 | 6 | Revenues |
| WTS | 18 | 18 | 14 | 18 | 17 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WTW | 18 | 18 | 18 | 18 | 17 | 2 | Revenues |
| WWD | 18 | 0 | 18 | 12 | 17 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| WYNN | 11 | 18 | 18 | 17 | 17 | 0 | Revenues+SalesRevenueNet |
| XOM | 0 | 0 | 0 | 0 | 0 | 0 | — |
| XYL | 17 | 17 | 17 | 18 | 16 | 0 | Revenues+SalesRevenueNet |
| XYZ | 12 | 12 | 12 | 13 | 11 | 0 | Revenues+SalesRevenueNet |
| YETI | 10 | 10 | 10 | 9 | 9 | 0 | RevenueFromContractWithCustomerExcludingAssessedTax |
| YUM | 19 | 19 | 19 | 1 | 18 | 0 | Revenues |
| ZBH | 10 | 19 | 19 | 18 | 18 | 2 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ZBRA | 18 | 18 | 18 | 19 | 17 | 5 | RevenueFromContractWithCustomerExcludingAssessedTax+SalesRevenueNet |
| ZTS | 15 | 0 | 15 | 14 | 14 | 0 | Revenues+SalesRevenueNet |

## Verdikt (mechanisch)

Schwelle laut Auftrag: >=10 Jahre bei klar ueber der Haelfte der US-Titel (> 305 von 610).

- Auftrags-Konzeptliste: **364** Titel mit allen vier Reihen >=10 Jahre (59.7% aller US-Titel) → **REICHT**
- erweiterte Liste: **519** Titel mit allen vier Reihen >=10 Jahre (85.1% aller US-Titel) → **REICHT**

Diese Zeile ist arithmetisch, nicht abschliessend. Die Bewertung steht darunter.

<!-- HANDGESCHRIEBEN AB HIER — ein erneuter Lauf laesst dies stehen -->

## Empfehlung

**Kurz: Die Datengrundlage trägt. Die Dimension allein löst das gemeldete Problem trotzdem
nicht — sie erreicht fünf der acht Preisnehmer nicht.**

### 1. Die Abdeckung reicht — aber nicht mit der Konzeptliste aus dem Auftrag

Mit der beauftragten Liste erreichen **364 von 610 US-Titeln (59,7 %)** alle vier benötigten
Reihen über zehn zusammenhängende Jahre. Das liegt über der Hälfte, aber nicht „klar" darüber.
Mit einer um vier Tags erweiterten Liste sind es **519 (85,1 %)**.

Die Differenz ist **keine Datenlücke, sondern eine Namenslücke**. Vier Tags erklären sie fast
vollständig:

| fehlender Tag | betroffene Titel |
|---|---|
| `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` | 86 |
| `ProfitLoss` | 70 |
| `IncomeLossFromContinuingOperationsBeforeIncomeTaxes…NoncontrollingInterest` | 59 |
| `RevenueFromContractWithCustomerIncludingAssessedTax` | 21 |

Wer die Dimension baut, sollte die erweiterte Liste nehmen. Eine Einschränkung dazu: beim Umsatz
mischt eine erweiterte Liste im Grenzfall Definitionen (Gesamtumsatz gegen Umsatz aus Verträgen).
Für eine *Stetigkeits*-Kennzahl ist das vertretbar — gemessen wird die Form der Reihe, nicht ihr
Niveau —, für eine Bewertungskennzahl wäre es das nicht.

### 2. Die konkrete Hürde ist nicht die Abdeckung, sondern die Reichweite

Von den acht Preisnehmern erreichen nur drei zehn Jahre: **HL (15), NEM (14), MU (17)**.
Die anderen fünf nicht:

- **EDV.L, ANTO.L** — keine SEC-Registranten (London), über EDGAR grundsätzlich unerreichbar.
- **SNDK (4), RGLD (5), TPL (8)** — zu junge XBRL-Historie. Sandisk ist ein Spin-off von 2025,
  Texas Pacific Land wurde 2021 von einem Trust in eine Corporation umgewandelt.

Nach dem vorgeschlagenen Umgang „neutral setzen, nicht bestrafen" stünden diese fünf **unverändert
in der Liste**. Die Dimension träfe MU, NEM und HL und ließe fünf von acht durch. Das ist der
Punkt, an dem eine Aggregatzahl (85 % Abdeckung) und die Wirkung auseinanderfallen: die
Preisnehmer sind überdurchschnittlich oft junge oder europäische Titel — genau die Population,
die EDGAR nicht abdeckt.

Zur Gegenprobe: auf der anderen Seite verhält sich die Dimension wie erwünscht. **MEDP (11),
FAST (19), FICO (18)** bekämen alle eine echte Stetigkeit und blieben oben. Mit ihnen gingen
allerdings auch **PLTR (8) und ABNB (7)** auf neutral — ebenfalls junge Titel, ebenfalls
unbestraft.

### 3. Ein Viertel des Universums ist strukturell außerhalb

**233 von 843 gescorten Titeln (27,6 %)** sind keine SEC-Registranten. Eine EDGAR-gestützte
Dimension ist damit dauerhaft asymmetrisch: der europäische Teil des Universums bekäme nie eine
Stetigkeit. Das ist kein Argument dagegen — es deckt sich mit der bereits getroffenen
Entscheidung, vor ESAP (September 2027) keine EU-Quellenschicht zu bauen. Es heißt nur, dass
„neutral" für ein Viertel der Titel der Dauerzustand ist und entsprechend sichtbar sein muss.

### Empfehlung

1. **Phase 2a ist machbar und richtig** — die Datengrundlage trägt, und die drei Kriterien
   (Jahre mit Umsatzwachstum, Schwankung der operativen Marge, schlechteste Eigenkapitalrendite)
   sind aus den gemessenen Reihen berechenbar. Die Spec sollte die erweiterte Konzeptliste
   festschreiben, nicht die aus dem Auftrag.
2. **„Neutral" darf nicht wie „unauffällig" aussehen.** Ein Titel ohne Historie bekommt einen
   sichtbaren Marker in der Crosshits-Tabelle. Ohne das verschiebt die Dimension das Problem,
   statt es zu lösen — und zwar unsichtbar.
3. **2a allein schließt den gemeldeten Fall nicht.** Fünf der acht Preisnehmer bleiben unberührt.
   Die Preisnehmer-Kennzeichnung aus Phase 2b ist deshalb **kein Ersatz für 2a, sondern die
   Ergänzung, die genau diese Lücke schließt**: sie hängt am yfinance-Feld `industry`, ist von
   EDGAR unabhängig und damit auch für EDV.L und ANTO.L verfügbar. Mein Vorschlag ist, beides zu
   bauen — 2b zuerst, weil es klein ist und die acht gemeldeten Fälle vollständig erreicht, 2a
   danach, weil es die allgemeine Ursache adressiert.
4. **Eine Stellschraube zur Entscheidung:** Eine harte 10-Jahres-Hürde lässt TPL (8), PLTR (8)
   und ABNB (7) durch. Eine abgestufte Regel — ab sieben Jahren bewerten, aber den erreichbaren
   Höchstwert deckeln — würde diese drei erfassen, analog zum bestehenden `consistency_cap`.
   Das ist eine Design-Entscheidung, keine Datenfrage; die Zahlen dafür stehen oben.

### Wiederverwendbar

`consistency_ratio(revenues)` in `app/screener/growth_consistency.py:11` nimmt bereits eine
Umsatzreihe entgegen und ist quellenblind. Eine Zehn-Jahres-Reihe aus EDGAR ließe sich dort
einsetzen, ohne eine neue Kennzahl zu definieren — das erste der drei Kriterien existiert also
schon, es sieht heute nur vier Jahre.

### Was diese Messung nicht sagt

- Sie misst **Vorhandensein**, nicht Richtigkeit. Ob die Werte je Jahr stimmen, ist an der
  Stichprobe (FAST, NEM, XOM) exemplarisch prüfbar, nicht flächendeckend.
- 20-F-Filer (US-notierte Foreign Private Issuers unter `ifrs-full`) sind **nicht** gemessen —
  das wäre eine eigene Konzeptliste.
- `BLD`, `EA` und `GTLS` haben keine CIK in `company_tickers.json` und fehlen deshalb ganz;
  drei von 610, für die Quote unerheblich, aber genannt statt verschwiegen.
