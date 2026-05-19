# FisherScreen — Projektstand

> **Single Source of Truth für den aktuellen Stand.**
> Wird am Ende jeder Arbeitssession aktualisiert.
> Verwandte Dokumente: `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md` (Architektur, extern),
> `docs/superpowers/brainstorm/` (Architektur-Entscheidungen),
> `docs/superpowers/plans/` (ausgeführte Implementations-Pläne).

---

## Letztes Update: 2026-05-19

## Top of mind

FisherScreen Phase 1 ist produktiv. Erster Lauf am 2026-05-16 erfolgreich durchgeführt nach Fix eines kritischen Feedback-Loop-Bugs. Monatlicher Scheduler-Job läuft, drei Markdown-Outputs (Dimensions, Crosshits, Changes) werden via GitHub Sync ins Obsidian-Repo gepusht. Nächster regulärer Lauf: 2026-06-01 03:00 UTC.

**V3-Filter-Fix ist LIVE auf Cloud Run.** `fix/basis-filter-v3` in `main` gemergt (Commit `d30f581`). Lokaler Akzeptanztest bestätigt: 11/15 US Large-Caps passieren V3-Filter, FX-Konversion sauber. Deploy verifiziert 2026-05-17: GHA-Workflow für Commit `2741634` lief erfolgreich (Run `25984321514`, 07:11 UTC) → Revision `fisherscreen-service-00035-htn`, Image `app:2741634...`. Der 2026-06-01-Lauf läuft gegen die gefixte Pipeline. **Production-Akzeptanz (≥15 US-Titel in Top-50-Crosshits) wird am 2026-06-01 verifiziert.**

**Quick Wins vor 2026-06-01 erledigt (2026-05-17).** TODO #11 Gemini-503-Retry (tenacity, 503/429, Backoff 1s/4s/16s, max 4 Versuche — PR #3, `1d66c47`) und TODO #10 Negativ-Filter-Audit (`docs/negative-filters-status.md` — PR #4, `b78817d`) gemergt; V3-Doc-Pfad-Drift in `CLAUDE.md` + `Projektstand.md` korrigiert (PR #5, `5aa20f4`). Suite 247 grün, 95.39% Coverage. **Sofia/Telefon-Agent-Refactor bleibt zurückgestellt bis nach Tool B.**

**Tool B läuft (2026-05-18).** B.1-Brainstorm → B.1-Design-Spec (`docs/superpowers/specs/2026-05-18-tool-b-phase-b1-design.md`, inkl. ADR-5 Mehrjahres-Quant, 10 Tasks) → B.0-Skeleton-Plan → **B.0 implementiert** auf Branch `feature/tool-b-b0-skeleton` (10 Commits, 265 Tests grün, 95.69% Coverage, subagent-driven mit zweistufigem Review). B.0 liefert: `DeepDiveError`, statische ADR-Tabelle + validierender Loader (`data/adr_table.json` Seed Novo), Tool-B-Composition-Root, argparse-CLI-Skeleton, `output/Watchlist/`-Junction (im Vault angelegt). **Projekt-übergreifende Lesson (Top of mind):** SOPRA-EPDR blockt ALLE uv-generierten `.exe`-Shims (`pytest.exe`, `fisherscreen.exe`, künftige) — kanonische lokale Aufrufform ist immer `uv run python -m <modul>` (`python -m pytest`, `python -m app.deepdive deepdive <TICKER>`); `[project.scripts]` bleibt nur für CI/Container. Daraus: `pyproject.toml` `dev` → PEP-735-`[dependency-groups]` + `[tool.uv] default-groups`, CLAUDE.md-SOPRA-Abschnitt generalisiert, B.1-Spec-Aufrufform korrigiert. B.0 wurde nach `main` gemergt; B.1-Plan (`docs/superpowers/plans/2026-05-18-tool-b-phase-b1-vertical-slice.md`, 12 Tasks) geschrieben + gemergt. **B.1 ist implementiert** (Branch `feature/tool-b-b1-vertical-slice`, subagent-driven mit zweistufigem Review pro Gruppe + Final-Review): vollständiger 6-Stage-Deep-Dive (ADR-Lookup → EDGAR-Pull → Hybrid-Filing-Parse → Quant-Join inkl. ADR-5a Mehrjahres + Trend-Metriken → `gemini-2.5-pro`-15-Punkte-Synthesis mit Post-Hoc-Quellen-Validator → Mini-Block-Dossier), `uv run python -m app.deepdive deepdive NOVO-B.CO`. ~351 Tests grün, ≥95% Coverage. Mehrere Plan-Bugs während der Ausführung gefangen+gefixt (Filing-Parser TOC/Cross-Ref → line-start-Anker, Dilution-Guard, historical-cache-Härtung, `--no-cache`→historical, Empty-CIK-Guard, ValidationError→GeminiError). **Zwei Spec-Amendments (Option A):** E2 `response_schema`→B.2 (google-genai-Emoji-Literal-Friktion; Vertrag via Post-Parse-`FisherPoint`-Validierung + Post-Hoc-Validator erzwungen); §6-Bewertungsratios (KGV/EV-EBIT/FCF-Yield vs. 5J) → B.2, als ehrlicher source_coverage-Gap markiert (§2.7). **Nächster Schritt: B.1→`main` mergen, dann manuelles Akzeptanz-Gate `scripts/acceptance_deepdive.py` (echter Novo-Lauf, Stephan beurteilt Synthesis-Nützlichkeit — V3-Phase-1-Exit-Analog).**

### Scoring-Methodik (Phase 1)

FisherScreen bewertet jeden Ticker auf einer 1–5-Skala in fünf Dimensionen, die Phil Fishers 15 Punkte aus *Common Stocks and Uncommon Profits* clustern:

| Dimension | Fisher-Punkte | Kern-Frage |
|---|---|---|
| **Growth** | #1, #2 | Marktpotenzial und Wachstumsfähigkeit |
| **Profitability** | #5, #6, #11 | Margen und Margen-Stabilität |
| **Management** | #7–#10 | Executive-Qualität, Tiefe, Disziplin |
| **Innovation** | #3, #4 | F&E-Effektivität und Vertriebsstärke |
| **Resilience** | #12–#15 | Langfristige Robustheit, Bilanz, Integrität |

Score entsteht aus Kombination von quantitativen yfinance-Metriken (Margins, ROIC, Revenue-CAGR, Verschuldung, Cashflow-Stabilität) und Gemini-Bewertung pro Dimension. Qualifikationsschwelle: Score ≥ 4.0 (`score_threshold` in `config.py`).

**Crosshits-Logik:** Ticker zählt als Crosshit wenn er in mehreren Dimensionen gleichzeitig die Schwelle überschreitet. Ranking: primär nach Anzahl Crosshits (mehr = besser), sekundär nach Ø Score der qualifizierenden Dimensionen. Phil-Fisher-Grundgedanke: mehrdimensionale Stärke ist robuster als eindimensional hoher Score.

**Beispiel (Mai 2026):** Novo Nordisk (NOVO-B.CO) = 5 Crosshits (alle Dimensionen), Ø Score 4.6 → Position 1. Allianz = 3 Crosshits (Profitability, Management, Resilience), Ø Score 4.33.

**Universum:** Vorfilter reduziert ~1.389 Tickers auf ~160 vor der Dimensions-Bewertung. Im Mai-Lauf: ausschließlich EU-Ticker (US-Titel durch Bid/Ask-Filter eliminiert — Root Cause identifiziert, Fix in Branch `fix/basis-filter-v3`). V3-Filterlogik nun dokumentiert in `docs/superpowers/brainstorm/2026-05-17-us-titel-bugfix.md`.

### Vault-Anbindung (lokal)

Der Cloud-Run-Service pusht die monatlichen Markdown-Outputs nach `stnmllr/fisherscreen` in `output/Universum/`. Lokal auf der Workstation sind diese Files via Windows-Junction im Obsidian-Vault sichtbar:

```
D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\Universum
  → Junction nach →
D:\programme\fisherscreen\output\Universum
```

Angelegt 2026-05-16 via `mklink /J`. Voraussetzung für Sichtbarkeit in Obsidian: regelmäßiges `git pull origin main` in `D:\programme\fisherscreen`. Der Junction-Ordner ist in `stef-vault/.gitignore` eingetragen, damit `stnmllr/stef-vault` die Files nicht doppelt versioniert.

**Single-Machine-Setup:** Aktuell nur auf der Workstation. Falls Vault auf einem zweiten Gerät genutzt werden soll, müsste der Service zusätzlich nach `stnmllr/stef-vault` pushen (Phase-2-TODO #5-Variante).

### Phase-1-Status nach erstem Produktivlauf (2026-05-16)

Tool A ist in seiner Kernfunktion live und produziert valide Output-Files. Ein Abgleich gegen die V3-Architektur-Spec zeigt, dass einige in V3 spezifizierte Komponenten noch nicht oder nur als Stub implementiert sind.

#### ✅ Produktiv vorhanden

- Universum-Builder (S&P 500 + S&P 400 + STOXX Europe 600, 1.389 Tickers)
- yfinance-Pipeline mit Firestore-Caching
- Negativ-Filter-Kaskade (reduziert auf ~160 Tickers; effektive Filter-Logik noch nicht auditiert, siehe unten)
- Fünf Dimensions-Listen-Generator (Growth, Profitability, Management, Innovation, Resilience)
- Crosshits-Generator mit Mehrfachnennungs-Ranking
- Changes-Generator (beim Erstlauf konzeptionell korrekt leer)
- Markdown-Output mit YAML-Frontmatter
- FastAPI auf Cloud Run europe-west3, Firestore-Backend
- Cloud Scheduler monatlich (1. um 03:00 UTC = 05:00 CEST)
- EDGAR-Client (Basis-Implementierung: Restatement, Going Concern)
- GitHub Actions Deploy mit Feedback-Loop-Schutz (`paths-ignore` + `[skip ci]`)
- Obsidian-Vault-Sync via Windows-Junction

#### ⚠️ Unklar / Audit notwendig

- **Negativ-Filter-Status:** ✅ **Auditiert (2026-05-17, TODO #10, PR #4)** — vollständig dokumentiert in `docs/negative-filters-status.md`. Befund: 4 Basis-Filter aktiv (Volume/MarketCap/GrossMargin/RevenueGrowth); Bruttomarge/Umsatz nur Single-Value statt V3-Mehrjahres; 3 V3-Kriterien (Dilution/Verluste/neg. Marge) nicht implementiert; `has_active_enforcement` ist Stub; EDGAR-Filter (Restatement/Going-Concern/Enforcement) nur für US-Ticker mit CIK wirksam → ~485 EU-Ticker ungeprüft (**EU-CIK-Blindfleck**). Die früher hier vermutete EU-Restatement-Inaktivität ist damit bestätigt und dokumentiert.

#### ❌ Laut V3 zu Tool A gehörend, aber noch nicht implementiert

- **Portfolio Hold-Check** (V3 Abschnitt 4.3) — erfordert `portfolio_normalized.json` aus Portfolio-Analyzer v5.3, `buy_snapshots` Firestore-Collection, Delta-Check-Logik (CEO/CFO-Wechsel, Margin-Drop, Insider-Verkäufe, Auditor-Wechsel, Going-Concern neu). Wert nur sichtbar, sobald echtes Portfolio mit Kauf-Snapshots existiert.
- **Cost-Caps im Code** (V3 Architekturprinzip #3) — Hard-Limits für Gemini-Tokens pro Lauf mit Logging bei 80%-Erreichung. Aktuell nicht implementiert. Niedriges Risiko bei Flash Lite, aber Spec-Lücke.
- **CLAUDE.md Vollständigkeitsprüfung** (V3 Phase-4-Punkt) — CLAUDE.md ist vorhanden und wird von Claude Code genutzt, aber ein Abgleich gegen die V3-Anforderungen (cmd.exe-Konventionen, WatchGuard-EPDR-Workaround, Test-Befehle) ist ausstehend.

#### Bewertung

Tool A erfüllt seine Hauptaufgabe (Fisher-konforme Kandidatensuche aus großem Universum) **vollständig**. Was fehlt, sind ergänzende V3-Features — allen voran der Portfolio Hold-Check. Diese können parallel oder nach Tool B nachgezogen werden, da sie für den V3-Kernworkflow (Tool A → Stufe-3-Diskussion → Tool B) nicht blockierend sind.

**Phase-1-Exit-Kriterium aus V3:** „Stef sieht die Listen + Querliste und sagt 'da ist mindestens einer interessant' oder 'Filter müssen anders'." → **Erfüllt am 2026-05-16.** Novo Nordisk als einziger 5-of-5-Crosshit-Hit ist ein methodisch plausibles Ergebnis.

### Reihenfolge bis V3-Workflow vollständig nutzbar

V3 Abschnitt 1.1 definiert den Kernworkflow als:

```
Tool A → Stufe-3-Diskussion mit Claude → Tool B (Deep-Dive) → Kaufentscheidung
```

Tool A ist heute (2026-05-16) live. Die Stufe-3-Diskussion ist immer manuell (V3-Intent, keine Automatisierung). Tool B fehlt noch als ausführender Output-Schritt. Folgende Reihenfolge ist sinnvoll:

1. **Diese Woche — Quick Wins (beide Tools profitieren):**
   - ~~Gemini 503-Retry (TODO #11)~~ ✅ erledigt 2026-05-17 (PR #3) — Production-Verifikation steht beim 2026-06-01-Lauf aus
   - ~~Negativ-Filter-Audit-Doku (TODO #10)~~ ✅ erledigt 2026-05-17 — Klarheit über reale Score-Basis und Vorarbeit für Tool-B-EDGAR-Pipeline

2. **Nächste 1–2 Wochen:** Tool B implementieren gemäß V3 Abschnitt 5 (HTTP-Endpoint `/run/deepdive`, Hard/Soft-Scuttlebutt-Pipeline, Sprach-Analyse, Subagent-Isolation, Dossier-Generator, CLI-Wrapper)

3. **Nach Tool-B-Fertigstellung:** Erste echte Stufe-3-Diskussion über den Mai-Output, dann 1–3 echte Deep-Dives produzieren, V3-Workflow End-to-End durchlaufen

4. **2026-06-01:** Zweiter automatischer Monatslauf. Verifikation, dass Changes-Datei sich befüllt und Pipeline stabil ist.

5. **Im Juli (nach erstem realen Kauf-Workflow):** Portfolio Hold-Check nachziehen (TODO #12), sobald echte Kauf-Snapshots vorliegen.

6. **Laufend:** Cost-Caps (TODO #13), CLAUDE.md-Review (TODO #14) als Hygiene-Items.

Wichtig: Portfolio Hold-Check (V3 Abschnitt 4.3) ist konzeptionell Tool A, aber für den V3-Hauptworkflow nicht blockierend. Er ergänzt die Universum-Suche um die Portfolio-Beobachtung — beide Schichten arbeiten unabhängig. Daher pragmatische Verschiebung nach Tool B.

## Status

**Aktueller Phase**: Phase 1 produktiv ✅ — Erster Lauf 2026-05-16, Feedback-Loop-Bug behoben.
**Branch**: `main` — 240 Tests, 95.39% Coverage. Fix gemergt via `d30f581`.
**Deploy**: ✅ V3-Fix live — Revision `fisherscreen-service-00035-htn` (Image aus Commit `2741634`, deployed 2026-05-17 via GHA).
**Cloud Run**: `fisherscreen-service` Revision `00035-htn` in europe-west3 (Projekt `fisherscreen-prod`, Projektnummer 896012696952).
**Gemini-Modell**: `gemini-2.5-flash-lite` (konfigurierbar via `FISHERSCREEN_GEMINI_MODEL`)
**Cloud Scheduler**: `fisherscreen-monthly` aktiv — läuft automatisch am 1. jeden Monats um 05:00 Europe/Berlin. Retry-Policy gehärtet: max 2 Retries, 60s minBackoff.
**Hard-Stop**: Cloud Function + $10-Budget mit Pub/Sub-Hook — verifiziert.
**EDGAR CIK-Lookup**: Funktioniert in Production ✅ — CIKs für US-Ticker aus `company_tickers.json`.
**Universe**: 1.389 Ticker (S&P 500 + S&P 400 + STOXX Europe 600) in `data/universe.json` ✅
**Erster Output**: Top-Crosshit NOVO-B.CO (Score 4.6, alle 5 Dimensionen), 50 Crosshit-Kandidaten aus 160 Vorfilter-Tickern.
**Nächster Lauf**: 2026-06-01 03:00 UTC (automatisch via Cloud Scheduler)
**Tool B (Deep Dive)**: B.0 + B.1 auf `main` (`36818af`, gepusht). CLI lokal `uv run python -m app.deepdive deepdive <TICKER>` (SOPRA-EPDR: kein `.exe`-Shim). Default-Synthesis `gemini-2.5-pro`. **Synthesis-Härtung Stufe 1 implementiert** (Branch `feature/synthesis-prompt-hardening-stage1`, `0b47d66`): erster Novo-Lauf war technisch ok, aber inhaltlich nicht produktionsreif (Sterne-Inflation 67% ⭐⭐⭐⭐⭐, Wettbewerb/Lilly fehlt, P2≈P3, kein Bear-Case, Confidence-Inflation). Stufe 1 = reine Prompt-Härtung + warn-only-Verteilungs-Validator, kein neuer Datenkontext. Suite 362 grün / 95.84%. Offen: NOVO-B.CO-Re-Run gegen 6 Erfolgskriterien (Stephan-Gate), danach Stufe 2 (Konsens/Peer-Daten in den Prompt, eigene Session).

## Erledigt

- 2026-05-10: Repo-Setup (10 Tasks, 23 Tests)
- 2026-05-11: Phase-1-Master-Brainstorm
- 2026-05-12: **Phase 1.1** Data Pipeline + Basisfilter — `main`
- 2026-05-13: **Phase 1.2** EDGAR-Signale — `main`
- 2026-05-13: **Phase 1.3** Gemini Scoring — `main`
- 2026-05-15: **Phase-1.4-Output-Struktur-Brainstorm** — `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`
- 2026-05-15: **Phase-1.4-Implementierungsplan** — `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`
- 2026-05-15: **Phase 1.4** implementiert — PR #1, Squash-Merge, Commit `c5d8019`
- 2026-05-15: **GCP Bootstrap** abgeschlossen — `docs/infra/setup-gcp-project.md`
- 2026-05-15: **Cloud Run Deploy** erfolgreich — `fisherscreen-service` läuft
- 2026-05-16: **$5 Warning-Budget** angelegt in GCP Console (Scope: `fisherscreen-prod`, Threshold: $5 actual spend, Alert: E-Mail an stn.mueller@gmail.com)
- 2026-05-16: **Smoke-Test `/health`** ✅ — `{"status":"ok"}`, OIDC-Auth via `gcloud auth print-identity-token`, Cloud Run operational
- 2026-05-16: **Phase 3 vollständig abgeschlossen** ✅ — Cloud Function, Hard-Stop Budget, reduzierter Run, Cloud Scheduler
- 2026-05-16: **EDGAR CIK-Lookup** gefixt — `get_cik()` via `www.sec.gov/files/company_tickers.json`, URL-Bug (`data.sec.gov` → `www.sec.gov`) behoben, Production verifiziert
- 2026-05-16: **GitHub-Token `.strip()`** — defense-in-depth gegen PAT-Newline-Bug deployed
- 2026-05-16: **Universe-Erweiterung** auf 1.389 Ticker — `scripts/build_universe.py`, S&P 500 + S&P 400 + STOXX 600
- 2026-05-16: **Cloud Run Timeout** auf 3600s erhöht — `--timeout=3600` in `deploy.yml`
- 2026-05-16: **Deployment-Feedback-Loop** gefixt — `paths-ignore: output/**` + `[skip ci]`, PR #2, Commit `9b64007`
- 2026-05-16: **Scheduler Retry-Policy** gehärtet — `--max-retry-attempts=2 --min-backoff=60s --max-backoff=300s --max-retry-duration=1800s`
- 2026-05-16: **Erster produktiver Lauf** ✅ — Verifikations-Run 15:36 UTC, kein Retry, drei Output-Commits mit `[skip ci]`, kein Deploy getriggert
- 2026-05-17: **US-Titel-Bug Root Cause** — `passes_liquidity_filter` eliminierte alle 904 US-Stocks (bid=0.0 yfinance außerhalb Marktzeiten; `not 0.0 == True`). Alle 485 EU-Ticker kamen durch, 0 US-Ticker.
- 2026-05-17: **V3-Basis-Filter implementiert + gemergt** — `fix/basis-filter-v3` → `main` (Merge `d30f581`). Entfernt: `passes_liquidity_filter`, `passes_penny_stock_filter`. Neu: Market Cap ≥ €2B (mit FX-Normalisierung), Gross Margin ≥ 30%, Revenue Growth ≥ 0%. `YFinanceClient.get_fx_rate()` + `CachedYFinanceClient.get_fx_rate()` hinzugefügt. Region-Logging (US/EU-Counts) in Runner. 240/240 Tests, 95.39% Coverage.
- 2026-05-17: **Lokaler Akzeptanztest** ✅ — `scripts/acceptance_basis_filter.py` gegen echtes yfinance: 11/15 US Large-Caps (AAPL, MSFT, GOOGL, AMZN, META, JNJ, V, PG, KO, NVDA, MA) + 5/10 EU-Ticker passieren V3-Filter. FX-Konversion sauber (USD/DKK/GBP/CHF → EUR). Keine Exceptions. (4 US-Ausfälle plausibel: JPM/UNH Finanz/Versicherungs-Margins, XOM Energy-Margin, HD Retail-Wachstum.)
- 2026-05-17: **V3-Filter-Fix auf Cloud Run deployed** ✅ — GHA-Deploy-Trigger funktionierte wieder (Run `25984321514` für Commit `2741634`, erfolgreich 07:11 UTC). Verifiziert via `gcloud run services describe`: Revision `fisherscreen-service-00035-htn`, Image-Tag `app:27416345130f29dd9838b164522f54b15ac7eb4f` (= voller SHA von `2741634`, enthält V3-Fix `d2bff68` als Ancestor). Damit ist der einzige für den 2026-06-01-Lauf blockierende Punkt erledigt.
- 2026-05-17: **TODO #11 Gemini 503-Retry** ✅ — tenacity-Retry für transiente 503 UNAVAILABLE + 429 RESOURCE_EXHAUSTED auf beide Gemini-Calls (`count_tokens` + `generate_content`), exponentieller Backoff 1s/4s/16s, max 4 Versuche, `reraise=True` → bisheriges Skip-Verhalten bei Dauerfehler erhalten. 6 Unit- + 1 Integrationstest, 247 Tests grün. Brainstorm→Spec→Plan→subagent-driven TDD, zweistufiges Review. PR #3 (Squash, `1d66c47`). Production-Verifikation (ALV.DE überlebt transientes 503) steht beim 2026-06-01-Lauf aus.
- 2026-05-17: **TODO #10 Negativ-Filter-Audit** ✅ — `docs/negative-filters-status.md` erstellt: code-verifiziertes Audit aller effektiven Filter (Status/Datenquelle/Aktivierungsaufwand-Grobskala) + Querschnitts-Befunde (EU-CIK-Blindfleck prominent, 8-vs-9-Diskrepanz aufgelöst, Cache-Verhalten). Jede Statuszeile zweistufig + final Zeile-für-Zeile gegen realen Code reviewt. 0 Code-/Test-Änderungen. PR #4 (Squash, `b78817d`).
- 2026-05-17: **V3-Doc-Pfad-Fix** ✅ — falscher Referenzpfad `…\10_Projekte\FisherScreen\…` → korrekt `…\Wissen\Finanzen\FisherScreen\…` in `CLAUDE.md` + `Projektstand.md` (Zeile 5). PR #5 (Squash, `5aa20f4`).
- 2026-05-18: **Tool-B-Master-Brainstorm (rev4)** ✅ — `docs/superpowers/brainstorm/2026-05-18-tool-b-master.md`: Master-Plan über Tool B (Deep-Dive-CLI), 6 Folge-Phasen B.0–B.5+ (je eigene Brainstorm→Plan→TDD-Session). Vier ADRs: ADR-1 EU-Quelle via SEC 20-F/ADR-Pfad (Novo `NOVO-B.CO`→`NVO`→CIK), ADR-2 CLI-lokal in-process (kein Cloud Run für Tool B, V3 §6.1 bewusst aufgegeben), ADR-3 Sprach-/Tonalitätsanalyse auf Phase B.4, ADR-4 Filing-Cache Lokal-FS + TTL. B.1 als vertikaler Durchstich detailliert (9 TDD-Tasks, Akzeptanz: vollständiges Novo-Dossier aus einem CLI-Aufruf). **Rev3 ergänzt die Reasoning-Schicht:** Begründungs-Pflicht pro Fisher-Punkt (2-3 Sätze + Quellen-Marker [Filing-Section]/[Quant-Snapshot]/[Inferenz]), Inferenz→Confidence-Cap 🟡, Post-Hoc-Quellen-Validator gegen Section-Halluzination (Risiko 2a), Dossier-Render auf Mini-Blöcke. **Rev4: beide §7a-Pre-Flight-Checks erledigt** — `gemini-2.5-pro` im FisherScreen-GCP-Projekt nutzbar (`scripts/preflight_gemini_pro.py`, count_tokens + generate_content OK, kein 429/403) → **B.1-Synthesis-Default = `gemini-2.5-pro`** (`FISHERSCREEN_DEEPDIVE_GEMINI_MODEL` bleibt Override); `cache/filings/` angelegt + schreibbar, `.gitignore`-Regel `cache/` greift. Vier rev-Runden + eigenständige Konsistenz-Checks (§-Refs, ADR-Zählung, cmd.exe-Syntax, Rev1/Rev2-Historien-Aufteilung, Commit-Message-Akkuratheit, §10-Forced-Fix). Commits `43b6d1c` (rev1/2) + `67b1e13` (PROJEKTSTAND) + `3d69308` (rev3) + `da9fb12` (rev4) auf `main` (Solo-Repo, kein PR-Workflow).
- 2026-05-18: **B.1-Brainstorm + Design-Spec** ✅ — `docs/superpowers/specs/2026-05-18-tool-b-phase-b1-design.md`. Schärft alle §5.1-Feinheiten (E1 Hybrid-Filing-Parser html2text+Anker-Regex+Flag, E2 ein Cap-gehärteter `gemini-2.5-pro`-Call mit `response_schema`, E3 argparse-CLI, E4 B.0 separat). Neuer **ADR-5** (gebündelt 5a/5b/5c) löst die ADR-3↔Tool-A-Cache-Inkonsistenz: Mehrjahres-Quant live aus yfinance (`historical_data_service`, lokaler 90d-Cache `_cached_at`-Format), strukturiertes `quant_snapshot`, Tool-A-Dimensions nur `[Inferenz]`-Kontext. Task-Zahl 9→10 (neu B.1-5a Trend-Metriken). Spec auf `main` gemergt (Commits `6595d1a`/`a5a1d6f`).
- 2026-05-18: **B.0-Skeleton-Plan** ✅ — `docs/superpowers/plans/2026-05-18-tool-b-phase-b0-skeleton.md` (8 bite-sized TDD-Tasks, keine neue Dependency), auf `main` (Commit `0ea1d93`).
- 2026-05-18: **B.0 implementiert** ✅ — Branch `feature/tool-b-b0-skeleton`, subagent-driven (backend-developer + Spec-/Code-Quality-Review + Final-Review, M1-Fix). `DeepDiveError`; `data/adr_table.json` (Seed `NOVO-B.CO`→`NVO`/`0000353278`/`20-F`) + validierender `app/deepdive/adr_table.py`; `app/deepdive/compose.py` (re-exportiert `build_github_client`); argparse-CLI `app/deepdive/__main__.py`; `output/Watchlist/.gitkeep` + Vault-Junction angelegt. 265 Tests grün, 95.69% Coverage. 7 Commits.
- 2026-05-18: **SOPRA-EPDR-Fund + 3 Korrekturen** ✅ (auf B.0-Branch) — `uv run fisherscreen` blockiert wie `pytest.exe`. `pyproject.toml`: `dev` → `[dependency-groups]` + `[tool.uv] default-groups` (`f7cf578`, damit `uv run python -m pytest` ohne Flags läuft); CLAUDE.md-SOPRA-Abschnitt auf generelles `python -m`-Pattern hochgezogen + uv-Grundbefehle-Inkonsistenz gefixt (`2a84cf2`); B.1-Spec-Aufrufform §1/E3/B.1-8/B.1-9 auf `python -m app.deepdive` (`0fbf5aa`). B.0 nach `main` gemergt.
- 2026-05-18: **B.1-Plan + Implementierung** ✅ — Plan `docs/superpowers/plans/2026-05-18-tool-b-phase-b1-vertical-slice.md` (12 Tasks) auf `main` (`040fa0b`). Implementiert auf Branch `feature/tool-b-b1-vertical-slice`, subagent-driven (Gruppen A–E, je `backend-developer` + Spec- + Code-Quality-Review + Fix-Loops, plus Final-Whole-Implementation-Review). Neu: `app/models/deep_dive_record.py`, `app/deepdive/{adr_resolver,filing_cache,filing_parser,historical_cache,trend_metrics,quant_join,fisher_points,synthesis,dossier_generator,pipeline}.py`, `app/services/{historical_data_service,gemini_deepdive_client}.py` + `edgar_client.get_latest_annual_filing`, CLI-Pipeline-Wiring, `scripts/acceptance_deepdive.py`. ~351 Tests, ≥95% Coverage. Während Ausführung gefangene Plan-Defekte: Filing-Parser `<40`-TOC-Bug + Cross-Ref-Defeat (→ line-start-Anker + Dotted-Leader-Skip), `compute_dilution_pct`-Guard, historical-cache I1/I2-Härtung (Sibling-Parität zu filing_cache), `--no-cache`→historical-Threading, Empty-CIK-actionable-Guard, `FisherPoint`-`ValidationError`→`GeminiError` (Fail-Loud/Exit-3). Spec-Amendments Option A: E2 `response_schema`→B.2, §6-Bewertungsratios→B.2 (ehrlicher Gap-Marker). **Nächster Schritt: B.1→`main`; danach manuelles Akzeptanz-Gate (echter Novo-Deep-Dive via `scripts/acceptance_deepdive.py`, Stephan urteilt).**

- 2026-05-19: **Tool B Synthesis-Härtung Stufe 1** ✅ — Befund aus erstem echten NOVO-B.CO-Dossier: Pipeline + Anti-Halluzinations-Layer technisch ok (6/15 Cite-Halluzinationen gefangen), aber inhaltlich nicht produktionsreif. Diagnose (P1–P7): `_SYSTEM_PROMPT` in `app/deepdive/synthesis.py` ist inline, ohne jede Rating-Rubrik; Wettbewerber-/Konsens-/News-Daten erreichen das Modell **nie** (P/E nicht einmal im `PointInTimeQuant`-Modell) → Lilly-Fehlen ist strukturell, nicht Gemini-Fehler. Stufe 1 (Branch `feature/synthesis-prompt-hardening-stage1`, Commit `0b47d66`, subagent-driven `backend-developer` strikt TDD): Prompt-Härtung — relative Sterne-Rubrik mit Wettbewerbsanker, Verteilungsvorgabe (≤4 ⭐⭐⭐⭐⭐, ≥3 schwach, Selbstprüfung), Punkt-Paar-Abgrenzung (P2≠P3, P4≠P11, P5≠P6, P12≠P13), Bear-Case-Pflicht mit Trigger-Wörtern, Wettbewerbserwähnungs-Pflicht P4/5/6/11/12 (generisch + `[Marktkontext]` ohne erfundene Namen/Cites), geschärfte Confidence-Skala (🟢 nur Hard-Source), neuer `[Marktkontext]`-Marker (passiert den unveränderten Cite-Layer). Plus warn-only-Verteilungs-Validator in `run_synthesis` (Option b, zwei Schwellen: >5/15 ⭐⭐⭐⭐⭐, <2/15 ≤⭐⭐⭐ — `logging.warning`, kein Hard-Fail, schont teuren Gemini-Pro-Lauf). JSON-Vertrag/Pydantic-Modell/`_validate_sources`/`_build_user_prompt` byte-identisch unangetastet. Suite 362 grün / 95.84%. **Nächster Schritt: NOVO-B.CO-Re-Run gegen 6 Erfolgskriterien (Sterneverteilung realistischer, Lilly in ≥3 Punkten, P2≠P3, Bear-Case je Punkt, Inferenz-Zahl stabil/leicht sinkend, Bear-Wort in ≥10/15) — Stephan-Gate; danach Stufe 2 (yfinance-Konsens + Peer-Kennzahlen in den Prompt, eigene Session mit eigenem TDD-Lauf).**

### Mai 2026 — Produktivgang und Feedback-Loop-Fix

Erster Scheduler-Run produzierte Output, aber löste eine Feedback-Schleife aus: jeder der drei Output-Commits (Dimensions, Crosshits, Changes) auf `main` triggerte den `Deploy to Cloud Run` Workflow, der eine neue Cloud-Run-Revision deployte und den laufenden Container mit `SIGTERM` killte. Cloud Scheduler mit aggressiver Retry-Policy retriede den Request → zweiter `POST /run/monthly` 4 Sekunden nach dem ersten. Sechs GitHub-Actions-Workflow-Runs in 15 Minuten, zwei davon HTTP 409 wegen paralleler `gcloud run deploy`-Calls auf denselben Service.

**Fix (PR #2, Commit `9b64007`):**
- `.github/workflows/deploy.yml`: `paths-ignore: ['output/**']`
- `app/main.py:63`: Commit-Message ergänzt um `[skip ci]`-Suffix
- Tests erweitert (`test_monthly_run_commit_message_includes_skip_ci`)
- Defense-in-Depth: beide Maßnahmen aktiv, jede für sich allein würde reichen

**Cloud Scheduler Retry-Policy gehärtet:**
- Vorher: unlimited retries, 5s minBackoff, kein maxRetryDuration
- Nachher: `--max-retry-attempts=2 --min-backoff=60s --max-backoff=300s --max-retry-duration=1800s`

**Deployment-Quirk:** Squash-Merge-Commit `9b64007` und nachfolgender Empty-Commit `b8427f6` haben den `Deploy to Cloud Run` Workflow nicht getriggert (Ursache unklar — möglicher GitHub-Actions-Trigger-Bug bei zeitlich engem Aufeinanderfolgen). Workaround: manueller Deploy via `gcloud builds submit` + `gcloud run deploy` von der Workstation. Resultierende Revision: `fisherscreen-service-00030-jnv`, Image-Tag `b8427f6`.

**Verifikations-Lauf (15:36 UTC):**
- ✅ Genau ein `POST /run/monthly` 200 OK (kein Retry)
- ✅ Keine doppelten EDGAR-Calls (jeder CIK genau einmal)
- ✅ Drei Output-Commits mit `[skip ci]` Suffix gepusht
- ✅ Kein neuer GitHub-Actions-Workflow trotz Output-Commits
- ✅ Cloud Run Revision blieb stabil bis zum Lauf-Ende (kein Mid-Run-Shutdown)

**Erster echter Phil-Fisher-Output:**
- Universum-Größe nach Vorfilter: 160 Tickers (aus ~1.389 S&P 500 + S&P 400 + STOXX 600)
- Top-Crosshit: **Novo Nordisk (NOVO-B.CO)** mit Score 4.6 und allen 5 Dimensionen positiv — einziges Unternehmen mit Full-House-Hit
- Weitere Top-Kandidaten: DB1.DE, ITX.MC, MONC.MI, SAP.DE (alle 4 Dimensionen)
- Insgesamt 50 Crosshit-Kandidaten in der Top-50-Liste
- Changes-Datei korrekt leer (erster Lauf, kein Vormonat-Vergleich möglich)

---

### Phase-3-Details (2026-05-16)

| Schritt | Was |
|---|---|
| Phase 3b — Cloud Function | `fisherscreen-budget-stop` deployed (Gen 2, europe-west3), Trigger: Pub/Sub `fisherscreen-budget-alerts` |
| Phase 3b — $10 Budget | Hard-Stop-Budget mit Pub/Sub-Hook aktiv für `fisherscreen-prod` |
| Phase 3c — /run/monthly Test | Revision 00006, 9 Ticker processed (1 filtered), Markdown-Files in `stnmllr/fisherscreen/output/Universum/` committed |
| Phase 3c — Cloud Scheduler | `fisherscreen-monthly` aktiv, Schedule `0 5 1 * *` Europe/Berlin, OIDC-Auth mit `fisherscreen-scheduler` SA |
| Phase 3c — Hard-Stop-Verifikation | Pub/Sub-Test pausierte Scheduler korrekt; manuell resumed — End-to-End bestätigt |
| Gemini-Migration | `gemini-2.0-flash-lite` → `gemini-2.5-flash-lite`; `FISHERSCREEN_GEMINI_MODEL` Env-Var eingebaut |
| Cloud Function Rename | `infra/budget_stop.py` → `infra/main.py` (Cloud Functions Python-Konvention) |

### Phase-1.2-Details (2026-05-13)

| Datei | Was |
|---|---|
| `app/services/edgar_client.py` | `EdgarClientImpl`: `has_restatement` (submissions.json → 8-K Item 4.02), `has_going_concern` (EFTS Full-Text), `has_active_enforcement` Stub |
| `app/services/cached_edgar_client.py` | 7-Tage-TTL-Cache in `dev_edgar_cache` |
| `app/screener/filters.py` | `apply_edgar_filters()` ergänzt |
| `app/screener/runner.py` | `run_edgar_filter()` — läuft nur auf Phase-1.1-Restmenge |
| `app/screener/compose.py` | `build_edgar_pipeline()` Composition Root |
| `app/config.py` | `edgar_collection`-Setting |

### Phase-1.3-Details (2026-05-13)

| Datei | Was |
|---|---|
| `app/services/gemini_client.py` | `GeminiClientImpl`: Token-Counting vor API-Call, strukturiertes JSON-Output, `GeminiError`-Wrapping; `GeminiScoreResult` Dataclass |
| `app/services/cached_gemini_client.py` | 30-Tage-TTL-Cache in `dev_gemini_scores` |
| `app/models/run_record.py` | `RunRecord` Pydantic-Modell mit `compute_cost()` |
| `app/screener/run_tracker.py` | Token-Akkumulation, `finish()` schreibt in `dev_screener_runs` |
| `app/screener/scorer.py` | `run_gemini_scoring()`: 3.000-Ticker Hard-Cap, per-Ticker `GeminiError`-Guard, Run-Level Token-Budget (80% Warning + Hard Stop bei 500k) |
| `app/screener/compose.py` | `build_gemini_pipeline()`, `build_run_tracker()` |
| `app/config.py` | `gemini_api_key`, `gemini_score_collection`, `screener_runs_collection` |
| `infra/budget_stop.py` | Cloud Function: pausiert Cloud Scheduler wenn $10/Monat überschritten |
| `infra/requirements.txt` | `google-cloud-scheduler` Dependency für Cloud Function |
| `docs/infra/budget-alerts.md` | Setup-Doku für GCP Budget Alerts ($5 E-Mail, $10 Hard Stop) |

### Phase-1.4-Details (2026-05-15)

| Datei | Was |
|---|---|
| `app/screener/dimensions.py` | `DIMENSIONS` Konstante — Single Source of Truth |
| `app/output/dimensions_generator.py` | `YYYY-MM-Dimensions.md` mit YAML-Frontmatter + 5 Dimensions-Tabellen |
| `app/output/crosshits_generator.py` | `YYYY-MM-Crosshits.md` — Ticker in ≥2 Dims mit Score ≥4 |
| `app/output/changes_generator.py` | `YYYY-MM-Changes.md` — Diff gegen jüngsten Vormonats-Run |
| `app/screener/runner.py` | `run_screener()` Orchestrator (Basis → EDGAR → Gemini → Output) |
| `app/services/github_client.py` | `GitHubClientImpl` — Push via REST API |
| `app/screener/compose.py` | `build_github_client()` |
| `app/main.py` | FastAPI `/health` + `/run/monthly` |
| `Dockerfile` | python:3.12-slim + uv, uvicorn Port 8080 |
| `.github/workflows/deploy.yml` | Push-to-main → Cloud Run Deploy (Workload Identity Federation) |
| `data/universe.json` | 10-Ticker Placeholder |
| `docs/infra/cloud-scheduler.md` | Cloud Scheduler Setup-Doku |
| `docs/infra/setup-gcp-project.md` | GCP Bootstrap Step 1–11 |

**Qualitäts-Korrekturen durch Code-Review (nicht im Plan):**
- `GeminiClientImpl._parse_response`: `ValueError` in except-Tuple ergänzt (safety-filtered responses)
- `RunTracker.finish()`: delegiert zu `RunRecord.compute_cost()` statt Formel duplizieren
- `RunTracker`: `Literal["success","partial","aborted"]`-Typ, `_finished`-Guard gegen Doppelaufruf
- Alle `build_*()` geben Protocol-Typen zurück, nicht konkrete Klassen
- `spec=True` auf Pydantic-Settings-Mock (16 harmlose Pydantic-v2-Deprecation-Warnings — bekannt)
- `budget_stop.py`: `os.environ.get()` statt `[]` (kein KeyError beim Cold Start), `GoogleAPICallError`-Catch
- `DimensionsGenerator`: `qualifying_count` ist pre-cap (nicht post-cap) — durch Review-Loop gefunden

## Nächste Session — Phase 2 TODOs

Phase 1 ist vollständig. Nächster regulärer Lauf automatisch 2026-06-01 03:00 UTC. Die folgenden Phase-2-Punkte sind nach Priorität geordnet — kein Blocking-Item für den Juni-Lauf.

**Infra-Phasen-Status (vollständig):**

| Phase | Status |
|---|---|
| Phase 1 (Bootstrap) | ✅ |
| Phase 2 (Deploy) | ✅ |
| Phase 3a ($5 Warning) | ✅ |
| Phase 3b ($10 Hard Stop) | ✅ |
| Phase 3c (Cloud Scheduler) | ✅ |
| Phase 4 (Universe + Bugfixes + Produktivgang) | ✅ |

**Phase-2-Backlog:**

1. **Cloud Run Jobs statt Cloud Run Service für Tool A** — entkoppelt den Monatslauf von Deployments, eliminiert Deployment-Race-Risiko bei zukünftigen Architekturänderungen, höheres Timeout (24h statt 60min). Setzt voraus: Cloud Run Jobs Migration, Scheduler-Trigger auf Job-Execution statt HTTP.

2. ~~**Gemini 503-Retry mit tenacity**~~ ✅ (2026-05-17) — erledigt, siehe TODO #11 (Branch `feature/gemini-503-retry`, PR #3). Ursprung: ALV.DE fiel im Mai-Lauf durch transientes "503 UNAVAILABLE - high demand".

3. **`has_active_enforcement` ausimplementieren** — derzeit Phase-1-Platzhalter, gibt für alle CIKs `False` zurück. Bei US-Tickern via SEC EDGAR, bei EU-Tickern via BaFin/FCA/AMF/CNMV.

4. **Idempotenz-Lock auf `/run/monthly`** — Firestore-Dokument `runs/monthly/{YYYY-MM}` mit Status `running|completed`. Verhindert Doppelaufrufe falls Scheduler-Retry trotz neuer Policy noch zuschlägt.

5. **Output-Repo-Trennung** — `stnmllr/fisherscreen-output` als separates Repo, wenn Output-Frequenz steigt (Deep-Dives, Hold-Checks). Aktuell nicht nötig.

6. **GitHub-Actions-Trigger-Quirk** *(Priorität gesenkt — Trigger funktioniert wieder)* — Untersuchen, warum Squash-Merge-Commit `9b64007` keinen Workflow ausgelöst hat. Mögliche Ursache: zeitliches Aufeinanderfolgen von Commits. Update 2026-05-17: Trigger lief für Commits `2741634` und Folge-Commits wieder zuverlässig (mehrere erfolgreiche Runs in `gh run list`). Phänomen wirkt intermittierend, nicht reproduzierbar — bleibt Backlog ohne Dringlichkeit.

7. ~~**Vorfilter-Dokumentation**~~ ✅ (2026-05-17) — V3-Filterlogik jetzt in `docs/superpowers/brainstorm/2026-05-17-us-titel-bugfix.md` und direkt im Code dokumentiert. Threshold-Werte: Market Cap ≥ €2B, Gross Margin ≥ 30%, Revenue Growth ≥ 0%. Restlicher Audit (EU-Ticker ohne CIK, EDGAR-Stub-Status) weiterhin offen.

8. **Name-Cleanup im Output** — yfinance liefert Listing-Suffixe ("N", "I", "V") und kaputte Encodings ("DISE...O" statt "DISEÑO"). In `dimensions_generator.py` und `crosshits_generator.py` rstrip/encoding-Cleanup.

9. **`docs/scoring-methodology.md`** — Detaillierte Dokumentation der Score-Berechnung pro Dimension: yfinance-Feldmapping, Heuristiken, Gemini-Prompt-Templates, Score-Aggregation, Vorfilter-Logik. Wichtig für: Reproduzierbarkeit, künftige Methodenänderungen, Debugging schwacher Score-Plausibilität.

10. ~~**Negativ-Filter-Audit (`docs/negative-filters-status.md`)**~~ ✅ (2026-05-17) — Audit aller effektiven Filter erstellt: 4 Basis-Filter (Volume/MarketCap/GrossMargin/RevenueGrowth) aktiv, Bruttomarge/Umsatz nur Single-Value (vereinfacht ggü. V3-Mehrjahres), 3 V3-Kriterien (Dilution/Verluste/neg. Marge) nicht implementiert, `has_active_enforcement` Stub, EDGAR nur US-CIK (EU-Blindfleck). Branch `chore/negative-filters-audit`.

11. ~~**Gemini 503-Retry mit tenacity**~~ ✅ (2026-05-17) — tenacity-Retry für transiente 503 UNAVAILABLE + 429 RESOURCE_EXHAUSTED auf beide Gemini-Calls (count_tokens + generate_content), exponentieller Backoff 1s/4s/16s, max 4 Versuche, reraise → bisheriges Skip-Verhalten bei Dauerfehler erhalten. Branch `feature/gemini-503-retry`, 247 Tests grün. Spec/Plan: `docs/superpowers/specs/2026-05-17-gemini-503-retry-design.md`.

12. **Portfolio Hold-Check** — Vollständige Implementierung gemäß V3 Abschnitt 4.3. Sinnvoll zeitlich nach erstem Comdirect-CSV-Export → Portfolio-Analyzer → `portfolio_normalized.json` Workflow. Realistischer Zeithorizont: nach Juni-Lauf, vor Tool B.

13. **Cost-Caps im Code** — Hard-Limits für Gemini-Tokens pro Lauf, Logging-Schwelle bei 80%-Erreichung. V3-Architekturprinzip #3. *(Tool-B-Teil ✅ 2026-05-18: Per-Deepdive-Token-Cap + 80%-WARNING in `gemini_deepdive_client`; Tool-A-Run-Cap offen.)*

14. **CLAUDE.md gegen V3-Spec prüfen** — Vollständigkeit: cmd.exe-Konventionen, `uv run python -m pytest`-Workaround, Test-Konventionen, Deploy-Workflow lokal vs. CI. *(2026-05-18: SOPRA-EPDR-Abschnitt generalisiert + dev-Default-Group; Rest offen.)*

**Tool B — Active:**

- [x] **B.0 + B.1 implementiert** ✅ (2026-05-18) — siehe Erledigt; auf `main` gepusht.
- [ ] **B.1 Akzeptanz-Gate (Stephan)** — `uv run python -m scripts.acceptance_deepdive` (echter Novo-Lauf: EDGAR 20-F + Firestore + yfinance + Gemini Pro), Dossier beurteilen → „entscheidungs-nützlich" (B.2) oder „Synthesis/Struktur retunen". Exit-Kriterium-Analog zu Phase-1.
- [ ] **B.2 Vor-Brainstorm** — erst nach B.1-Akzeptanz. Scope: Hard-Scuttlebutt-Breite + EU-Voll-Abdeckung, dynamische ADR-Resolution (OpenFIGI/SEC-Search), IR-PDF-Fallback, 10-Q + Insider (Form 4 / MAR Art. 19), **valuation-Multiples** (§6, aus B.1 verschoben), Gemini **`response_schema`** (aus E2 verschoben), DOM-aware Filing-Parser, historical-cache→GCS falls HTTP-Phase.

## Offene Punkte (nicht-blockierend)

### Erster Lauf — Offene Punkte
- [ ] **TSMC market_cap missing** — yfinance-Bug oder Ticker-Format-Issue (TSM vs TSMC)? Klären.
- [ ] **Cache-TTL bei Monatswechsel** — greift Mai-Cache am 1. Juni? TTL-Logik im Firestore-Client prüfen
- [ ] **`dev_` Collection-Prefix** evaluieren — für Production auf `prod_` umstellen?
- [ ] Crosshits-Schwelle ≥4 nach erstem echten Lauf validieren — ggf. auf ≥4.5 wenn >50 Kandidaten

### Infra / Sicherheit
- [ ] **GitHub Token Rotation** — `fisherscreen-github-token` läuft am **2027-05-15** ab. Kalender-Reminder setzen.
- [ ] **Default Compute SA prüfen** — `896012696952-compute@developer.gserviceaccount.com` hat GCP-default `roles/editor`; evaluieren ob sicher entfernbar
- [ ] **`scripts/smoke-test.cmd`** schreiben — kapselt gcloud-Token + curl /health, für wiederholbare Tests

### Backlog (nicht-blockierend)
- [ ] IT-Ticket WatchGuard EPDR (strukturelle Lösung statt Workaround)
- [ ] mypy strict / `@runtime_checkable` auf Protocols erwägen
- [ ] GICS-50 (Communication Services) zu F&E-Branchen hinzufügen? — nach erstem Lauf bewerten
- [ ] `has_active_enforcement` ist Stub — SEC EDGAR hat keine direkte Enforcement-API; Lösung evaluieren
- [ ] Status Telefon-Agent-Migration prüfen (Deadline 1.6.2026)
- [ ] **V3-Architektur-Doc aktualisieren** (`D:\programme\stef-vault\...\FisherScreen_Architektur_v3.md`): Section 4.2 beschreibt L1-L5 quant-basierte Listen. Implementiert wurden Gemini-Assessment-Dimensionen — Doku-Drift vermerken.

## Lessons Learned — GCP Bootstrap

Aufgezeichnet nach dem ersten Deploy-Versuch (2026-05-15). Für künftige Projekte mit ähnlichem Stack.

### a) Bootstrap-Doku gehört zur gleichen Phase wie der Code

Wenn eine Phase Infrastruktur-Code generiert (`Dockerfile`, `deploy.yml`, Cloud-Function-Code), muss die **gleiche Phase** auch das Bootstrap-Setup dokumentieren — nicht nur nachgelagerte Schritte. `docs/infra/setup-gcp-project.md` hätte Teil der Phase-1.4-Lieferung sein müssen, nicht ein Add-on nach dem ersten fehlgeschlagenen Deploy.

### b) GitHub-Actions-Workflows immer auf Secret-Namen prüfen vor Merge

Ungetestete Workflows zu mergen ist riskant. Mindestens: alle referenzierten Secrets (`${{ secrets.XYZ }}`) vor dem Merge verifizieren. Falls möglich, `act` lokal für Trockenlauf nutzen.

### c) `uvicorn` explizit als Prod-Dependency eintragen

`uvicorn[standard]` muss explizit in `pyproject.toml` stehen. Der Container baut durch, weil `uv sync` keinen Fehler wirft wenn `uvicorn` fehlt — der Crash kommt erst zur Container-Startzeit. Cloud Run Logs zeigen dann kein stdout, weil der Crash vor jedem Python-Output passiert.

### d) `gcloud builds submit` braucht `roles/viewer` für Log-Streaming

Nicht nur `logging.viewer`. Diese Anforderung ist in der GCP-Doku nicht prominent dokumentiert. Alternative bei Least-Privilege-Präferenz: `--async` Flag im Workflow.

### e) WIF Service Account braucht 8 Rollen für funktionierende CI/CD

Vollständige Liste (in `docs/infra/setup-gcp-project.md` dokumentiert):
`run.admin`, `artifactregistry.writer`, `iam.serviceAccountUser`, `cloudbuild.builds.editor`, `cloudbuild.builds.viewer`, `serviceusage.serviceUsageConsumer`, `storage.admin`, `viewer`

### f) `--service-account=...` explizit im deploy-Befehl angeben

Ohne dieses Flag läuft Cloud Run mit dem Default Compute SA (`PROJECT_NUMBER-compute@developer.gserviceaccount.com`), der projektweit `roles/editor` hat — Security-Issue. Immer explizit `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` setzen.

### g) GitHub Token: immer 1 Jahr + Kalender-Reminder

GitHub erlaubt max 1 Jahr für fine-grained Tokens. Default ist 30 Tage — viel zu kurz für Production. Immer 1 Jahr setzen und sofort einen Kalender-Reminder ~2 Wochen vor Ablauf eintragen.

### h) Nach Squash-Merge sofort lokalen Branch aufräumen

```
git checkout main
git pull
git branch -D feature/<branch-name>
```

Ohne diesen Schritt entstehen divergierende Histories (Squash-Commit hat andere SHA als die WIP-Commits). Führt zu `unmerged-paths`-State, der nur via `git reset --hard origin/main` reparierbar ist.

### i) Pfade mit Sonderzeichen in der Working Copy prüfen

Kaputte Verzeichnisse (z.B. `D:programmefisherscreendata`) entstehen, wenn ein Tool in einer Bash-Umgebung Windows-Pfade mit `\` als Escape-Zeichen interpretiert. Vor Commit prüfen und ggf. löschen.

### j) Konsolidiertes Budget ≠ projektspezifischer Hard-Stop

Ein konsolidiertes GCP-Budget (Scope: "Alle Projekte") ist ein brauchbares Sicherheitsnetz, aber für project-spezifisches Hard-Stop-Verhalten ungeeignet: Die Pub/Sub-Notification enthält keine Projekt-ID mit der man zuverlässig unterscheiden kann, welches Projekt das Budget gerissen hat — Fehlauslösung durch andere Projekte ist möglich. Immer ein zweites, projektspezifisches Budget anlegen (`Scope: fisherscreen-prod`), auch wenn ein konsolidiertes bereits existiert. Beide koexistieren problemlos.

### k) OIDC-Token auf Windows/cmd.exe: robuster Ansatz via Zwischenspeicher

`gcloud auth print-identity-token | curl` ist auf Windows/cmd.exe fragil (Pipe-Timing, Quote-Escaping). Robuster ist:

```
gcloud auth print-identity-token > %TEMP%\token.txt
set /p TOKEN=<%TEMP%\token.txt
curl -H "Authorization: Bearer %TOKEN%" https://<SERVICE_URL>/health
```

Für wiederholbare Tests lohnt sich ein kleines `scripts\smoke-test.cmd`, das diesen Boilerplate kapselt.

### l) Kein /run/monthly-Test mit vollem Universum vor aktivem Hard-Stop

Bei einem Bug im Gemini-Calling-Loop (~2.100 Ticker × mehrere API-Calls) kann das $5-Budget binnen Stunden gerissen werden. Der E-Mail-Alert trifft mit ~24 h Verzögerung ein. Reihenfolge nicht verhandelbar:
1. Hard-Stop Cloud Function deployen (Phase 3b)
2. $10 Hard-Stop-Budget anlegen (GCP Console)
3. Reduzierter Test mit 5–10 Tickern
4. Voller Lauf erst danach

## Lessons Learned — Phase 3 (Cloud Function, Run, Scheduler)

Aufgezeichnet 2026-05-16. Ergänzung zu GCP-Bootstrap-Lessons a–l.

### m) GitHub-PAT-Newline-Bug: `echo` hängt `\n` an → httpx-Crash

`echo "token" | gcloud secrets versions add` speichert das Secret mit abschließendem Newline. httpx wirft dann beim ersten Request `LocalProtocolError` (invalider HTTP-Header). **Fix:** Secret mit Binary-Write ohne Newline speichern:
- PowerShell: `[System.IO.File]::WriteAllText("token.txt", "ghp_...", [System.Text.Encoding]::ASCII)`
- Alternativ: VS Code → neue Datei, LF-Encoding, **kein** trailing newline → `gcloud secrets versions add ... --data-file=token.txt`
- Code-seitig als Defense-in-depth: `token = token.strip()` beim Laden des Secrets.

### n) Token-Leak in Cloud Logging via httpx-Exceptions

Wenn httpx eine Exception wirft (z.B. nach Newline-Bug), schreibt es den vollständigen Request-Header in die Exception-Message — inkl. `Authorization: Bearer ghp_...`. Landet ungefiltert in Cloud Logging, ist öffentlich lesbar wenn Logs-Viewer falsch konfiguriert. **Mitigation:** `.strip()` verhindert den Crash; bei echter Token-Exposition sofort revoken + neues Secret anlegen.

### o) Gemini 2.0 Flash-Lite deprecated ab 1. Juni 2026

`gemini-2.0-flash-lite` wird June 1, 2026 eingestellt. Migration auf `gemini-2.5-flash-lite` (GA seit Feb 2026). `3.1-preview` übersprungen wegen Account-Zugriff (gleiches Muster wie bei anderen Projekten — Preview-Modelle oft quota-restricted). **Pattern für die Zukunft:** Gemini-Modell nie hardcoden — immer `FISHERSCREEN_GEMINI_MODEL` als Env-Var in Cloud Run setzen, Fallback im Code.

### p) Cloud Run Secret-Caching: Update wirkt erst nach Container-Restart

Wenn ein Secret in Secret Manager aktualisiert wird, cached der laufende Container die alte Version bis zum nächsten Kaltstart. `gcloud run services update --update-secrets=KEY=secret:latest` erzwingt einen Restart — auch wenn der Secret-Name identisch bleibt. Ohne diesen Schritt testet man gegen das alte Secret.

### q) Cloud Functions Python: Entrypoint muss `main.py` heißen

Cloud Functions (Python Runtime) erwartet den Source-Code in einer Datei namens `main.py`. Eine Datei `budget_stop.py` als `--source=infra` wird nicht gefunden — Cloud Function startet, findet aber den Entrypoint nicht. Fix: Datei in `main.py` umbenennen.

### r) cmd.exe interaktiv vs. Batch: `%{variable}` vs. `%%{variable}`

In interaktiver cmd.exe-Session: `%{http_code}` (einfaches Prozentzeichen).  
In `.bat`-Skripten: `%%{http_code}` (doppeltes Prozentzeichen, weil Batch-Parser ein `%` konsumiert).  
Verwirrungsquelle wenn man Befehle zwischen interaktiver Session und `.bat`-Datei kopiert.

### s) SOPRA-EPDR blockt ALLE uv-`.exe`-Shims — `python -m <modul>` ist kanonisch

WatchGuard EPDR blockiert nicht nur `pytest.exe`, sondern jeden von uv in
`venv\Scripts\` generierten Console-Script-Shim (`fisherscreen.exe` etc.) —
`Zugriff verweigert (os error 5)`. `python.exe` selbst ist freigegeben. Der
Workaround ist **strukturell, nicht shim-spezifisch**: lokal immer
`uv run python -m <modul>` (`python -m pytest`, `python -m app.deepdive
deepdive <TICKER>`). `[project.scripts]`-Deklarationen bleiben — sie gelten
für CI/Container ohne EPDR. Folge-Entscheidung: Dev-Deps als
PEP-735-`[dependency-groups]` + `[tool.uv] default-groups`, damit der
CLAUDE.md-dokumentierte `uv run python -m pytest` ohne `--extra`/`--group`
real funktioniert (vorher: `No module named pytest`). Generalisiert die
frühere pytest.exe-only-Notiz. Entdeckt bei B.0-Akzeptanz (2026-05-18).

### t) Plan-verbatim-Code kann mit seinen plan-verbatim-Tests inkonsistent sein → BLOCKED, nicht raten

3× in der B.1-`subagent-driven`-Ausführung bestand der vom Plan vorgegebene
Code seine eigenen vorgegebenen Tests nicht (Filing-Parser `<40`-TOC-Skip;
`compute_dilution_pct`-Guard; weitere). Plan-Self-Review fängt Code↔Test-
Inkonsistenz **nicht** zuverlässig — erst die TDD-Ausführung deckt sie auf.
Regel: ausführender Subagent meldet bei Plan-Selbstwiderspruch **STOP/BLOCKED
+ Root-Cause**, rät keine Korrektur; der Controller (Plan-Autor) entscheidet
den Fix (oft 1-Zeilen-Angleich an die Schwester-Funktion). Subagent-Briefing
explizit: „verbatim; bei Selbstwiderspruch BLOCKED".

### u) Final-Whole-Implementation-Review fängt emergente Seam-Bugs, die Per-Task-Reviews strukturell nicht sehen

Per-Gruppen-Reviews testeten je nur valide Fixtures. Der Critical-Bug
(uncaught `pydantic.ValidationError` aus `FisherPoint(**rp)` umgeht die
`FisherScreenError`→Exit-Code-Mappung — Fail-Loud-Bruch beim ersten echten
Gemini-Lauf) wurde erst vom abschließenden End-to-End-Review über den ganzen
Branch gefunden. Bei mehrteiligen Plänen den finalen Whole-Diff-Review nie
überspringen — einzige Stelle, die Seam-übergreifende Contract-Lücken sieht.

## GCP-Infrastruktur (Stand 2026-05-16)

| Ressource | Wert |
|---|---|
| Projekt | `fisherscreen-prod` (896012696952) |
| Region | `europe-west3` |
| Cloud Run Service | `fisherscreen-service` (aktuell: Revision `00035-htn`, Image `2741634` — V3-Filter-Fix live seit 2026-05-17) |
| Runtime SA | `fisherscreen-runtime@fisherscreen-prod.iam.gserviceaccount.com` |
| Deploy SA | `github-deploy@fisherscreen-prod.iam.gserviceaccount.com` |
| Scheduler SA | `fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com` |
| WIF Pool | `github-pool` / Provider `github-provider` |
| Artifact Registry | `europe-west3-docker.pkg.dev/fisherscreen-prod/fisherscreen` |
| Secrets | `fisherscreen-gemini-api-key`, `fisherscreen-github-token` (läuft ab: 2027-05-15) |
| Gemini SDK | `google-genai` mit API-Key (nicht Vertex AI) |
| Gemini Modell | `gemini-2.5-flash-lite` (via `FISHERSCREEN_GEMINI_MODEL` Env-Var) |
| Budget Warning | $5/Monat actual spend → E-Mail stn.mueller@gmail.com (aktiv) |
| Budget Hard Stop | ✅ $10/Monat + Pub/Sub `fisherscreen-budget-alerts` → Cloud Function (verifiziert) |
| Cloud Function | `fisherscreen-budget-stop` (Gen 2, europe-west3, `infra/main.py`) |
| Cloud Scheduler | `fisherscreen-monthly` — `0 5 1 * *` Europe/Berlin → POST `/run/monthly` (max 2 Retries, 60s–300s Backoff) |
| Konsolidiertes Budget | €10/Monat alle Projekte — grobes Sicherheitsnetz |

## Decisions Log

| Datum | Entscheidung | Begründung | Trade-off |
|---|---|---|---|
| 2026-05-13 | `google-genai` SDK statt `google-generativeai` | Offizielle neue Bibliothek für Gemini; unterstützt `count_tokens()` vor API-Call | Breaking changes bei zukünftigen SDK-Updates wahrscheinlich — aber kein Weg zurück zur alten SDK sinnvoll |
| 2026-05-13 | Token-Counting vor jedem API-Call | Verhindert übergroße Prompts; kein verlorenes API-Budget | Zusätzlicher API-Call pro Ticker (~100ms Latenz) |
| 2026-05-13 | Run-Level Token-Budget in `run_gemini_scoring()`, nicht im Aufrufer | Fail-safe auf dem niedrigsten Level; Aufrufer kann die Cap nicht vergessen | Parameter `token_cap` am Aufrufpunkt sichtbar — könnte versehentlich überschrieben werden |
| 2026-05-13 | `RunRecord.compute_cost()` als Single Source für Kostenformel | Formel-Duplikation zwischen `RunTracker` und `RunRecord` vermieden | `RunRecord.estimated_cost_usd` wird nach Konstruktion nachträglich gesetzt — leicht unintuitiv |
| 2026-05-13 | `budget_stop.py` als eigenständige Cloud Function (kein FastAPI-Route) | Pub/Sub-Trigger erfordert separaten Entrypoint; Cloud Function ist günstiger als zweiter Cloud Run Dienst | Separate Deployment-Pipeline nötig; `infra/requirements.txt` separat von `pyproject.toml` halten |
| 2026-05-15 | Drei Output-Files pro Monatslauf (Dimensions/Crosshits/Changes) statt File-pro-Ticker | Kognitiv skalierbarer Output — Stephan schaut realistisch max. 10 Ticker/Monat; 400 Files verstecken die wenigen relevanten | Mehr Generator-Code als ein einziger Per-Ticker-Renderer; drei kleinere Module statt einem großen |
| 2026-05-15 | Crosshits-Logik (≥2 Dimensionen mit Score ≥4) statt Composite-Score | Bleibt V3-konform (kein Composite); Schnittmenge ist Fisher-konformeres Signal als gemittelter Score | Schwelle muss nach erstem Lauf empirisch validiert werden |
| 2026-05-15 | Markdown ist Snapshot, kein Firestore-Snapshot pro Run | Vermeidet Schreibkosten + Redundanz; Git versioniert die Markdowns ohnehin | Changes-Diff muss aus Markdown-Frontmatter lesen statt aus Firestore — leichte Mehrarbeit im Generator |
| 2026-05-15 | YAML-Frontmatter in `Dimensions.md` als maschinen-lesbare Sicht | Eine Datei für Mensch + Maschine; Obsidian rendert Frontmatter sauber | Format-Drift muss durch Schema-Test gesichert werden |
| 2026-05-16 | `gemini-2.5-flash-lite` statt `gemini-2.0-flash-lite` | 2.0 Flash-Lite deprecated ab 1. Juni 2026; 2.5 ist GA und kostengleich | Preview-Modelle (3.1) wegen Account-Quota-Beschränkung übersprungen |
| 2026-05-16 | `FISHERSCREEN_GEMINI_MODEL` als Env-Var statt Hardcode | Modell-Updates ohne Code-Deploy; ermöglicht A/B-Testing per Cloud Run Revision | Default `gemini-2.5-flash-lite` im Code — Env-Var nur wenn Abweichung nötig |
| 2026-05-16 | `paths-ignore: output/**` + `[skip ci]` als Defense-in-Depth gegen Feedback-Loop | Output-Commits dürfen keinen Deploy triggern; `paths-ignore` ist primärer Schutz, `[skip ci]` Backstop falls Output-Pfad je außerhalb `output/` landet | Beide Maßnahmen sind unabhängig voneinander wirksam — keine Doppelarbeit, aber leicht mehr Konfigurations-Surface |
| 2026-05-17 | V3-Basis-Filter ersetzen Pre-V3-Filter vollständig | Bid/Ask-Filter ist timing-sensitiv (yfinance 03:00 UTC = US Pre-Market → bid=0.0) und kein Qualitätsmerkmal. V3 spezifiziert: Market Cap ≥ €2B, Gross Margin ≥ 30%, Revenue Growth ≥ 0%. FX-Normalisierung (USD/GBP/CHF/SEK → EUR) im Runner via `get_fx_rate()`. | Volume-Filter (100k Avg Daily) beibehalten als praktischer Liquiditäts-Safeguard, auch wenn nicht in V3-Spec. |
| 2026-05-18 | Tool B: ADR-1 (EU via SEC-20-F/ADR-Pfad) · ADR-2 (CLI-lokal in-process, kein Cloud Run) · ADR-3 (Sprach-Analyse→B.4) · ADR-4 (Filing-Cache Lokal-FS+TTL) — Detail in Master-Brainstorm/B.1-Spec | Pull-Workflow, schnelle Dev-Iteration, Cloud-Run-Timeout-Risiko, Firestore-1-MiB-Limit | Statische ADR-Tabelle = Wartungsschuld (~50 Einträge); HTTP-Endpoint frühestens B.5+ |
| 2026-05-18 | ADR-5 (gebündelt 5a/5b/5c): Mehrjahres-Quant live aus yfinance (`historical_data_service` + lokaler 90d-Cache, `_cached_at`); strukturiertes `quant_snapshot`; Tool-A-Dimensions nur `[Inferenz]`-Kontext | Tool-A-Cache hat keine Mehrjahres-Reihen; ADR-3 verlangt Buyback/Verwässerungs-Proxies; Inferenz-auf-Inferenz vermeiden | +1 Task (5a); yfinance-Mehrjahres instabil → graceful (≥3J ok, sonst Flag) |
| 2026-05-18 | E2-Amendment (Option A): Synthesis-Vertrag via Post-Parse-`FisherPoint`-Validierung + Post-Hoc-Quellen-Validator statt Gemini `response_schema` | `google-genai` bildet Emoji-`Literal`-Enums + pydantic-Validatoren nicht sauber ab; zwei Validierungs-Schichten erzwingen den Vertrag bereits strukturell | `response_schema` → B.2; Durchsetzung post-parse, nicht am Modell-Output |
| 2026-05-18 | §6-Bewertungsratios (KGV/EV-EBIT/FCF-Yield vs. 5J) → B.2; in B.1 als ehrlicher source_coverage-Gap markiert | B.1-Akzeptanz = Synthesis-Qualität; echte Multiples = Daten-Breite/B.2-Scope; §2.7 statt stillem Drop | B.1-Dossier ohne Bewertungs-Multiples — bewusst, sichtbar getrackt |
| 2026-05-18 | `pyproject.toml` `dev` → PEP-735 `[dependency-groups]` + `[tool.uv] default-groups=["dev"]` | CLAUDE.md-`uv run python -m pytest` lief sonst nicht (pytest nicht default-installiert: „No module named pytest") | Production-Build muss `--no-default-groups`, sonst pytest im Image |
| 2026-05-18 | Filing-Parser: Line-Start-Anker + Dotted-Leader-TOC-Skip statt „last-anchor-wins" | „last-wins" wird von Mid-Sentence-Cross-Refs („see Item 5 above") besiegt → still falsche Sections (Fail-Loud-Verstoß) | Flatten-Fixtures brauchen Any-Position-Fallback; DOM-aware = B.2 |

## Parallele Projekte

- **Telefon-Agent / Sofia-Refactor**: **Zurückgestellt bis nach FisherScreen Tool B** (bewusste Reihenfolge-Entscheidung 2026-05-17 — FisherScreen-Quick-Wins + Tool B haben Vorrang). Sofia-Refactor wird NICHT vor Tool B gestartet. Memory-Deadline 1.6.2026 für die Gemini-Migration ist bekannt; beim nächsten Login Status prüfen.
- **RechPro**: Stabil, keine Aktivität geplant.

## Geänderte Annahmen / Pivots

- **2026-05-15:** Phase-1.4-Scope geändert von „ein File pro Ticker in `output/Universum/`" auf „drei aggregierte Files pro Monatslauf". Ursache: Premortem-Diskussion identifizierte „Pull-Philosophie kollabiert in der Praxis" als Top-Risiko. 400 Markdown-Files = Bibliothek, nicht Briefing. Siehe `docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md`.
- **`filter_passed_basis` ist binär nach apply_basis_filters**: `None` = "nicht geprüft", `True`/`False` = Ergebnis. Unveränderlich.
- **`get_financials` Rückgabetyp `Any`**: yfinance liefert pandas DataFrame, kein dict.
- **Kein Composite-Score in Tool A**: fünf Dimensions-Listen nebeneinander — V3-Entscheidung, kein Scoring-Aggregat. Crosshits ersetzen die funktionale Rolle ohne Composite-Probleme.
- **`screened_at` Timestamp in `ScreenerRecord` ist `default_factory`**: Objekte, die zu verschiedenen Zeiten erstellt werden, sind nicht gleich. In Tests: Record-Instanz einmal erstellen und wiederverwenden, nicht mehrfach `_record()` aufrufen.
- **Gemini via API-Key, nicht Vertex AI**: `google-genai` SDK mit `FISHERSCREEN_GEMINI_API_KEY`. Kein Service-Account für Gemini-Calls nötig.
