---
title: Phase 1 — Pareto-B.2 (Substanz-Hebel für Investitions-Vorcheck)
status: aktiv (Start 2026-05-27)
created: 2026-05-26
last_updated: 2026-05-27
phase_lead: Stephan Müller
exit_criterion: drei reale Watchlist-Deep-Dives mit voll-ausgebauten Dossiers, Stephan bewertet Vorcheck-Nützlichkeit positiv
estimated_aufwand: 10–14 Sessions, gestreckt 2–3 Monate
predecessor_phases: Punkt 5 (Anchor-Tracing) abgeschlossen, Stages 1–5 + Intermediate-Items-Diagnose in `main`
successor_phase: Phase 2 — Vollausbau (zurückgestellt, siehe `PROJEKTSTAND.md ## Phase 2`)
---

> **Plan-Doc (`docs/superpowers/plans/`), konsolidiert 2026-05-27** aus dem Phase-1-Pareto-B.2-Quelldokument (`stef-vault/Inbox`, created 2026-05-26). Inhalt übernommen; beim Konsolidieren nur Frontmatter-Datum gesetzt (`status`/`last_updated` → 2026-05-27) und eine Überschrift präzisiert (Akzeptanz-Gate). PROJEKTSTAND-Anker: `## Phase 1 — Pareto-B.2 (aktiv)`.

# Phase 1 — Pareto-B.2

## Ziel

FisherScreen Tool B von „funktional vollständigem Tool-B-MVP" zu „substanz-tragender Vorcheck-Basis für reale Investitionsentscheidungen" entwickeln. Pareto-Variante des ursprünglichen B.2-Scopes: nur die Hebel, die systemische Substanz-Lücken in der Fisher-Stufe-1-Methodik schließen, der Rest wandert in Phase 2.

## Kontext

Tool B ist seit B.1-Abschluss (2026-05-18) CLI-produktiv und liefert vollständige 6-Stage-Pipeline-Dossiers. Punkt 5 (2026-05-21 bis 2026-05-26) hat die Filing-Parser-Substanz für F1/F2/F3/F4/F6 strukturell gelöst und in Stage 5 gegen reale Dossiers verifiziert. Vintage-Anzeige im Synthesis-Prompt ist mit 2a.2 implementiert (2026-05-26).

Mit diesem Stand liefert Tool B substanzielle Bewertung für ~8 von 15 Fisher-Punkten hart, ~3 weiche, ~4 dünn. Die dünnen sind systematisch dieselben (P8/P9/P11/P15 — Management/Vergütung/Governance/Integrität), weil die Substanz dafür **nicht im 10-K oder 20-F liegt**, sondern in separaten Dokumenten (US: DEF-14A-Proxy + Form-4-Insider; EU: Vergütungsbericht + Director's-Dealings).

Phase 1 schließt die systematischen Substanz-Lücken für US-Filer (DEF-14A-Proxy, Form-4-Insider) plus den fehlenden historischen Bewertungs-Kontext (5J-Range), plus die zwei kleinen offenen Tier-1-Items (2a.3 Vintage-Confidence, 2a.1c Marker-Spec-Gap).

## Scope — die fünf Sub-Phasen plus Akzeptanz-Gate

### Phase 1.1 — 2a.3 Globaler Vintage-Confidence-Faktor

**Aufwand:** 1–2 Sessions plus bezahlter Akzeptanz-Lauf (~$2–8).

**Was:** Confidence-Bewertung pro Fisher-Punkt wird systematisch an Filing-Alter gekoppelt — vintage-sensitive Punkte (z.B. Margen, Wettbewerb, Outlook) bekommen ab Threshold-Überschreitung einen Confidence-Cap.

**Warum vor B.2-Substanz:** Konsolidierung des Stage-3-Validator-Pfades. Klein genug, dass es nicht den Phase-1-Schwung verzögert, aber wichtig genug, dass es nicht aufgeschoben werden sollte.

**Vorbereitung:** Kickoff-Prompt liegt vor (separate Session), Brainstorm-Phase (Enforcement-Mechanismus, Schwellen, vintage-sensitive Punkte) muss vor TDD geklärt sein.

### Phase 1.2 — 2a.1c Marker-Spec-Gap

**Aufwand:** 1 Session.

**Was:** Modell erfindet vereinzelt Source-Marker außerhalb der SOURCES-Whitelist (z.B. `[peer_comparison]`). Whitelist erweitern oder strikter Collapse für unbekannte Marker.

**Warum hier:** Kleines isoliertes Hygiene-Item, sauberer Abschluss vor B.2-Substanz.

### Phase 1.3 — 5J-Bewertungs-Range

**Aufwand:** 3–4 Sessions plus bezahlter Akzeptanz-Lauf.

**Was:** Bewertungsblock im Synthesis-Prompt + Dossier zeigt historische Multiples (KGV, EV/EBIT, FCF-Yield) über 5 Jahre, mit Vergleichs-Anker („heute KGV 11, 5J-Median 21, untere 25-Perzentile 12.1").

**Warum als erstes B.2-Item:** Kleinster Aufwand der drei Pareto-Hebel, wirkt auf jeden zukünftigen Tool-B-Lauf, kein neuer Filing-Source-Pfad nötig. Hoher Sofort-Wert.

**Architektur-Voraussicht:**
- yfinance liefert historische `info`-Daten nicht stabil → Implementierung über Quarterly-Financials + Multiples-Rückrechnung.
- FX-Handling (DKK/EUR/USD historisch) ist die Stolperfalle.
- Historische Multiples landen als neues Sub-Feld in `QuantSnapshot`.
- Bewertungsblock-Renderer erweitert sich um 5J-Median-Vergleich.

**Akzeptanz:** Tool-B-Re-Run gegen NOVO + GOOGL. NOVO-Dossier zeigt „TTM 10.9 vs 5J-Median 21.4" oder analoge Substanz.

### Phase 1.4 — Insider-Transactions (Form-4)

**Aufwand:** 2 Sessions plus bezahlter Akzeptanz-Lauf.

**Was:** Tool B zieht zusätzlich zu 10-K/20-F die Form-4-Insider-Filings desselben Filers über EDGAR. Synthesis-Prompt erhält neuen Block „Insider-Transactions (letzte 12 Monate)". P11/P15-Reasoning bezieht Insider-Signale ein.

**Warum als zweites:** Sehr klein, eigenes Mini-Subsystem (Form-4 XML, klar strukturiert), greift nicht in bestehende Pipeline ein. Liefert eine zusätzliche Datenschicht.

**Architektur-Voraussicht:**
- EDGAR-Endpunkt: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=...&type=4`.
- XML-Parser, einfacher als HTML-Filings.
- Schwellen-Definition: signifikant = Single-Transaktion > $1M ODER CEO/CFO-Transaktion unabhängig vom Wert (in Brainstorm-Phase finalisieren).

**Form-4 ist US-spezifisch:** Foreign Private Issuers (20-F-Filer wie SAP, NOVO, ASML) sind Section-16-exempt und filen kein Form-4. Für diese Filer greift Phase 1.4 nicht — siehe „Bewusste Lücken" unten.

**Akzeptanz:** Tool-B-Re-Run gegen einen US-Filer mit bekannten Insider-Transactions (Ticker im Akzeptanz-Schritt von Stephan gewählt). Dossier zeigt Insider-Sektion, P11/P15-Reasoning bezieht sie ein.

### Phase 1.5 — DEF-14A-Proxy-Source-Layer (US-Filer)

**Aufwand:** 5–7 Sessions plus bezahlter Akzeptanz-Lauf.

**Was:** Tool B zieht zusätzlich zum 10-K das Proxy-Statement (DEF 14A) desselben US-Filers. P8/P9/P11/P15 werden für US-Filer von Inferenz- auf Hard-Source-Bewertung gehoben.

**Warum als drittes:** Größter Pareto-Aufwand, aber technisch erschlossen (gleicher EDGAR-Pfad, gleicher Anchor-Resolver aus Punkt 5, gleicher Synthesis-Pfad). Maximaler Substanz-Hebel der drei.

**Architektur-Voraussicht:**
- Zweiter EDGAR-Pull pro Deep-Dive: `DEF 14A`-Form-Type.
- Filing-Parser-Wiederverwendung: 100%, weil DEF-14A strukturell wie 10-K HTML-iXBRL ist.
- Anchor-Resolver lernt neue Item-Liste: `_FORM_ITEMS["DEF 14A"]` = {1, 2, 3, ...}. Verifikation gegen 3–4 reale Proxy-Filings.
- Synthesis-Prompt: neue Filing-Sections, Cite-Format `[DEF 14A §X]`, Validator-Regex um Form-Type-Branch erweitern.
- Cache-Layer: paralleler Cache für Proxy-Filings, gleiche TTL-Logik.

**DEF-14A ist US-Domestic-Form:** 20-F-Filer (Foreign Private Issuers) filen kein DEF-14A. Ihre Vergütungs-/Governance-Substanz steht in nationalen Vergütungsberichten — siehe „Bewusste Lücken".

**Akzeptanz:** Tool-B-Re-Run gegen 3 reale Watchlist-US-Kandidaten. Dossiers zeigen Proxy-grounded P8/P11/P15-Reasoning. Cite-Grounding-Probe (analog Stage 5) verifiziert.

### Phase 1.6 — Phase-1-Akzeptanz-Gate

**Aufwand:** 1 Session (Memo-Dokument plus Stephan-Beurteilung).

**Was:** Drei reale Watchlist-Deep-Dives mit voll-ausgebauten Dossiers (Vintage + 5J-Range + Insider + Proxy für US-Filer; Vintage + 5J-Range plus manueller 20-F-Routine für EU-Filer). Stephan beurteilt: nützlich genug für reale Kaufentscheidungen?

**Outcome-Klassen:**
- **Ja** → Phase 1 erfolgreich. PROJEKTSTAND-Eintrag, Tag, Phase 2 wird offizielles aktuelles Backlog.
- **Nein, eine konkrete Lücke** → Phase 1.7 mit nachgezogenem Hebel (z.B. „10-Q-Quartals-Update war doch nötig", oder „Vergütungsbericht-Layer für 20-F-Filer").
- **Nein, mehrere Lücken** → Phase-1-Definition war zu eng, Re-Scoping.

**Memo-Dokument:** `docs/superpowers/diagnostic-reports/2026-XX-XX-phase-1-acceptance.md` mit drei Dossiers, Bewertung pro Dossier, Phase-2-Trigger-Entscheidung.

## Sequenz und Disziplin

**Reihenfolge ist sequenziell, nicht parallel:** 1.1 → 1.2 → 1.3 → 1.4 → 1.5 → 1.6. Jede Sub-Phase eigener Branch, eigener Akzeptanz-Lauf (wo vorgesehen), eigener Merge.

**Warum sequenziell:** Stage-2-Lesson v aus Punkt 5 ist relevant — bei LLM-Output-Pipelines nie mehrere Datenkontext-Änderungen ohne Zwischen-Re-Run bündeln, sonst ist Wirkungs-Zuordnung nicht möglich. „Hat das Dossier besser geworden weil 5J-Range oder weil Proxy?" ist nur durch sequenzielle Implementation beantwortbar.

**Anti-Patterns (aus Stage-Lessons übernommen):**

- **Scope-Drift während Sub-Phase:** Während 1.5 (Proxy-Layer) fällt auf „eigentlich bräuchten wir auch EU-Native nebenbei". → Stop, erst 1.5 abschließen, dann entscheiden ob neue Idee in Phase 1 oder Phase 2 gehört.
- **Akzeptanz-Gate-Verwässerung:** Das Gate (1.6) ist „drei reale Deep-Dives, Stephan beurteilt nützlich". Nicht „Tests grün". Test-grün ist Voraussetzung, nicht Akzeptanz.
- **Sub-Phasen-Parallelisierung:** Versuchung, 1.3 und 1.4 parallel zu machen weil beide klein. Nicht tun.

## Bewusste Lücken (Honest-Label)

### Vergütungs-Substanz und Insider für 20-F-Filer (SAP, NOVO, ASML, Allianz, BASF, Siemens, etc.)

DEF-14A-Proxy-Pipeline aus 1.5 ist US-Domestic-Form-spezifisch und greift bei 20-F-Filern nicht. Form-4-Insider-Reporting aus 1.4 greift ebenfalls nicht (Foreign Private Issuers sind Section-16-exempt).

**Kompensation:** Manuelle Routine pro 20-F-Deep-Dive.
- Vergütungsbericht von IR-Website der Firma (HGB §162 verlangt jährliche Veröffentlichung bei deutschen AGs, Pflicht-Inhalt: individualisierte Vorstands-Vergütung, Performance-Komponenten, Aktien-Programme).
- Director's-Dealings vom Bundesanzeiger oder DGAP-Newsfeed (§15a WpHG / Art. 19 MAR, letzte 12 Monate).
- Geschätzter Zusatz-Aufwand: 15 Min pro 20-F-Ticker.

**Backlog-Marker für Phase 2:** „Vergütungs-/Director's-Dealings-Layer für 20-F-Filer". Re-Evaluation, wenn die manuelle Routine zur operativen Last wird (z.B. >5 EU-Deep-Dives pro Monat).

### EU-Filer ohne US-ADR (z.B. reine MDAX/SDAX-Werte ohne SEC-Reporting)

Pareto-B.2 erreicht diese Filer nicht. Tool B liefert für sie weiterhin Honest-Label-Dossiers (`fallback_used+missing`) oder Filing-not-found-Fehler.

**Kompensation:** Keine in Phase 1. Wenn diese Werte auf der Watchlist landen, manuelle Bundesanzeiger-Recherche.

**Backlog-Marker für Phase 2:** „EU-Native-Source-Layer" als kohärente Initiative zusammen mit dem 20-F-Vergütungs-Layer (External-Document-Source-Layer).

### Aktualität jenseits Annual Report

Tool B greift auf das letzte vollständige Annual-Report-Jahr zu (10-K für US, 20-F für EU). Zwischenzeitliche Quartals-Performance, Halbjahres-Updates, jüngste Konsens-Revisionen oder 8-K-Material-Events sind im Dossier nicht enthalten.

**Kompensation:** Manuelle Vor-Kauf-Routine pro Ticker.
- Letzter Quartalsbericht (10-Q für US, Halbjahresbericht für EU) — 5–10 Min Lesen.
- Konsens-Drift letzte 90 Tage über Yahoo Finance oder Trading-Plattform.
- 8-K-/Ad-hoc-Filings der letzten 60 Tage über SEC-EDGAR oder DGAP.

**Backlog-Marker für Phase 2:** „10-Q-Quartals-Update-Pipeline".

### Sektor-Spezifika

Tool B ist generisch implementiert. Für Banken/Versicherer (Net Interest Margin statt Op-Margin), REITs (FFO statt EPS), Biotech (Pipeline-Stage statt TTM-Margins) sind die Standard-Multiples teilweise irreführend.

**Kompensation:** Sektor-Fit-Frage manuell **vor** Tool-B-Lauf entscheiden. Wenn Wert nicht generic-bewertbar, Tool-B-Output als „nur P12-P15 verwendbar" einordnen.

**Backlog-Marker für Phase 2:** Optional „Sektor-Specific-Heuristics" (niedrige Priorität, vermutlich nicht in Phase 2 sondern später).

### Fisher-Stufe-2-Substanz (P7–P10)

Management-Tiefe, Vertriebsstärke, F&E-Effektivität, Buchhaltungs-Disziplin können auch nach Pareto nicht aus Filings gegrounded werden. Fisher selbst delegiert diese in tiefes Scuttlebutt.

**Kompensation:** Methodisch unvermeidbar. Tool B liefert hier weiterhin Inferenz mit Confidence-Cap. Echte Bewertung in der 1–2 ernsthaften-Kandidaten-Stufe durch manuelle Recherche (Wettbewerber-Befragung, ehemalige Mitarbeiter, Branchen-News, Konferenz-Calls).

**Backlog-Marker:** Keiner. Das ist keine Tool-Lücke, das ist Methodik-Grenze.

## Phase-1-Exit-Kriterium

Phase 1 ist erfolgreich abgeschlossen, wenn:

1. **Alle fünf Sub-Phasen sind in `main` gemergt** und nach Workflow-Standard (Brainstorm → Plan → TDD → Review → Akzeptanz-Lauf wo vorgesehen) durchgelaufen.
2. **Drei reale Watchlist-Deep-Dives in Phase 1.6 sind absolviert.** Tickers von Stephan gewählt aus realer 6-Monats-Kandidaten-Liste. Mindestens ein US-Filer und ein 20-F-Filer dabei.
3. **Stephan bewertet das aggregierte Dossier-Substanz-Niveau positiv** im Phase-1.6-Memo-Dokument. „Positiv" heißt: für mindestens zwei der drei Dossiers ist die Aussage „dieses Dossier wäre für mich eine substanzielle Entscheidungsgrundlage für Pass-oder-Vertiefen" zustimmungsfähig.
4. **Bewusste-Lücken-Routinen-Marker sind dokumentiert** für die 20-F-Filer-Vergütungs-/Insider-Lücke und die Aktualitäts-Lücke. Operative Routine ist klar.

Wenn Punkt 3 nicht erfüllt: Phase 1.7 mit konkretem Re-Scope, **nicht** „Phase 2 starten und Stille".

## Geschätzter Aufwand

| Sub-Phase | Sessions | Gestreckt |
|---|---|---|
| 1.1 — 2a.3 | 1–2 | 1 Woche |
| 1.2 — 2a.1c | 1 | wenige Tage |
| 1.3 — 5J-Bewertungs-Range | 3–4 | 2 Wochen |
| 1.4 — Insider-Form-4 | 2 | 1 Woche |
| 1.5 — DEF-14A-Proxy | 5–7 | 3–4 Wochen |
| 1.6 — Akzeptanz-Gate | 1 | wenige Tage |
| **Summe** | **13–17** | **8–10 Wochen** |

**Bezahlte Akzeptanz-Läufe:** vier nach Sub-Phasen 1.1, 1.3, 1.4, 1.5, je ~$2–8. Plus drei reale Watchlist-Läufe in 1.6 je ~$2–8. Gesamt-Budget Phase 1: ~$20–50.

## Voraussetzungen vor Phase-1-Start

- [x] **Punkt 5 abgeschlossen** (Stages 1–5 + Intermediate-Items-Diagnose, alles in `main`).
- [x] **2a.2 Vintage-Anzeige im Prompt** (in `main`, Commit `e804a75` / Merge `e292237`).
- [ ] **Watchlist-Realitäts-Check** geschrieben (5–10 Tickers, 20-F-vs-10-K-Verteilung, plausibilisiert Phase-1-Scope).
- [ ] **PROJEKTSTAND umstrukturiert** mit Phase-1- und Phase-2-Block.
- [ ] **Phase-1-Memory angelegt** (`phase-1-pareto-scope.md` oder ähnlich) als Session-Eröffnungs-Anker.
- [ ] **Decisions-Log-Eintrag** zur Option-A-Pareto-Entscheidung.

## Verweise

- **Vorgänger-Architektur:** `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md` (V3-Spec)
- **Punkt-5-Plan-Doc:** `docs/superpowers/plans/punkt-5-filing-parser.md`
- **Stage-5-Akzeptanz-Report:** `docs/superpowers/diagnostic-reports/2026-05-26-punkt5-acceptance.md`
- **Intermediate-Items-Diagnose:** `docs/superpowers/diagnostic-reports/2026-05-26-intermediate-items-diagnose.md`
- **PROJEKTSTAND:** `PROJEKTSTAND.md ## Phase 1 — Pareto-B.2 (aktiv)`
- **Stage-Lessons (Vault):**
  - `latent-parsing-edges-llm-input.md`
  - `workflow-rhythm-staged-gated.md`
  - `subagent-commit-hygiene.md`

## Phase-2-Vorausschau (zurückgestelltes Backlog, nicht Phase-1-Scope)

Nach erfolgreicher Phase 1 wird das aktuelle Phase-2-Backlog zur aktiven Phase. Inhalt grob (Detail in PROJEKTSTAND):

- **External-Document-Source-Layer** als kohärente Initiative: US DEF-14A-Layer für tiefere Substanz + EU-Native-Source-Layer (Bundesanzeiger/Companies House/AMF) + 20-F-Vergütungsbericht-Layer + IR-PDF-Fallback.
- **10-Q-Quartals-Update-Pipeline** für strukturelle Aktualitäts-Lösung.
- **Tool-B-Hygiene:** Dynamische ADR-Resolution (OpenFIGI/SEC), Filing-Cache-Migration nach GCS, `response_schema` E2.
- **Tool-A-Phase-2-Backlog:** Portfolio Hold-Check (sobald reale Kauf-Snapshots existieren), Cost-Caps im Code, `has_active_enforcement`, Idempotenz-Lock, Cloud Run Jobs.
- **Universum-Erweiterung:** optional, nach Phase 2.

**Geschätzter Phase-2-Aufwand:** 20–30 Sessions, gestreckt 4–6 Monate. Re-Evaluation der Phase-2-Scope-Definition nach Phase-1-Abschluss.