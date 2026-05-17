# Negative-Filters Audit Doc Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create `docs/negative-filters-status.md` — an honest, code-verified audit of every effective negative filter (status, data source, activation effort) plus cross-cutting findings.

**Architecture:** Single new Markdown file in repo-root `docs/`. No code, no tests, no behavior change. The "test" for each task is a verification step: every status claim must be confirmed by reading the cited `file:function` in the real codebase. A wrongly-stated status is an audit failure, not cosmetic.

**Tech Stack:** Markdown only. Shell cmd.exe. No build/test tooling involved. Git on branch `chore/negative-filters-audit`.

**Spec:** `docs/superpowers/specs/2026-05-17-negative-filters-audit-design.md`

> **Discipline reminder for the implementer:** Do NOT re-derive the audit from scratch and do NOT soften findings. The verified facts are embedded below with exact code references. Your job: transcribe them into the doc in the spec's structure, then independently re-open each cited file and confirm the claim before committing. If any cited code does NOT match the stated status, STOP and report — the plan's facts may be stale.

---

### Task 1: Create doc with Methodik (§1) + Statustabelle (§2)

**Files:**
- Create: `docs/negative-filters-status.md`

- [ ] **Step 1: Write §1 (Methodik) and §2 (Statustabelle)**

Create `docs/negative-filters-status.md` with exactly this content:

````markdown
# Negativ-Filter — Status-Audit

> Audit-Stand: 2026-05-17. Quelle des Soll: V3-Architektur §4.1.
> Belegt gegen Code-Stand Branch `chore/negative-filters-audit`.
> Reines Status-Dokument — keine Roadmap, keine Empfehlungen (siehe §4).

## 1. Methodik

TODO #10 spricht von „8 V3-Filtern". Dieses Audit deckt bewusst **alle real
wirkenden Filter** ab — die 9 Knock-out-Kriterien aus V3-Architektur §4.1
**plus** den Nicht-V3-Volume-Safeguard (`MIN_AVG_DAILY_VOLUME`) —, weil die
effektive Score-Basis von *jedem* aktiven Filter bestimmt wird, nicht nur
von den spezifizierten. Der Volume-Filter ist kein V3-Kriterium, wurde aber
am 2026-05-17 bewusst als praktischer Liquiditäts-Safeguard beibehalten
(Decisions-Log PROJEKTSTAND, 2026-05-17). Status- und Aufwands-Vokabular
sind unten fixiert, damit das Dokument vergleichbar altert.

**Status:** `Aktiv` (wirkt wie V3 spezifiziert) · `Aktiv (vereinfacht)`
(implementiert, aber methodisch reduziert ggü. V3) · `Stub` (Funktion
existiert, gibt konstant Pass zurück) · `Nicht implementiert` (kein Code,
kein Datenfeld).

**Aktivierungsaufwand (Grobskala, keine Stunden):** `Trivial` (Schwellen-/
Config-Wert) · `Klein` (neues Feld aus vorhandenem yfinance-`info`-Dict +
Filterfunktion + Tests) · `Mittel` (neue Datenquelle wie yfinance
financials/balance-sheet-Historie + Mehrjahres-Aggregation + Tests) ·
`Groß` (neue externe Integration ohne saubere API) · `Unklar` (keine
bekannte verlässliche Datenquelle; Research-Spike nötig). `—` = entfällt
(Filter bereits aktiv).

## 2. Statustabelle

| # | Filter | V3-Bezug (§4.1 / Fisher) | V3-Soll | Code-Ist | Status | Datenquelle | Aktivierungsaufwand |
|---|---|---|---|---|---|---|---|
| 1 | Insolvenz / Chapter 11 / Going Concern | §4.1 Z1 / trivial | Knock-out bei Insolvenz/Chapter-11/Going-Concern | Going-Concern via EFTS-Volltext „raise substantial doubt" in 10-K/10-Q letzte 24 Mon. (`edgar_client.py:has_going_concern`); Insolvenz/Chapter-11-Status wird **nicht** separat geprüft | Aktiv (vereinfacht) | SEC EDGAR EFTS (nur US m. CIK) | Mittel (EU-Abdeckung) / Unklar (expliziter Chapter-11-Status) |
| 2 | Marktkapitalisierung < 2 Mrd EUR | §4.1 Z2 / Datenqualität | < €2 Mrd raus | `passes_market_cap_filter` ≥ `MIN_MARKET_CAP_EUR` (2e9), FX-normalisiert via `runner.py:_resolve_market_cap_eur` | Aktiv | yfinance `marketCap` + `get_fx_rate` | — |
| 3 | Bruttomarge < 30 % in 8/10 Jahren | §4.1 Z3 / Punkt 5 | < 30 % in 8 von 10 Jahren | `passes_gross_margin_filter`: **Single-Value** `grossMargins` ≥ 0.30, keine 10-Jahres-Historie | Aktiv (vereinfacht) | yfinance `info['grossMargins']` (Punktwert) | Mittel |
| 4 | Negative Bruttomarge in 2/3 letzten Jahren | §4.1 Z4 / Punkt 5 | negativ in 2 von 3 Jahren | kein Code, kein Datenfeld; lose von #3 (Single-Value) mit-abgedeckt | Nicht implementiert | yfinance financials-Historie | Mittel |
| 5 | Umsatz-CAGR 10J < 0 % | §4.1 Z5 / Punkt 1 | 10-Jahres-CAGR < 0 % | `passes_revenue_growth_filter`: **Single-Value** `revenueGrowth` (YoY) ≥ 0.0, kein 10J-CAGR | Aktiv (vereinfacht) | yfinance `info['revenueGrowth']` (YoY-Punktwert) | Mittel |
| 6 | Aktien-Outstanding-Wachstum > 5 % p.a. / 5J | §4.1 Z6 / Punkt 13 | > 5 % p.a. über 5J raus | kein Filter, kein Datenfeld in `ScreenerRecord` | Nicht implementiert | yfinance shares-outstanding-Historie | Mittel |
| 7 | Verluste in 5/10 letzten Jahren | §4.1 Z7 / allgemein | Verlust in 5 von 10 Jahren | kein Filter, keine Net-Income-Historie in `ScreenerRecord` | Nicht implementiert | yfinance income-statement-Historie | Mittel |
| 8 | Aktive SEC-Enforcement | §4.1 Z8 / Punkt 15 | Knock-out bei aktiver Enforcement | `edgar_client.py:has_active_enforcement` loggt „not implemented" und gibt konstant `False` zurück; ungecacht (`cached_edgar_client.py:has_active_enforcement` delegiert nur) | Stub | SEC EDGAR Litigation Releases (keine saubere API) | Groß |
| 9 | Restatement letzte 3 Jahre | §4.1 Z9 / Punkt 10/15 | Restatement in letzten 3J | `edgar_client.py:has_restatement`: 8-K Item 4.02 letzte 3J aus `submissions.json`; greift nur für US-Ticker mit CIK, EU → `edgar_skipped` | Aktiv (US m. CIK) | SEC EDGAR submissions (nur US) | Groß (EU-Abdeckung: Nicht-US-Filing-Quellen) |
| + | Volume ≥ 100k Avg-Daily (**Nicht-V3**) | nicht in V3 | — (kein V3-Kriterium) | `passes_volume_filter` ≥ `MIN_AVG_DAILY_VOLUME` (100 000); bewusster Safeguard | Aktiv | yfinance `info['averageVolume']` | — |

Reihenfolge der Filterprüfung im Code (`filters.py:_get_fail_reason`):
Volume → Market Cap → Gross Margin → Revenue Growth; danach EDGAR-Stufe
(`filters.py:apply_edgar_filters`): Restatement → Going Concern →
Enforcement. EDGAR läuft erst auf der Basis-Filter-Restmenge
(`runner.py:run_screener` ruft `run_basis_filter` dann `run_edgar_filter`).
````

- [ ] **Step 2: Verify every §2 row against the real code (the "test")**

Re-open and read each cited location; confirm the stated Code-Ist/Status is literally true. Use the Read tool, not memory:

- `app/screener/filters.py` — confirm: `MIN_MARKET_CAP_EUR = 2_000_000_000`, `MIN_AVG_DAILY_VOLUME = 100_000`, `MIN_GROSS_MARGIN = 0.30`, `MIN_REVENUE_GROWTH = 0.0`; functions `passes_market_cap_filter`, `passes_volume_filter`, `passes_gross_margin_filter`, `passes_revenue_growth_filter` use a single record field each (no multi-year loop); `_get_fail_reason` order is volume→market_cap→gross_margin→revenue_growth; `apply_edgar_filters` checks restatement→going_concern→enforcement and treats `edgar_skipped` as pass-through (`filter_passed_edgar = None`).
- `app/screener/runner.py` — confirm: `_resolve_market_cap_eur` does FX via `yfinance.get_fx_rate`; `run_edgar_filter` sets `record.edgar_skipped = True` when `cik is None`; `run_screener` calls `run_basis_filter` then `run_edgar_filter`.
- `app/services/edgar_client.py` — confirm: `has_restatement` = 8-K Item "4.02" within `years=3` from `submissions.json`; `has_going_concern` = EFTS query `"raise substantial doubt"` forms `10-K,10-Q` within `months=24`; `has_active_enforcement` logs `not implemented` and `return False`.
- `app/services/cached_edgar_client.py` — confirm: `_TTL_SECONDS = 7 * 24 * 3600`; `_fetch_and_cache` stores `has_restatement` + `has_going_concern` together; `has_active_enforcement` delegates without caching.
- `app/models/screener_record.py` — confirm: only point-value fields from `from_yfinance_info` (`grossMargins`, `revenueGrowth`, `marketCap`, `averageVolume`, …); **no** shares-outstanding history, **no** net-income/earnings history, **no** multi-year series fields. This is the proof for rows 4/6/7 = "Nicht implementiert" and 3/5 = "Aktiv (vereinfacht)".

If any check fails, STOP and report which row contradicts the code. Otherwise continue.

- [ ] **Step 3: Commit**

```
git add docs/negative-filters-status.md
git commit -m "docs: add negative-filters audit — methodik + status table (TODO #10)"
```

---

### Task 2: Add §3 (Querschnitts-Befunde) + §4 (Implikationen, strikt deskriptiv)

**Files:**
- Modify: `docs/negative-filters-status.md` (append §3 and §4)

- [ ] **Step 1: Append §3 and §4**

Append exactly this to `docs/negative-filters-status.md`:

````markdown
## 3. Querschnitts-Befunde

### 3.1 EU-CIK-Blindfleck (wichtigster Befund)

Die drei EDGAR-Filter (`has_restatement`, `has_going_concern`,
`has_active_enforcement`) greifen ausschließlich für Ticker, deren CIK
`edgar_client.py:get_cik` über die SEC-`company_tickers.json` (US-zentriert)
auflöst. `runner.py:run_edgar_filter` setzt für jeden Ticker ohne CIK
`record.edgar_skipped = True`; `filters.py:apply_edgar_filters` reicht
solche Records ungeprüft durch (`filter_passed_edgar = None`). Im
1.389-Ticker-Universum sind ~485 EU-Ticker (Ticker mit „."): für dieses
~⅓ des Universums sind alle drei EDGAR-Filter still inaktiv. Ein EU-Titel
ohne Restatement-/Going-Concern-Flag wurde **nicht geprüft**, nicht
freigesprochen.

### 3.2 8-vs-9-Diskrepanz

V3-Architektur §4.1 listet **9** Knock-out-Zeilen. PROJEKTSTAND
konsolidiert sie als „8 V3-Filter", indem „Insolvenz / Chapter 11 / Going
Concern" und der Going-Concern-Aspekt als ein Punkt gezählt werden. Dieses
Audit führt alle 9 §4.1-Zeilen einzeln plus den Nicht-V3-Volume-Filter. Die
Diskrepanz ist eine reine Zähl-/Konsolidierungsfrage, kein fehlender Filter
— sie wird hier nur dokumentiert, die V3-Architektur-Doku wird **nicht**
geändert (separater PROJEKTSTAND-Backlog-Punkt zur V3-Doc-Drift).

### 3.3 Cache-Verhalten

`cached_edgar_client.py` speichert `has_restatement` und
`has_going_concern` gemeinsam in einem Firestore-Dokument pro CIK mit
7-Tage-TTL (`_TTL_SECONDS = 7 * 24 * 3600`). `has_active_enforcement` wird
nicht gecacht (Stub, delegiert direkt). Basis-Filter (yfinance) nutzen den
separaten `universe_cache`/`dev_`-Mechanismus, nicht den EDGAR-Cache.

## 4. Implikationen für die Score-Interpretation

*Strikt deskriptiv — was ist, nicht was zu tun ist.*

- Die Score-Basis eines Titels ist die Schnittmenge: Volume ≥ 100k **und**
  Market Cap ≥ €2 Mrd **und** Gross Margin (Punktwert) ≥ 30 % **und**
  Revenue Growth (YoY-Punktwert) ≥ 0 %. Die V3-Mehrjahres-Schärfen
  (8/10-Jahre-Marge, 10J-CAGR, Verlust-/Verwässerungs-Historie) wirken
  faktisch nicht; Titel mit schwacher Langzeit-, aber solider
  Momentaufnahme passieren die Basis-Stufe.
- Restatement/Going-Concern als Knock-out wirken nur für US-Titel mit CIK.
  Für EU-Titel ist das Fehlen dieser Flags Ausdruck eines übersprungenen
  Checks, nicht einer bestandenen Prüfung.
- Aktive SEC-Enforcement fließt derzeit in keine Entscheidung ein (Stub
  liefert konstant „kein Knock-out").
- Für die Tool-B-EDGAR-Pipeline ist der Ist-Stand: `has_restatement` und
  `has_going_concern` sind nutzbare, gecachte US-Signale; eine
  EU-Abdeckung und ein Enforcement-Signal existieren nicht und sind dort
  als Datenlücke vorzufinden.
````

- [ ] **Step 2: Verify §3/§4 claims against code (the "test")**

Re-confirm by reading code, not memory:
- `runner.py:run_edgar_filter` — `record.edgar_skipped = True` is set exactly when `record.cik is None` (after attempting `edgar.get_cik`).
- `filters.py:apply_edgar_filters` — `if record.edgar_skipped:` → `record.filter_passed_edgar = None` and the record is appended (pass-through).
- `edgar_client.py:get_cik` / `_load_ticker_map` — source is `https://www.sec.gov/files/company_tickers.json` (US issuer list).
- `cached_edgar_client.py` — `_TTL_SECONDS = 7 * 24 * 3600`; `_fetch_and_cache` writes both `has_restatement` and `has_going_concern`; `has_active_enforcement` is uncached.
- V3 spec §4.1 table — count the rows: confirm it is 9, and that PROJEKTSTAND's "8 V3-Filter" phrasing exists (search PROJEKTSTAND for "8 konkrete Knock-out").
- §4 contains **no** imperatives / recommendations / roadmap wording (no "sollte", "TODO", "als Nächstes", "empfohlen", priority ordering). It only describes current state. If any sentence prescribes action, rewrite it descriptively.

If any claim is unsupported, STOP and report. Otherwise continue.

- [ ] **Step 3: Commit**

```
git add docs/negative-filters-status.md
git commit -m "docs: add negative-filters audit — findings + score implications (TODO #10)"
```

---

### Task 3: Spec acceptance + Projektstand TODO #10 done

**Files:**
- Modify: `docs/superpowers/specs/2026-05-17-negative-filters-audit-design.md`
- Modify: `Projektstand.md`

- [ ] **Step 1: Tick spec acceptance criteria**

In `docs/superpowers/specs/2026-05-17-negative-filters-audit-design.md`, set every checkbox in "## Akzeptanzkriterien" to `- [x]` — but only after confirming each is literally true against the produced doc. Each criterion maps to a concrete fact:
- doc exists at `docs/negative-filters-status.md` ✓ (Task 1)
- Methodik begründet Volume-Einschluss ✓ (§1)
- Tabelle deckt 9 V3-§4.1 + Volume ✓ (§2, 10 rows incl. `+`)
- jede Zeile `datei:funktion`-Beleg + fixiertes Status-Vokabular ✓ (§2)
- Aufwand nur Grobskala ✓ (§1 defs + §2 column uses only Trivial/Klein/Mittel/Groß/Unklar/—)
- EU-CIK-Blindfleck prominent ✓ (§3.1, first finding)
- 8-vs-9 explizit aufgelöst, V3-Doc unverändert ✓ (§3.2)
- §4 rein deskriptiv ✓ (Task 2 Step 2 check)
- nur die .md im Diff ✓ (Tasks 1+2 touched only `docs/negative-filters-status.md`)
- Review verifiziert jede Zeile gegen Code ✓ (spec/code review tasks)

Do NOT tick anything not verifiably true.

- [ ] **Step 2: Mark TODO #10 done in Projektstand.md**

In `Projektstand.md`, find list item **10** under "## Nächste Session — Phase 2 TODOs" (currently:
`10. **Negativ-Filter-Audit (`docs/negative-filters-status.md`)** — Tabelle aller 8 V3-Filter mit Status ...`).
Rewrite it mirroring the done-style of items 7 and 11 (strikethrough + ✅ + date):
`10. ~~**Negativ-Filter-Audit (`docs/negative-filters-status.md`)**~~ ✅ (2026-05-17) — Audit aller effektiven Filter erstellt: 4 Basis-Filter (Volume/MarketCap/GrossMargin/RevenueGrowth) aktiv, Bruttomarge/Umsatz nur Single-Value (vereinfacht ggü. V3-Mehrjahres), 3 V3-Kriterien (Dilution/Verluste/neg. Marge) nicht implementiert, `has_active_enforcement` Stub, EDGAR nur US-CIK (EU-Blindfleck). Branch `chore/negative-filters-audit`.`

Also update the forward reference at the "Reihenfolge"/"Diese Woche — Quick Wins" list (search for `TODO #10`): mark the `Negativ-Filter-Audit-Doku (TODO #10)` bullet as done analog to how `Gemini 503-Retry (TODO #11)` was struck through:
`~~Negativ-Filter-Audit-Doku (TODO #10)~~ ✅ erledigt 2026-05-17`
Change nothing else in Projektstand.md (do NOT touch the unrelated `output/Universum/2026-05-Crosshits.md`).

- [ ] **Step 3: Commit**

```
git add docs/superpowers/specs/2026-05-17-negative-filters-audit-design.md Projektstand.md
git commit -m "docs: mark negative-filters audit (TODO #10) done"
```

---

## Self-Review

**Spec coverage** (each spec section → task):
- §1 Methodik (Volume-Begründung transparent) → Task 1 Step 1 ✓
- §2 Statustabelle (9 V3 + Volume, code-Beleg, fixiertes Vokabular, Grobskala) → Task 1 Step 1+2 ✓
- §3 Querschnitts-Befunde (EU-CIK prominent, 8-vs-9, Cache) → Task 2 ✓
- §4 strikt deskriptiv → Task 2 Step 1 + explicit imperative-scan in Step 2 ✓
- Korrektheits-Disziplin (Zeile-für-Zeile gegen Code) → Task 1 Step 2 + Task 2 Step 2 verification steps + reviewer mandate ✓
- Akzeptanzkriterien abhaken → Task 3 Step 1 ✓
- Projektstand TODO #10 done → Task 3 Step 2 ✓
- "nur die eine .md im Diff" → Tasks 1+2 only touch `docs/negative-filters-status.md`; Task 3 separately touches spec + Projektstand (doc-only, expected) ✓

**Placeholder scan:** No TBD/“fill in"/“similar to". Full doc content embedded verbatim in Task 1/2. Verification steps name exact files/symbols. ✓

**Type/name consistency:** Status vocabulary (`Aktiv` / `Aktiv (vereinfacht)` / `Stub` / `Nicht implementiert`) and effort scale (`Trivial`/`Klein`/`Mittel`/`Groß`/`Unklar`/`—`) used identically in §1 definitions and §2 table. File/function references (`filters.py:passes_*`, `runner.py:run_edgar_filter`, `edgar_client.py:has_*`, `cached_edgar_client.py`, `screener_record.py:from_yfinance_info`) consistent across tasks and match the spec's Datenbasis list. ✓
