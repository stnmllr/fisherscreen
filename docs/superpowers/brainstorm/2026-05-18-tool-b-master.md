> **Pareto-Restriktion 2026-05-27:** Der ursprüngliche B.2-Scope dieses
> Master-Brainstorms (Hard-Scuttlebutt-Breite, EU-Voll-Abdeckung,
> dynamische ADR-Resolution, IR-PDF-Fallback, 10-Q+Insider,
> 5J-Bewertungs-Range, `response_schema` E2, DOM-Filing-Parser,
> historical-cache→GCS) wurde auf eine Pareto-Variante reduziert und in
> sechs sequenzielle Sub-Phasen 1.1–1.6 aufgeteilt. Aktueller Plan:
> `docs/superpowers/plans/2026-05-27-phase-1-pareto-b2.md`. Inhalte dieses
> Brainstorms bleiben historisch gültig; zurückgestellte Punkte (EU-Native,
> 20-F-Vergütung, 10-Q, dynamische ADR-Resolution, `response_schema`,
> GCS-Cache) sind im PROJEKTSTAND-Phase-2-Block aufgeführt.

# Tool B (Deep Dive) — Master-Brainstorm

**Datum:** 2026-05-18 (rev4)
**Status:** Struktur-Brainstorm. Vier ADRs gesetzt. Strukturiert mehrere Folge-Sessions
(eine Phase pro Session, jede mit eigenem Brainstorm + Plan + TDD).
**Rev1:** Sechs Strukturkorrekturen — Insider-Transaktionen aus B.1 ADR-3 entfernt
(Foreign-Private-Issuer-Asymmetrie), nach B.2 verschoben (Form 4 + EU MAR Art. 19 /
PDMR gemeinsam); Filing-Cache als ADR-4 hochgezogen (Lokal-FS mit TTL); Pre-Flight-Checks
separiert (§7a); B.0 als eigener Setup-Vorlauf bestätigt; §8-Risiko #1↔#2 verknüpft;
Querverweis-Konsolidierung (§7-/§8-/ADR-Renumber).
**Rev2:** Wortlaut-Konsolidierung — §6-B.2-Stub an §4-Tabelle angeglichen
(Insider-Transaktionen US/EU explizit gleichlautend); Commit-Message-Akkuratheits-Korrektur
(nicht-vorhandener Doku-Inhalt entfernt).
**Rev3:** Reasoning-Pflicht pro Fisher-Punkt eingeführt (2-3 Sätze Prosa + Quellen-Marker
[Filing-Section]/[Quant-Snapshot]/[Inferenz]), Inferenz-Confidence-Cap auf 🟡,
Post-Hoc-Quellen-Validator gegen Section-Halluzination, Dossier-Render-Format auf
Mini-Blöcke umgestellt.
**Rev4:** Pre-Flight-Checks §7a beide erledigt (2026-05-18): `gemini-2.5-pro` nutzbar
→ B.1-Synthesis-Default; Filing-Cache `cache/filings/` angelegt + `.gitignore`-Regel.
Spike-Skript `scripts/preflight_gemini_pro.py`.
**Vorbild-Format:** `docs/superpowers/brainstorm/2026-05-11-phase-1-structure.md`
**Referenz-Spec:** `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`
(insb. §1.1, §1.2, §5, §6.1, §6.3)

> Dieses Dokument terminiert **nicht** in einem Implementierungsplan. Es ist der
> Master-Plan über Tool B. Jede Phase B.x bekommt ihre **eigene** Brainstorm- →
> Plan- → TDD-Session. Die nächste Session startet mit dem `brainstorming`-Skill
> auf **Phase B.1** (siehe §10).

---

## 1. Zweck & Abgrenzung zu Tool A

Tool A (Monthly Screener) ist seit 2026-05-16 produktiv: ein **breiter, automatischer**
Lauf über das ~1.389-Ticker-Universum, der monatlich via Cloud Scheduler fünf
Dimensions-Listen + Crosshits + Changes nach Obsidian schreibt. Tool A beantwortet
*„Wer ist überhaupt Fisher-tauglich?"* (V3 §2, Topf „Universum").

Tool B (Deep Dive) ist das **tiefe, manuelle** Pendant: ein On-Demand-CLI-Aufruf für
**einen** Ticker, der ein einzelnes Markdown-Dossier gegen Fishers 15 Punkte erzeugt.
Tool B beantwortet *„Passt dieser eine Titel wirklich?"* (V3 §2, Topf „Watchlist").

Die Verbindung ist die **Stufe-3-Diskussion** (V3 §1.1 / §1.2): Tool-A-Output →
Diskussion mit Claude (Vorgaben aus §1.2 gegen Recall-Bias) → 0–5 Deep-Dive-Kandidaten
→ manueller Tool-B-Trigger. Tool B ist strikt **Pull** (V3 §11 Prinzip 7): nie
automatisch, nie batch über die ganze Watchlist.

| Eigenschaft | Tool A | Tool B |
|---|---|---|
| Kardinalität | gesamtes Universum (~1.389) | 1 Ticker pro Aufruf |
| Kadenz | monatlich automatisch | on demand, manuell |
| Auslöser | Cloud Scheduler → HTTP | lokaler CLI-Aufruf (**ADR-2**) |
| Hosting | Cloud Run (europe-west3) | lokal in-process (**ADR-2**) |
| LLM | Gemini Flash Lite, Hard-Caps | Gemini Pro/Flash Lite, per-Deepdive-Cap |
| Quellen | yfinance + EDGAR (nur US-CIK) | EDGAR 10-K/20-F + (später) Hard/Soft Scuttlebutt |
| Output | 3 Aggregat-Files/Monat | 1 Dossier/Ticker (V3 §5.3) |
| Tiefe | Quant + Gemini-Dimensions-Score | 15-Punkte-Synthesis auf Primär-Filing |

Tool B ist bewusst **kein** zweites Tool A: keine Listen, kein Composite, kein
Scheduler, kein Multi-Ticker-Lauf.

---

## 2. Architektur-Grundsätze

Tool B erbt die bewährte Tool-A-Infrastruktur und ergänzt sie um drei Tool-B-spezifische
Grundsätze. Die strukturellen Weichen sind in §3 als ADRs (ADR-1 bis ADR-4) ausformuliert.

**Geerbt aus Tool A (CLAUDE.md, V3 §11):**

1. **Service-Layer als Thin Wrapper + Dependency-Injection.** Jeder externe Call
   (EDGAR, Gemini, Firestore) läuft durch eine injizierbare Service-Klasse. Kein
   direkter API-Call aus der Deep-Dive-Logik. Tests mocken via DI, kein Netzwerk in
   Unit-Tests.
2. **AppError-Hierarchie.** `FisherScreenError` → `DataSourceError` / `GeminiError` /
   `FilterConfigError`, ergänzt um **`DeepDiveError`** (ungültiger/nicht auflösbarer
   Ticker, fehlendes Filing). Fail loud, niemals still schlucken.
3. **Firestore-Caching-Pattern + `dev_`-Prefix**, strukturiertes JSON-Logging
   (`severity`, Trace-Korrelation), `FISHERSCREEN_*`-Env-Var-Prefix, Secrets lokal
   via `.env` (nie auf Cloud Run — hier ohnehin lokal, **ADR-2**).
4. **pytest mit DI ab Task 1**, Aufruf via `uv run python -m pytest`
   (WatchGuard-EPDR-Workaround, CLAUDE.md), 90%-Coverage-Threshold zentral in
   `[tool.pytest.ini_options]`.
5. **Gemini-503/429-Retry** wird aus Tool A wiederverwendet (tenacity, Backoff
   1s/4s/16s, max 4, `reraise=True` — TODO #11, PR #3). Kein Neubau.

**Neu für Tool B:**

6. **Per-Deepdive-Token-Cap als Hard-Limit im Code.** CLAUDE.md sagt „Tool B hat keine
   API-Beschränkungen — Kosten durch manuelle Bedienung implizit gekappt". Das gilt
   nicht mehr, wenn **ein einziger** Synthesis-Call ein 200+-Seiten-20-F bei
   Pro-Tarif einliest. Daher: `FISHERSCREEN_DEEPDIVE_TOKEN_CAP`, `count_tokens` vor
   dem Call (Tool-A-Pattern), Abbruch mit `GeminiError` bei Überschreitung,
   `logging.warning` bei 80 %. Premortem-Risiko #1 (§8 #1).
7. **Quellen-Transparenz im Dossier — vorhanden UND fehlend.**
   Eine fehlende Quelle wird sichtbar im Dossier markiert, nicht hinter
   einem selbstsicher aussehenden Text versteckt (z. B. „Soft Scuttlebutt:
   folgt Phase B.3", „Sprach-Analyse: folgt Phase B.4",
   „Insider-Transaktionen: folgt Phase B.2"). **Zusätzlich** wird jede
   vorhandene Quelle pro Fisher-Punkt attributiert: jede Bewertung trägt
   eine Begründung (2-3 Sätze Prosa, max 70 Wörter) und am Ende einen
   Quellen-Marker — eine von [Filing-Section] (z. B. `[20-F §5]`),
   [Quant-Snapshot] (z. B. `[yfinance, 5J]`) oder [Inferenz] (Gemini
   kombiniert mehrere Quellen ohne direkten Zitat-Pfad). Bei [Inferenz]
   ist Confidence maximal 🟡, nie 🟢 — als Code-Regel erzwungen, nicht
   als Soft-Konvention. Lehre aus Tool-A-Pivot 2026-05-15
   (Bibliothek vs. Briefing) und negative-filters-status.md §4.
8. **Trusted-Sources-only in B.1 → Subagent-Isolation aufgeschoben.** V3 §5.4
   (Reader/Scorer/Writer-Isolation) ist durch *untrusted* Inputs (Glassdoor, Reddit,
   Earnings-Q&A) motiviert. B.1 nutzt nur regulierte Emittenten-Filings (10-K/20-F).
   Damit ist Subagent-Isolation in B.1 **nicht** nötig und wird mit den Soft-Quellen
   gemeinsam in **B.3** eingeführt — nie Soft-Quellen ohne Isolation.

---

## 3. Architecture Decision Records

Diese vier ADRs sind **gesetzt** (Entscheidung Stephan, 2026-05-18). Sie werden in
Folge-Sessions nicht neu aufgerollt, sondern als Rahmen vorausgesetzt.

### ADR-1 — EU-Primärquelle im MVP = SEC 20-F via ADR-Pfad

**Kontext.** Der EU-CIK-Blindfleck (negative-filters-status.md §3.1): `edgar_client.get_cik`
löst CIKs ausschließlich über die US-zentrierte `company_tickers.json` auf. Im
1.389-Ticker-Universum sind ~485 EU-Ticker (Heuristik `"." in ticker`) ohne CIK —
für sie liefert die EDGAR-Pipeline strukturell **nichts**. Der vorgeschlagene
MVP-Ticker Novo Nordisk (NOVO-B.CO) ist genau dieser Fall. Ohne Lösung gäbe es für
den ersten echten Deep Dive kein Primär-Filing — und damit nichts, woran sich die
Synthesis-Qualität (der eigentliche Zweck des Durchstichs) prüfen ließe.

**Entscheidung.** EU-Ticker werden über eine **statische ADR-Mapping-Tabelle**
(YAML/JSON, ~Top-50 EU-ADRs) auf den US-ADR-Ticker und dann auf die SEC-CIK gemappt.

- Beispiel: `NOVO-B.CO → NVO → CIK 0000353278`
- Form-Type-Weiche im Filing-Parser: `10-K | 20-F`
- 20-F-Sections für Scuttlebutt: **Item 4** (Information on the Company),
  **Item 5** (Operating & Financial Review), **Item 18** (Financial Statements)
- Bewusst **nicht** im MVP abgedeckt: reine EU-Titel **ohne** US-ADR
  → Phase B.2/B.3 via IR-PDF-Fallback.
- Dynamische ADR-Resolution (OpenFIGI, SEC Company Search) ist eine **B.2**-Optimierung,
  kein MVP-Bestandteil.

**Konsequenzen.**
- Der erste echte Deep Dive kann zum Mai-Top-1 (Novo Nordisk) erfolgen — die
  stärkste Validierung, weil es der real ausgeworfene Spitzenkandidat ist.
- Wartungsschuld: ~50 statische Einträge. Vertretbar, weil Deep Dives selten/manuell
  sind und die Tabelle versioniert + per Test gegen Format gesichert wird.
- 20-F ≠ 10-K: nur jährlich (keine 10-Q-Quartale), andere Item-Struktur. Der
  Filing-Parser braucht von Tag 1 zwei Form-Type-Pfade (Task B.1-4).
- CIK-Drift (Delisting, Re-Registrierung) ist ein Premortem-Risiko (§8 #4).

**Verworfene Alternativen.**
| Alternative | Verworfen weil |
|---|---|
| IR-PDF-Parsing schon im MVP | Neue fragile Fähigkeit (Layout-Drift), verzögert den Durchstich; gehört in B.2/B.3 |
| MVP-Ticker auf US-Titel wechseln | Erstes echtes Dossier nicht zum Mai-Top-1 → schwächere Validierung; Mai-Lauf war ohnehin EU-only |
| EDGAR-leer akzeptieren + Quant-only | Zu dünn, um die Synthesis-Qualität zu prüfen — genau das ist der Zweck des Durchstichs |

### ADR-2 — Aufrufmodus = CLI-lokal in-process

**Kontext.** V3 nennt sowohl HTTP-Endpoint `/run/deepdive` (§5.1, §6.1) als auch CLI
(`fisherscreen deepdive ASML.AS`). Tool A ist Cloud-Run-only — richtig, weil es
*scheduled* ist. Tool B ist **manuell und interaktiv** (Pull, V3 §11 Prinzip 7):
man läuft einen Deep Dive, liest ihn, justiert, läuft erneut.

**Entscheidung.** Tool B läuft in B.1 **vollständig lokal in-process**.

- Entrypoint: `uv run fisherscreen deepdive <TICKER>` bzw. `python -m fisherscreen.deepdive`
- **Kein** Cloud Run für Tool B in B.1.
- V3 §6.1 (Single-Service-Konsistenz mit Tool A) wird **bewusst aufgegeben**.
- HTTP-Endpoint `/run/deepdive` ist **nicht** in B.1, sondern optional ab **B.5+**,
  gebunden an einen konkreten Use-Case (z. B. Obsidian-Trigger oder Auto-Dossier
  für Tool-A-Top-1).

**Begründung / Konsequenzen.**
- Cloud-Run-Timeout-Risiko entfällt: ein 200+-Seiten-20-F-Synthesis-Call kann lange
  laufen; Tool A musste den Timeout schon auf 3600s heben.
- Dev-Iteration: ~5–10 Min/Deploy × erwartete 50+ Iterationen in den ersten Wochen
  → lokal spart Stunden und vermeidet den Deploy-Feedback-Loop ganz.
- Firestore-Read lokal via ADC (`gcloud auth application-default login`) — identisch
  zum Phase-1-Local-Dev-Setup. Secrets lokal via `.env` (CLAUDE.md erlaubt das lokal).
- Auflage: Die CLI nutzt denselben Service-Layer wie Tool A, damit ein späterer
  HTTP-Wrapper (B.5+) trivial bleibt — die Geschäftslogik kennt den Aufrufmodus nicht.

**Verworfene Alternativen.**
| Alternative | Verworfen weil |
|---|---|
| HTTP-on-Cloud-Run zuerst | Timeout-Risiko + langsame Dev-Iteration; kein Architektur-Zwang zur Tool-A-Kollokation |
| CLI **und** HTTP gemeinsam in B.1 | Scope-Bloat im MVP; HTTP hat (noch) keinen konkreten Use-Case |

### ADR-3 — Sprach-/Tonalitätsanalyse = eigene Phase B.4

**Kontext.** V3 §5.2 spezifiziert zwei Sprach-Analysen. **Analyse-1**
(Letter-to-Shareholders-Ton-Shift) hat eine verfügbare Quelle (CEO-Brief im
Geschäftsbericht/Filing). **Analyse-2** (Earnings-Call-Q&A-Defensiveness) hat
**keine geklärte Quelle** — V3 §13 Punkt 7 ist explizit offen (SEC EDGAR hat keine
Transkripte). Sprach-Analyse ist zugleich das halluzinationsanfälligste Stück
(V3 §9: „Sprach-Analyse halluziniert / over-interpretiert").

**Entscheidung.** B.1 enthält **keine** Sprach-Analyse.

- Fisher-Punkte 14/15 (Offenheit/Integrität) bekommen im B.1-Dossier
  einen 🔴-Confidence-Marker mit explizitem Verweis „Insider-Transaktionen
  folgen Phase B.2, Sprach-/Tonalitäts-Analyse folgt Phase B.4". Quant-
  Proxies (Buyback-Disziplin aus Cash-Flow-Statement, Verwässerung aus
  Shares-Outstanding-Historie) sind primär Punkt-3/8/9-Signale und
  werden dort verortet, nicht in 14/15.
- **B.4** ist ein eigener Spike mit zwei Sub-Tasks:
  - **B.4a** — Letter-to-Shareholders-Korpus (5 Jahre zurück), Quellen-Klärung
    (Filing-Embed vs. IR-PDF), Ton-Shift-Metrik.
  - **B.4b** — Earnings-Call-Q&A-Transkript-Quelle klären (Seeking Alpha,
    Motley Fool, AlphaSense, Quartr — V3 §13 Pkt 7).

*Notiz Insider-Daten:* SEC Form 4 (US-Insider-Meldungen) ist für den
MVP-Kandidaten Novo Nordisk strukturell nicht verfügbar — Foreign Private
Issuers sind von Section 16 ausgenommen. EU-Pendant ist MAR Art. 19 /
PDMR-Meldungen (Finanstilsynet/BaFin/etc.), heterogen über nationale
Aufsichten verteilt, keine einheitliche API. Beides gehört konzeptionell
zusammen in B.2, nicht aufgeteilt.

**Konsequenzen.**
- B.1–B.3 sind von der ungeklärten Transkript-Quelle **entkoppelt** und können
  dadurch nicht von ihr blockiert werden.
- Das B.1-Dossier ist ehrlich über die 14/15-Lücke (Grundsatz §2.7).
- Subagent-Isolation (V3 §5.4) ist analog aufgeschoben (Grundsatz §2.8) — sie ist
  durch dieselben untrusted Inputs motiviert.

**Verworfene Alternativen.**
| Alternative | Verworfen weil |
|---|---|
| Analyse-1 schon in B.1 | Verbreitert den MVP, braucht 5J-Brief-Korpus + Quellen-Entscheidung, verwässert den Durchstich-Fokus |
| Volle Sprach-Analyse in B.1 | Durch ungeklärte Transkript-Quelle (Analyse-2) blockiert |

### ADR-4 — Filing-Cache = Lokal-FS mit TTL

**Kontext.** EDGAR-Filings sind MB-groß (10-K oft 5–15 MB, 20-F bis 30 MB).
Firestore-Dokumente sind auf 1 MiB begrenzt — Filings passen strukturell nicht
rein. GCS wäre möglich, ist aber Overkill für einen CLI-lokalen Workflow.

**Entscheidung.** Filings werden lokal auf dem Filesystem gecacht unter
`cache/filings/<cik>/<accession_number>.txt` mit konfigurierbarer TTL
(Default 30 Tage, Env-Var `FISHERSCREEN_FILING_CACHE_TTL_DAYS`).
Cache-Verzeichnis in `.gitignore`.

**Konsequenzen.**
- Konsistent mit ADR-2 (CLI-lokal in-process): kein Cloud-Storage-Roundtrip.
- Erneute Deep Dives desselben Tickers innerhalb der TTL sparen
  EDGAR-Call + Rate-Limit-Budget.
- Cache-Invalidierung trivial: `rmdir /s /q cache\filings\` (cmd.exe) oder Datei-Alter.
- Wenn je ein HTTP-Endpoint (B.5+) kommt, wird der Cache auf GCS
  migriert — kein B.1-Thema.

**Verworfene Alternativen.**
| Alternative | Verworfen weil |
|---|---|
| Firestore | 1-MiB-Doc-Limit, strukturelle Inkompatibilität |
| GCS | Overkill für CLI-lokal, zusätzliche Auth-Komplexität |
| Kein Cache | Wiederholte EDGAR-Calls verschwenden Rate-Limit-Budget |

---

## 4. Phasen-Übersicht B.0 – B.5+

| Phase | Scope | Akzeptanztest |
|---|---|---|
| **B.0** | Gerüst: CLI-Package-Skeleton, `output/Watchlist/`-Junction + GitHub-Push-Pfad, statische ADR-Tabelle (Seed: NOVO-Eintrag), `DeepDiveError`-Klasse, `compose.py`-Analog | `uv run fisherscreen deepdive --help` läuft; ADR-Tabelle lädt + Format-Test grün; Watchlist-Junction im Vault sichtbar |
| **B.1** | **Vertikaler Durchstich** (§5): ADR-Lookup → EDGAR-Pull → Filing-Parse → Quant-Join → Gemini-15-Punkte-Synthesis → Markdown-Dossier | Vollständiges Novo-Nordisk-Dossier (NOVO-B.CO) aus **einem** CLI-Aufruf; Stephan beurteilt Entscheidungs-Nützlichkeit |
| **B.2** | Hard-Scuttlebutt-Breite + EU-Voll-Abdeckung: dynamische ADR-Resolution (OpenFIGI/SEC-Search), IR-PDF-Fallback für reine EU-Titel, 10-Q (nur 10-K-Titel) + Insider-Transaktionen (SEC Form 4 für US-Titel + EU MAR Art. 19 / PDMR-Meldungen für EU-Titel, gemeinsam geplant um US/EU-Asymmetrie-Bruch zu vermeiden), Filing-Caching-Strategie | Deep Dive funktioniert für (a) reinen EU-Titel ohne ADR und (b) US-Titel mit Form-4-Insider-Daten |
| **B.3** | Soft Scuttlebutt **+ Subagent-Isolation** (gemeinsam): Apify Glassdoor/Kununu, Reddit, HN Algolia, Marketaux + Reader/Scorer/Writer (V3 §5.4), pydantic `extra="forbid"` | Dossier integriert ≥1 Soft-Quelle über isolierten Reader; Injection-Test (manipuliertes Review) bewegt den Score **nicht** |
| **B.4** | Sprach-/Tonalitätsanalyse (ADR-3): B.4a Letter-Ton-Shift, B.4b Q&A-Transkript-Quelle | Ton-Shift-Sektion für 3J-Briefe; Q&A-Defensiveness sobald Quelle geklärt |
| **B.5+** | Hardening: Cost-Cap-Politur, optionaler HTTP-Endpoint (use-case-gebunden), erste 1–3 echte Deep Dives end-to-end → V3-Workflow-Schluss | V3 §1.1-Workflow mindestens einmal vollständig für einen realen Kandidaten durchlaufen |

**Schätzung Session-Anzahl:** ~5 substanzielle Sessions (B.1–B.5), plus B.0 als
eigener kurzer Plan-Schritt vor B.1, ohne eigene Brainstorm-Runde.
Tool B ist damit ähnlich groß wie Tool A (dort 4 Sub-Phasen 1.1–1.4 + Infra), aber
**nicht** 8+: Soft Scuttlebutt + Sprach-Analyse sind echte eigene Phasen, kein
weiterer Zerfall nötig.

---

## 5. Phase B.1 im Detail — der vertikale Durchstich

**Ziel:** Aus einem einzigen CLI-Aufruf ein vollständiges, entscheidungs-nützliches
Dossier zu **einem** Ticker (Novo Nordisk, NOVO-B.CO; alternativ Mai-Top-1) — der
„Stufe-3-Diskussion bis erstes echtes Dossier"-Durchstich. Nur **trusted sources**
(reguliertes Emittenten-Filing), daher keine Subagent-Isolation (Grundsatz §2.8).

### 5.1 Pipeline-Stages

```
[1] ADR-Lookup          TICKER → (adr_ticker, cik, form_type)
        │                statische Tabelle (ADR-1). NOVO-B.CO → NVO → 0000353278 → 20-F
        ▼
[2] EDGAR-Pull          cik + form_type → jüngstes 10-K | 20-F (Volltext-Dokument)
        │                Reuse edgar_client (User-Agent, Rate-Limit aus Phase 1.2)
        ▼
[3] Filing-Parse        Roh-Filing → {section_key: text}
        │                10-K: Items 1,1A,7,7A,8 (+MD&A) · 20-F: Items 4,5,18
        ▼
[4] Quant-Join          TICKER → yfinance-Cache + Gemini-Dimensions-Scores
        │                aus Tool-A-Firestore (universe_cache, dev_gemini_scores).
        │                Fallback wenn nicht im letzten Lauf: Live-yfinance + Marker
        ▼
[5] Gemini-Synthesis    Filing-Sections + Quant → 15-Punkte-JSON
        │                Confidence-Marker 🟢/🟡/🔴 (V3 §1.2 Pkt 5),
        │                Per-Deepdive-Token-Cap (Grundsatz §2.6)
        ▼
[6] Markdown-Output     15-Punkte-JSON + Quant → Dossier (V3 §5.3)
                         output/Watchlist/<TICKER>_YYYY-MM-DD.md → Repo-Sync → Obsidian
```

**Design-Notizen (offene Feinheiten, in der B.1-Brainstorm-Session zu schärfen):**

- **Stage 4 Fallback.** Tool A schreibt Firestore nur für Vorfilter-Überlebende
  (~160). Novo Nordisk war Mai-Top-1 → Daten vorhanden. Für einen Ticker, der **nicht**
  im letzten Lauf war: WARNING loggen, Live-yfinance via bestehenden Service ziehen,
  im `source_coverage` als „live, nicht aus Monatslauf" markieren. Graceful
  degradation, nie Abbruch.
- **Stage 5 Modell.** V3 §7 will Gemini Pro für die Synthesis. Lesson (o)
  (PROJEKTSTAND): Pro/Preview-Modelle sind oft account-quota-beschränkt. → Modell
  über `FISHERSCREEN_DEEPDIVE_GEMINI_MODEL` konfigurierbar (Muster wie
  `FISHERSCREEN_GEMINI_MODEL` in Tool A), Default dokumentiert, Pro-Verfügbarkeit
  **vor** B.1-Implementierung verifizieren (→ §7a Pkt 1).
- **Stage 5 Kosten.** Section-Extraktion in Stage 3 ist nicht nur Strukturierung,
  sondern **Kostenhebel**: nur relevante Items in den Prompt, nicht das ganze
  200-Seiten-Dokument (Premortem #1).

### 5.2 Task-Aufteilung (Superpower-Stil, TDD je Task)

Jeder Task: Brainstorm-Konsens → Plan → TDD via Subagent (`backend-developer` für
Logik, `qa-engineer` für Fixtures/DI-Mocks; CLAUDE.md Multi-Agent). Tests via
`uv run python -m pytest`. Kein echter Netzwerk-Call in Unit-Tests.

| # | Task | Kern | Testing-Strategie |
|---|---|---|---|
| **B.1-1** | `DeepDiveRecord`-Datenmodell (Pydantic) | Felder: ticker, adr_ticker, cik, form_type, filing_sections, quant_snapshot, synthesis: 15× `{rating, confidence, reasoning, sources}` — Schema-Detail in B.1-6, source_coverage, generated_at. Analog `ScreenerRecord`. | Modell-Validierung, `extra="forbid"`, None-Toleranz für optionale Quant-Felder |
| **B.1-2** | ADR-Resolver-Service (`adr_resolver.py`) | Lädt statische YAML/JSON-Tabelle (ADR-1). `resolve(ticker) → (adr,cik,form_type)`. US-Ticker = Passthrough (10-K). | NOVO-B.CO → NVO/0000353278/20-F; US-Passthrough; unbekannt → `DeepDiveError` mit handlungsleitender Message; DI-mockbar |
| **B.1-3** | Filing-Fetcher (`edgar_client` erweitern) | Neue Methode `get_latest_annual_filing(cik, form_type)` — zieht **Volltext-Dokument** (nicht nur submissions.json-Flags). User-Agent + Rate-Limit aus Phase 1.2 wiederverwenden. | Gemockte EDGAR-Responses für 10-K **und** 20-F; fehlendes Filing → `DataSourceError`; Cache-Hit/Miss |
| **B.1-4** | Filing-Parser | Section-Extraktion mit Form-Type-Weiche. 10-K: Items 1,1A,7,7A,8. 20-F: Items 4,5,18. Normalisiert zu `{section_key: text}`, Längen-Caps. | Fixture-10-K + Fixture-20-F → erwartete Section-Keys; fehlende Section → geflaggt, **kein** Crash |
| **B.1-5** | Quant-Join | Liest yfinance-Cache + Gemini-Dimensions-Scores aus Tool-A-Firestore. Fallback Live-yfinance + `source_coverage`-Marker (§5.1 Notiz). | Cache-vorhanden-Pfad; Ticker-abwesend → Fallback-Pfad; Firestore via DI gemockt |
| **B.1-6** | Gemini-15-Punkte-Synthesis | Prompt aus Filing-Sections + Quant. Strukturiertes JSON pro Fisher-Punkt mit Feldern `{rating, confidence, reasoning, sources}`: `reasoning` ist 2-3 Sätze Prosa (max 70 Wörter), `sources` ist Array von Quellen-Markern (z. B. `['20-F §5', 'yfinance, 5J']` oder `['Inferenz']`). Confidence-Regel im Code erzwungen: enthält `sources` nur `['Inferenz']` → max 🟡, kein 🟢. Hard-Token-Cap + `count_tokens` vor Call + 503/429-Retry (Tool-A-Wrapper). Modell via Env-Var. **Post-Hoc-Quellen-Validator:** jede im `reasoning` zitierte Filing-Section (Regex auf `20-F §X` / `10-K §X`) wird gegen die tatsächlich an Gemini gesendeten Section-Keys geprüft; Mismatch → Source-Marker auf `['Inferenz']` herabstufen und Confidence entsprechend kappen, WARNING loggen (nicht hart fehlschlagen — Gemini-Halluzination ist erwartbarer Modus, kein Bug). | Gemini gemockt; Cap überschritten → `GeminiError`; Schema-Validierung des 15-Punkte-Outputs (pydantic, `extra='forbid'`, reasoning-Längen-Cap, sources-Array nicht leer); Inferenz-only → Confidence-Downgrade-Test (`sources=['Inferenz']` + rating mit confidence=🟢 → Output muss 🟡 sein); Post-Hoc-Quellen-Validator: gemockte Response mit halluzinierter Section (`Item 99`) → Source-Marker auf `['Inferenz']` herabgestuft, WARNING geloggt; safety-filtered Response (ValueError-Pfad wie Phase 1.4) |
| **B.1-7** | Dossier-Generator | Markdown nach V3 §5.3 (mit Reasoning-Erweiterung): Exec Summary (3 Sätze, hart), Bewertung, 15 Punkte je als eigener Mini-Block (NICHT als Tabellenzeile) — Format siehe Block direkt unter dieser Tabelle. Anschließend **source_coverage-Sektion** (EDGAR: 20-F via ADR · Soft: folgt B.3 · Sprach: folgt B.4 · Insider-Transaktionen: folgt B.2), leere „Stef's Notizen". YAML-Frontmatter. Pfad `output/Watchlist/<TICKER>_YYYY-MM-DD.md`. | Golden-File-Render mit allen 15 Punkten als Mini-Blöcke (nicht Tabelle); Längen-Budgets erzwungen (Exec ≤3 Sätze, Reasoning ≤70 Wörter pro Punkt — Test bricht bei Überschreitung); Frontmatter-Schema-Test; Quellen-Marker-Sichtbarkeit (jeder Punkt rendert mindestens einen Marker am Reasoning-Ende) |
| **B.1-8** | CLI-Entrypoint + Composition Root | `fisherscreen deepdive <TICKER>` (typer/argparse), verdrahtet Services (compose.py-Analog), `python -m fisherscreen.deepdive`. | Arg-Parsing; End-to-End mit allen Services gemockt → Dossier in tmp; Exit-Codes (Erfolg / DeepDiveError / DataSourceError) |
| **B.1-9** | Akzeptanz-Skript (manuell) | `scripts/acceptance_deepdive.py` — echter CLI-Lauf NOVO-B.CO gegen reales EDGAR + Firestore-Read + Gemini. Analog `scripts/acceptance_basis_filter.py`. | **Kein** Unit-Test: dokumentiertes manuelles Gate. Stephan liest das Dossier und urteilt (V3-Phase-1-Exit-Kriterium-Analog) |

**Render-Format B.1-7 (pro Fisher-Punkt, Mini-Block statt Tabellenzeile):**

```
### Punkt N — <Titel>
**Bewertung:** ⭐⭐⭐⭐ · **Confidence:** 🟢

<Reasoning, 2-3 Sätze Prosa, max 70 Wörter> [Quellen-Marker]
```

**B.1-Akzeptanztest (Exit-Kriterium).** Analog zum Tool-A-Phase-1-Exit
(„Stef sieht die Listen und sagt: da ist mindestens einer interessant"):

> Ein einziger `uv run fisherscreen deepdive NOVO-B.CO` erzeugt
> `output/Watchlist/NOVO-B.CO_2026-05-XX.md`. Stephan liest das Dossier und sagt
> entweder *„das ist entscheidungs-nützlich"* oder *„Synthesis/Struktur muss anders"*.
> Erst danach wird auf weitere Ticker skaliert (B.2).

---

## 6. Phasen B.2 – B.5+ (Stubs)

Jeweils nur Ziel + Anschlussstelle. Jede bekommt ihre eigene Brainstorm-Session.

**B.2 — Hard-Scuttlebutt-Breite + EU-Voll-Abdeckung.**
*Anschluss an B.1:* B.1-ADR-Resolver ist statisch. B.2 ersetzt/ergänzt ihn durch
dynamische Resolution (OpenFIGI/SEC Company Search) und fügt für reine EU-Titel ohne
ADR den IR-PDF-Fallback hinzu (ADR-1 „nicht im MVP"-Teil). Zusätzlich 10-Q
(Quartale, nur 10-K-Titel) + Insider-Transaktionen (SEC Form 4 für US-Titel,
EU MAR Art. 19 / PDMR für EU-Titel). Filing-Cache-Migration
Lokal-FS → GCS vorbereiten (ADR-4, falls HTTP-Phase B.5+). *Ziel:* Deep Dive
für jeden Universum-Ticker, nicht nur Top-50-ADRs.

**B.3 — Soft Scuttlebutt + Subagent-Isolation (gemeinsam).**
*Anschluss an B.2:* Erst wenn Hard Scuttlebutt stabil ist, kommen die *untrusted*
Quellen (Apify Glassdoor/Kununu, Reddit, HN Algolia, Marketaux). **Gleichzeitig**
das Reader/Scorer/Writer-Pattern (V3 §5.4): Reader nur Read+Grep, schema-validiertes
JSON (`extra="forbid"`, maxLength, Ticker-Regex), Scorer nimmt nur validiertes JSON,
Writer einziger File-Writer. Subagent-Isolation braucht eine **eigene
Brainstorm-Session** (In-Process-Layer mit harten pydantic-Grenzen vs. echte
Subagent-Orchestrierung — heute kein Repo-Standard, §7). *Ziel:* Soft-Signale ohne
Prompt-Injection-Exposition.

**B.4 — Sprach-/Tonalitätsanalyse (ADR-3).**
*Anschluss an B.3:* Nutzt die Reader-Isolation aus B.3 (Q&A-Text ist
attacker-influenced). **B.4a** Letter-to-Shareholders-Ton-Shift (5J-Korpus,
Quellen-Klärung Filing-Embed vs. IR-PDF, Ton-Shift-Metrik). **B.4b** Earnings-Call-
Q&A-Transkript-Quelle (Spike: Seeking Alpha / Motley Fool / AlphaSense / Quartr,
inkl. ToS/Kosten). *Ziel:* Fisher 14/15 aus Sprache statt nur Quant-Proxy.

**B.5+ — Hardening + Workflow-Schluss.**
*Anschluss an B.4:* Cost-Cap-Politur, optionaler HTTP-Endpoint `/run/deepdive`
(nur bei konkretem Use-Case, ADR-2), erste 1–3 echte Deep Dives end-to-end. *Ziel:*
V3 §1.1-Workflow (Tool A → Stufe-3 → Tool B → Kaufentscheidung) mindestens einmal
real vollständig durchlaufen.

---

## 7. Offene Fragen / nächste Brainstorm-Runden

Bewusst **nicht** jetzt entschieden — je eine künftige Brainstorm-Runde:

1. **EU-Voll-Abdeckung — IR-PDF-Parsing in B.2 oder B.3?** PDF-Parsing-Fragilität
   (Layout-Drift) vs. Kopplung an den Soft-Scuttlebutt-Umbau. Eigene B.2-Vor-Brainstorm.
2. **Earnings-Call-Transkript-Quelle (B.4b).** Seeking Alpha / Motley Fool /
   AlphaSense / Quartr — Verlässlichkeit, ToS/Legal, Kosten. V3 §13 Pkt 7. Spike vor
   jeder B.4-Implementierung.
3. **Tool-A → Tool-B Hand-off.** Manuell (Stephan tippt CLI nach Stufe-3) vs.
   Auto-Trigger (Tool A schreibt eine „deep-dive-suggested"-Queue). V3 §1.1 ist
   manuell; Auto-Trigger wäre Komfort, eigene Entscheidung.

---

## 7a. Pre-Flight-Checks vor B.1-Brainstorm

Beide Punkte sind Implementierungs-Voraussetzungen, keine offenen
Brainstorm-Themen. **Status: beide ✅ erledigt 2026-05-18 — B.1-Brainstorm
kann starten.**

1. **Gemini-Modell-Verfügbarkeit.** 10-Min-Spike: `count_tokens` + ein
   500-Token-Test-Call gegen `gemini-2.5-pro` aus dem FisherScreen-GCP-
   Projekt. Bei 429/Quota → Modell-Default in B.1 ist
   `gemini-2.5-flash-lite`, mit Env-Var `FISHERSCREEN_DEEPDIVE_GEMINI_MODEL`
   als Override-Punkt. Lesson (o) aus PROJEKTSTAND.
   **✅ Erledigt 2026-05-18** (`scripts/preflight_gemini_pro.py`):
   `gemini-2.5-pro` nutzbar — `count_tokens` + `generate_content` OK,
   kein 429/403. **B.1-Synthesis-Default = `gemini-2.5-pro`**;
   `FISHERSCREEN_DEEPDIVE_GEMINI_MODEL` bleibt Override (modell-agnostisch).
2. **Filing-Cache-Pfad.** Bestätigung, dass `D:\programme\fisherscreen\cache\filings\`
   schreibbar ist und in `.gitignore` eingetragen wird (siehe ADR-4 oben).
   **✅ Erledigt 2026-05-18:** `cache/filings/` angelegt + schreibbar;
   `.gitignore`-Regel `cache/` greift (per `git check-ignore` verifiziert).

---

## 8. Risiko-Mapping (Premortem)

| # | Risiko | Phase | W'keit | Impact | Gegenmittel |
|---|---|---|---|---|---|
| 1 | Gemini-Kosten explodieren bei 200+-Seiten-20-F (Pro-Tarif) | B.1 | Hoch | Hoch | Hard-Token-Cap im Code (§2.6); Section-Extraktion statt Volldokument (Stage 3); `count_tokens` vor Call; Flash Lite für Bulk, Pro nur Synthesis (V3 §5.4) |
| 2 | Filing-Section-Drift: 10-K- vs. 20-F-Item-Struktur, Parser bricht still | B.1 | Hoch | Mittel | Form-Type-Weiche von Tag 1 (Task B.1-4); Response-Shape-Validierung (CLAUDE.md „kein blindes Vertrauen"); fehlende Section → geflaggt, fail loud, nicht still leer. Task B.1-4 mitigiert Risiko #1 und #2 gemeinsam: robuste Section-Extraktion ist zugleich Token-Cost-Hebel (nur relevante Items in den Prompt) und Halluzinations-Schutz (falsche Sections in den Prompt → Gemini halluziniert auf irrelevantem Text) |
| 2a | Gemini halluziniert Filing-Section-Zitate im Reasoning („Item 99 sagt…" wenn es das nicht gibt) | B.1 | Hoch | Mittel | Post-Hoc-Quellen-Validator in Task B.1-6: Regex auf zitierte Sections, Abgleich gegen tatsächlich an Gemini gesendete Section-Keys, Mismatch → automatischer Downgrade auf `['Inferenz']` + 🟡-Cap; im Prompt explizit anweisen, nur tatsächlich vorhandene Sections zu zitieren |
| 3 | Dossier unbrauchbar lang/dünn (Bibliothek-vs-Briefing-Lehre) | B.1 | Mittel | Hoch | Festes Template mit Längen-Budgets (Exec 3 Sätze hart); Stephan-Review-Gate (B.1-9) **vor** Skalierung |
| 4 | Statische ADR-Tabelle veraltet (CIK-Drift, Delisting) | B.1/B.2 | Mittel | Mittel | Format-/Plausibilitäts-Test über Tabelle; B.2 dynamische Resolution; bei Lookup-Fehler `DeepDiveError` mit klarer Message statt falschem CIK |
| 5 | Quant-Join-Miss: Ticker nicht im letzten Tool-A-Lauf | B.1 | Mittel | Niedrig | Graceful Fallback Live-yfinance + `source_coverage`-Marker (§5.1) |
| 6 | Synthesis-Modell (Pro) quota-gesperrt | B.1 | Mittel | Mittel | Modell via Env-Var (Lesson o-Muster); Verfügbarkeit vor Implementierung verifizieren (§7a Pkt 1) |
| 7 | Prompt-Injection via Soft-Quellen vor Isolation | B.3 | — | Hoch | Phasenschnitt selbst: Soft-Quellen + Isolation **gemeinsam** in B.3, nie getrennt (§2.8) |
| 8 | B.4 blockiert durch ungeklärte Transkript-Quelle | B.4 | Hoch | Mittel | Entkopplung via ADR-3: B.1–B.3 unabhängig; B.4b startet als Quellen-Spike vor Code; notfalls nur B.4a (Briefe, Quelle verfügbar) liefern |

---

## 9. Nicht-Ziele (Tool B Phase B.0/B.1)

Bewusst ausgeklammert:

- **Portfolio Hold-Check** (V3 §4.3) — konzeptionell **Tool A**, nicht Tool B.
  Zeitlich nach Juni-Lauf, sobald echte Kauf-Snapshots existieren (PROJEKTSTAND
  TODO #12). Nicht Teil von Tool B.
- **Earnings-Call-Transkript-Ingestion** — B.4b, Quelle ungeklärt (ADR-3).
- **Soft Scuttlebutt** (Apify/Reddit/HN/Marketaux) — kostenpflichtig + untrusted, B.3.
- **Subagent-Isolation** — erst mit untrusted Soft-Quellen, B.3 (Grundsatz §2.8).
- **HTTP-Endpoint / Cloud Run für Tool B** — ADR-2, frühestens B.5+, use-case-gebunden.
- **Volle Sprach-/Tonalitätsanalyse** — B.4 (ADR-3).
- **Multi-Ticker-Batch-Deep-Dive** — V3 §11 Prinzip 7 (Pull): nie batch.
- **Automatisches Watchlist-Monitoring** — V3 §12 explizites Nicht-Ziel.
- **Composite-Score** — V3-Entscheidung, gilt auch in Tool B.
- **Reine EU-Titel ohne US-ADR** — ADR-1, IR-PDF-Fallback erst B.2/B.3.
- **Bundesanzeiger / Companies House** — B.2 (EU-Breite), nicht MVP.

---

## 10. Empfehlung & nächster Schritt

**Phase B.0 ist der Setup-Vorlauf, Phase B.1 der eigentliche vertikale
Durchstich.** B.0 (Gerüst, ADR-Tabelle-Seed mit NOVO-Eintrag, Watchlist-
Junction, `DeepDiveError`-Klasse) ist klein genug für eine kurze
Plan-Session ohne eigene Brainstorm-Runde — der Master-Brainstorm
liefert genug Festlegung. B.1 startet sauber mit fertigem Gerüst und
konzentriert seinen Akzeptanztest auf Synthesis-Qualität, nicht auf
Infrastruktur-Setup.

**Inhalt von Phase B.1:** ADR-Lookup (statische Tabelle, ADR-1) → EDGAR-Pull
(10-K/20-F-Volltext) → Filing-Parse (Form-Type-Weiche) → Quant-Join (Tool-A-Firestore
+ Live-Fallback) → Gemini-15-Punkte-Synthesis (Pro/Flash-Lite, Token-Cap,
Confidence-Marker) → Markdown-Dossier (V3 §5.3) → CLI-Entrypoint. Akzeptanz:
vollständiges Novo-Nordisk-Dossier aus einem CLI-Aufruf, von Stephan auf
Entscheidungs-Nützlichkeit beurteilt.

**Nächste Session beginnt mit dem `brainstorming`-Skill auf Phase B.1.** Die beiden
Pre-Flight-Checks aus §7a sind erledigt (2026-05-18: `gemini-2.5-pro` nutzbar →
B.1-Synthesis-Default; Filing-Cache `cache/filings/` angelegt) — B.1-Brainstorm
kann direkt starten.

---

*Ende des Dokuments.*
