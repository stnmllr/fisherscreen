# Phase 1.4 — Insider-Transactions (Form-4): Design-Spec

> **Status:** Spec. Brainstorm: `docs/superpowers/brainstorm/2026-06-01-phase-1-4-insider-form4.md`.
> Master-Plan: `docs/superpowers/plans/2026-05-27-phase-1-pareto-b2.md`.
> **Plan ist die nächste, separate Session** (kein writing-plans hier).
> Datum: 2026-06-01.

## 1. Ziel & Scope

Tool B zieht zusätzlich zum 10-K die **Form-4-Insider-Filings** desselben Filers über EDGAR, klassifiziert sie code-gerechnet, und speist eine `InsiderSummary` in (a) das Gemini-Synthesis-Prompt und (b) das Dossier. Anker: **Fisher P15 „Unanfechtbare Integrität"** (Alignment/Integrität). **US-spezifisch:** Foreign Private Issuers (`form_type==20-F`, z. B. NOVO/ASML) sind Section-16-exempt → kein Form-4.

**Nicht in dieser Phase** (siehe §13): 10b5-1 / exercise-and-sell als Signal-Discriminator, %-Holdings als Signifikanz-Trigger, `files`-Overflow jenseits des `recent`-Fensters, DEF-14A (1.5).

**Plan-Korrektur (Code-Check):** Master-Plan/Brainstorm sagen „P11/P15". `app/deepdive/fisher_points.py`: **P11 = „Branchenspezifische Wettbewerbsvorteile"** — hat mit Insidern keine natürliche Verbindung. Insider ankert **P15 solo**; P11 wird **nicht** als Insider-Anker erzwungen (verhindert tenuöse Reasoning-Brücken).

## 2. Start-Check (echter Code) & Probe-Befunde

- **`edgar_client.py`** — `EdgarClientImpl` über `data.sec.gov/submissions/CIK<padded>.json` (`recent`-Arrays index-aligned: `form`/`accessionNumber`/`primaryDocument`/`filingDate`). Rate-Limit 0,5 s. `_get` (JSON) / `_get_text` (Text). Service-Layer-Regel: **alle EDGAR-HTTP-Calls im Wrapper**.
- **`pipeline.py`** — `run_deep_dive` linear [1]–[6]; `submissions.json` wird in [2] fürs 10-K geladen.
- **`filing_cache.py`** — per-cik FS-Cache + `_meta.json`, atomic, fail-soft-auf-korrupt (`_load_meta`-Idiom).
- **`historical_cache.py`** — `CACHE_SCHEMA_VERSION`-Gate: Mismatch → Cache-Miss + Refetch; korrupt → leer + WARNING.
- **`deep_dive_record.py`** — Sub-Modelle sind **pydantic `BaseModel`, `model_config = ConfigDict(extra="forbid")`** (Vorlage: `ValuationHistory`, `PeerComparison` — **nicht frozen**). `SourceCoverage.insider = "folgt B.2"` (Platzhalter, hier ersetzt). `form_type: Literal["10-K","20-F"]`.
- **`synthesis.py`** — `run_synthesis(*, ticker, form_type, sections, quant, synthesizer, max_input_tokens, filing_date=None)`. Hard-Cap: Punkte 14 **und** 15 → 🔴. Source-Marker-Vokabular `_MARKER_CANON` (`_normalize_sources` vor `_validate_sources`). Vintage-Hybrid: Code-Cap (`VINTAGE_THRESHOLD_DAYS`, `VINTAGE_SENSITIVE_POINTS`) + sichtbarer Prompt-`Aktualitäts-Hinweis`.
- **`dossier_generator.py`** — rendert `cov.insider` (Z. 98); nutzt `render_valuation_block` (DRY-Muster: derselbe Renderer in synthesis **und** dossier).

**Probe (frei, kein Gemini):**
- `primaryDocument` = `xslF345X06/form4.xml` ist die **XSL-HTML**; Raw-XML = `primaryDocument.split("/")[-1]` im selben Accession-Ordner.
- MSFT = **122 Form-4 / 12M** (729 im `recent`-Fenster 2019–2026). Erst-Lauf ~60–70 s @ 0,5 s, danach Cache-Hit.
- XML `<ownershipDocument>` (X0609): `reportingOwner.reportingOwnerRelationship` (`isDirector`/`isOfficer`/`isTenPercentOwner` 0/1, `officerTitle` Freitext), `nonDerivativeTable`→`nonDerivativeTransaction` (`transactionCode` S/F/P/A/M/G, `transactionShares`, `transactionPricePerShare`, `transactionAcquiredDisposedCode` A/D, `sharesOwnedFollowingTransaction`, `directOrIndirectOwnership` D/I), `derivativeTable`, `footnotes`.
- **10b5-1 (teilgepinnt, ehrlich):** `<aff10b5One>1</aff10b5One>` = geplant (an NVDA 2026-05-29 `S` **bestätigt**). `=0` (diskretionär/nicht affirmiert) und Element-Abwesenheit (ältere Filings) sind **inferiert** — im TDD an einem echten diskretionären Filing zu verifizieren. `noAff10b5One` im Sample nicht beobachtet, aber das SEC-Schema kennt das Paar → **Parser defensiv auf das `aff10b5One`/`noAff10b5One`-Paar** auslegen, nicht Einzel-Boolean annehmen. Mapping: `aff==1`→`True`; `noAff==1`→`False`; `aff==0` ohne `noAff`→`False`; beide abwesend→`None`.

## 3. Datenmodell (`app/models/deep_dive_record.py`)

Beide pydantic `BaseModel`, `ConfigDict(extra="forbid")` (Spiegel von `ValuationHistory`/`PeerComparison`, nicht frozen).

```python
InsiderRole = Literal["CEO", "CFO", "Director", "Officer", "TenPercentOwner", "Other"]
InsiderBucket = Literal["buy", "sell", "routine"]
InsiderCoverage = Literal["ok", "partial", "empty", "fetch_failed", "fpi_exempt", "skipped"]

class InsiderTransaction(BaseModel):
    model_config = ConfigDict(extra="forbid")
    owner_name: str
    role: InsiderRole
    officer_title: str | None = None
    is_director: bool = False
    is_officer: bool = False
    is_ten_pct: bool = False
    date: str | None = None                 # transactionDate
    code: str                               # raw transactionCode
    bucket: InsiderBucket                    # classified (§6)
    shares: float | None = None
    price: float | None = None              # transactionPricePerShare
    value: float | None = None              # shares*price, None if either missing
    acquired_disposed: Literal["A", "D"] | None = None
    security_title: str | None = None
    is_derivative: bool = False
    shares_after: float | None = None       # sharesOwnedFollowingTransaction
    direct_or_indirect: Literal["D", "I"] | None = None
    is_10b5_1: bool | None = None           # §2 pin: aff10b5One 1/0/absent
    significant: bool = False               # §6

class InsiderSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage_state: InsiderCoverage
    window_label: str = "letzte 12 Monate"
    # --- Filing-Ebene (Denominator) ---
    n_filings_total: int = 0                 # form==4 in window (index count)
    n_parsed: int = 0                        # XMLs successfully fetched+parsed
    # --- Transaktions-Ebene (reconciles: total = sig_buys + sig_sells +
    #     immaterial_sell_count + routine_count) ---
    n_transactions_total: int = 0            # alle Transaktionen aus n_parsed Filings
    significant_buys: list[InsiderTransaction] = Field(default_factory=list)
    significant_sells: list[InsiderTransaction] = Field(default_factory=list)
    immaterial_sell_count: int = 0           # bucket=sell, significant=False (<Schwelle)
    routine_count: int = 0                   # bucket=routine NUR (A/M/F/G + unknown + Derivate)
    net_buy_value: float = 0.0               # Σ value(P, acquired)
    net_sell_value: float = 0.0              # Σ value(significant S, disposed)
    by_role: dict[str, dict[str, float]] = Field(default_factory=dict)  # role -> {buy,sell}
```

`DeepDiveRecord` bekommt: `insider_summary: InsiderSummary | None = None` (eigenes Top-Level-Feld — **nicht** auf `quant_snapshot` huckepack).

## 4. EDGAR-Client-Erweiterung (Service-Layer)

`EdgarClient`-Protocol + `EdgarClientImpl`:

```python
@dataclass(frozen=True)
class Form4Ref:
    accession_number: str
    primary_document: str
    filing_date: str

def get_form4_index(self, cik: str, since: str) -> list[Form4Ref]: ...
def get_form4_document(self, cik: str, accession_number: str, primary_document: str) -> str: ...
```

- `get_form4_index` lädt `submissions.json` **bewusst neu** (ein Index-Call, vernachlässigbar gegen N XML-Pulls — „gratis" bezieht sich auf den Endpunkt, nicht den Call; saubere Schicht-Trennung statt [2]-Internals durchzureichen), filtert `form=="4"` ∧ `filingDate >= since`, gibt `list[Form4Ref]` zurück. **Edge:** nur das `recent`-Array (≈1000 Filings); reicht das 12M-Fenster über das älteste `recent`-Datum hinaus (ultra-aktive Filer) → WARNING + Coverage-Hinweis „Fenster reicht über recent hinaus"; `files`-Overflow ist Backlog (§13).
- `get_form4_document` strippt den `xslF…/`-Prefix (`primary_document.split("/")[-1]`) und gibt das **Raw-XML** via `_get_text` zurück.

## 5. Cache (`app/deepdive/insider_cache.py`)

`CachedInsiderFetcher` (deepdive-Layer, wrappt `EdgarClient`):

```python
def get_summary_input(self, cik: str, since: str, use_cache: bool) -> InsiderFetchResult: ...
# InsiderFetchResult: transactions: list[InsiderTransaction], coverage_state, n_filings_total, n_parsed
```

- **Per-Accession-Cache:** `cache/insider/<cik>/<accession>.json` = `{schema_version, _cached_at, transactions: [...]}`. Form-4 sind **immutable** → **keine TTL-Frische-Prüfung**, nur `INSIDER_CACHE_SCHEMA_VERSION`-Gate (Start v1). Die Accession-**Liste** wird jeden Lauf frisch via `get_form4_index` abgeleitet (fängt neue Filings; Re-Run zieht nur neue XMLs). **Pre-Netting** gecached (geparste Transaktionen, nicht die Summary — Schwellen-Tuning ohne Refetch).
- Bump-Regel als Einzeiler-Kommentar (wie `historical_cache`): „bump bei Add/Remove/Rename eines im Read-Pfad genutzten Transaktions-Felds".
- Korrupt/Schema-Mismatch → Cache-Miss + WARNING (filing_cache-Idiom), kein Crash.
- **Fail-soft pro XML:** ein kaputter/fehlender Pull wird übersprungen + WARNING, `n_parsed` < `n_filings_total` → Coverage `partial`.
- **Coverage-State-Logik** (der gefährliche (empty)↔(fetch_failed)-Kollaps wird strukturell verhindert):
  - Index-Call wirft / nicht erreichbar → `fetch_failed`, `n_filings_total=0`.
  - Index ok, `len==0` → `empty` (echte Null).
  - Index `N>0`, `n_parsed==0` → `fetch_failed` (N gefunden, 0 geholt — **nie** als `empty` gerendert).
  - Index `N>0`, `0<n_parsed<N` → `partial`.
  - Index `N>0`, `n_parsed==N` → `ok`.

## 6. Parser (`insider_parser.py`) & Summary/Netting (`insider_summary.py`)

**Parser** `parse_form4(xml: str) -> list[InsiderTransaction]`: ein Owner pro Filing; iteriert `nonDerivativeTable` (is_derivative=False) **und** `derivativeTable` (is_derivative=True). Rolle aus `officerTitle`-Match (best-effort, §6.2). `is_10b5_1` aus `aff10b5One` (§2-Pin). `value = shares*price` (None wenn eins fehlt — z. B. `A`-Grants ohne Preis).

**§6.1 Klassifikation** (`bucket`, nach `transactionCode`, nur `nonDerivativeTable` signal-fähig):
- `P` → `buy` · `S` → `sell` · `A`,`M`,`F`,`G` → `routine`
- **Unbekannter Code** (C/X/D/I/J/W/V/…) → `routine` + **WARNING** „unknown transactionCode %r" (Katalog-Wachstums-Signal, 1.2-Linie) — zählt im Nenner, mis-signalisiert nicht.
- **Alle Derivate** (`is_derivative=True`) → `routine`, egal welcher Code (Comp per Konstruktion; Signal-Net zieht **ausschließlich** `nonDerivativeTable`).

**§6.2 Signifikanz** (Code-gerechnet, nicht Modell-Urteil):
- Jeder `buy` (P) ist signifikant (Rarität).
- Ein `sell` (S) ist signifikant gdw. **eines** gilt:
  - `abs(value) > INSIDER_SIGNIFICANCE_USD` (= 1_000_000; None-Preis → nicht $-signifikant)
  - Rolle CEO/CFO (Titel-Match, best-effort: case-insensitive Substring auf {`chief executive`, `ceo`, `principal executive officer`} bzw. {`chief financial`, `cfo`, `principal financial officer`}; „President" **bewusst ausgeschlossen** — mehrdeutig, durch $1M+Aggregat backstopped)
  - **Per-Owner-Aggregat**: Σ diskretionärer `sell`-value desselben Owners im Fenster `> INSIDER_SIGNIFICANCE_USD` → **markiert ALLE Konstituenten** dieses Owners `significant=True` (Math reconciled; Renderer gruppiert sie per Owner, §7). Kein synthetischer Aggregat-Eintrag.
- **Dedup:** `significant` ist ein Bool pro Transaktion; mehrfach-getriggerte Transaktion erscheint **einmal**.
- **`immaterial`**: ein `sell` mit `significant=False` (unter allen Schwellen) ist **immateriell**, **nicht** Routine — zählt in `immaterial_sell_count`, nie in `routine_count` (Routine ist strikt A/M/F/G + unknown + Derivate).
- **%-Holdings: nur Anzeige** (§7), **kein** Trigger diese Phase.

**§6.3 role-Ableitung (Display-Determinismus).** Das einzelne `role`-Literal wird nach fester Präzedenz aus Titel+Flags abgeleitet (Mehrfach-Flag-Owner wie Director∧Officer deterministisch): Titel-CEO → `CEO`; sonst Titel-CFO → `CFO`; sonst `isOfficer` → `Officer`; sonst `isDirector` → `Director`; sonst `isTenPercentOwner` → `TenPercentOwner`; sonst `Other`. **Signifikanz (§6.2) nutzt Titel+Bools direkt** — diese Präzedenz ist NUR für `role`/`by_role`/Display.

**Netting & Zähler:** `net_buy_value = Σ value(buy, acquired)`; `net_sell_value = Σ value(significant sell, disposed)`; `by_role` (light: role→{buy,sell}). Käufe/Verkäufe **getrennt**. **Reconciliation-Invariante** (im TDD geprüft): `n_transactions_total == len(significant_buys) + len(significant_sells) + immaterial_sell_count + routine_count`. Einheiten nie mischen: `n_filings_total`/`n_parsed` = Filing-Ebene, der Rest = Transaktions-Ebene.

## 7. Renderer (`insider_block.py`)

`render_insider_block(summary: InsiderSummary | None, form_type: str) -> str` — von synthesis **und** dossier importiert (DRY, wie `render_valuation_block`).

- `fpi_exempt`: „**Insider-Transaktionen:** nicht anwendbar (Foreign Private Issuer, Section-16-exempt — kein Form-4)."
- `skipped`: „**Insider-Transaktionen:** übersprungen (`--no-insider`)."
- `fetch_failed`: „**Insider-Transaktionen:** Fetch fehlgeschlagen ({n_parsed}/{n_filings_total} XMLs) — **kein Urteil möglich** (nicht „kein Signal")."
- `empty`: „**Insider-Transaktionen:** 0 Form-4 in {window} (für einen US-Filer auffällig — ggf. Datenlücke)."
- `ok`/`partial`: **einheiten-explizite Nenner-Zeile** (mischt nie Filings mit Transaktionen): „**Insider-Transaktionen:** {n_filings_total} Form-4-Filings · darin {n_transactions_total} Transaktionen → {sig} signifikant ({nb} Käufe, {ns} Verkäufe) · {immaterial_sell_count} immateriell · {routine_count} Routine (A/M/F/G)" [+ „· {n_parsed} von {n_filings_total} geparst" bei `partial`]. Danach je signifikante Zeile — **bei Aggregat-Trigger per Owner gruppiert** (Owner-Kopf + Konstituenten-Zeilen), sonst flach:
  - `{owner} ({role}) {date}: {code} {shares:,.0f} @ {price} = {value}` [%-Suffix] [10b5-1-Suffix]
  - **%-Suffix fail-soft + Vorzeichen an `acquired_disposed`:** nur wenn `shares_after is not None` **und** `direct_or_indirect=="D"` **und** Nenner > 0. Disposal (`D`): `pct = shares/(shares_after+shares)` → „— hält nun {shares_after:,.0f} = **−**{pct:.0%} der direkten Holdings". Acquisition (`A`, z. B. P-Buy): `pre = shares_after-shares`; bei `pre>0` `pct = shares/pre` → „… = **+**{pct:.0%}" (Beteiligungs-Aufbau = stärkeres Conviction-Signal). Indirekt/fehlend/Nenner≤0 → **weglassen** (keine irreführende Zahl).
  - **10b5-1-Suffix (neutral):** `True`→„(10b5-1-geplant)", `False`→„(ungeplant)", `None`→ weglassen.

## 8. Synthesis-Integration (`synthesis.py`) — P15-Floor-Hybrid

**2a.3/2a.3b-Hybrid wiederverwendet** (Code-Cap + sichtbarer Prompt-Hinweis, nicht neu erfunden):

1. **Code-Cap (objektiver Trigger):** Der P14/P15→🔴-Hard-Cap wird aufgeteilt:
   - **P14 bleibt unverändert hart 🔴** (Sprache = B.4).
   - **P15 nach Evidenzstärke (code-entschieden, dreistufig):** `coverage_state=="ok"` ∧ `n_parsed>0` → **kein Boden** (Modell setzt frei, 🟢 möglich). `coverage_state=="partial"` → **Cap auf 🟡** (unvollständige Evidenz, code-erzwungen wie der Vintage-Cap — nicht dem Modell überlassen). `empty`/`fetch_failed`/`fpi_exempt`/`skipped`/None → **hart 🔴**, gelesen als **„keine harte Quelle"**, nicht als Integritäts-Bedenken (deshalb §8.3).
2. **Source-Marker:** `Form-4` wird ins Vokabular aufgenommen (harte Quelle, erlaubt 🟢, **kein** Inferenz-Collapse, **kein** Downgrade) — Eintrag in der Quant-/Soft-Vokabular-Linie analog `yfinance, 5J`. SOURCES-Prompt-Zeile nennt `Form-4` für Insider-belegte Aussagen.
3. **Prompt-Block + Hinweis (sichtbar):** Der gerenderte `render_insider_block(...)` wird ins User-Prompt eingefügt (wie `vintage_block`) — **co-präsent in jedem Zustand**, damit ein P15-🔴 bei FPI/zero kohärent als „nicht anwendbar/keine Daten" lesbar ist. Plus P15-Nudge (analog P13-Nudge): „P15 (Integrität): Open-Market-Käufe (P) = starkes Alignment-Signal; ungewöhnlich große Verkäufe = Vorsicht; Routine-RSU-Vesting/Steuer-Einbehalt NICHT überinterpretieren; bei `nicht anwendbar`/keinen Daten bleibt P15 🔴 = fehlende Quelle, kein Negativ-Urteil."
4. **System-Prompt-Edit:** Zeile „Punkte 14 und 15 ohne Sprach-/Insider-Daten ⇒ 🔴" → „Punkt 14 ohne Sprachdaten ⇒ 🔴. Punkt 15: 🟢/🟡 nur belegbar, wenn der Insider-Block harte Form-4-Daten zeigt; fehlen sie ⇒ 🔴."

`run_synthesis` bekommt `insider_summary: InsiderSummary | None = None`.

## 9. Pipeline / Compose / CLI

- **`pipeline.run_deep_dive`**: neuer Param `insider_fetcher`, neuer Param `no_insider: bool = False`. Neue Stage **[2b]** nach [2]:
  - `form_type=="20-F"` → `InsiderSummary(coverage_state="fpi_exempt")`, kein Fetch.
  - `no_insider` → `coverage_state="skipped"`.
  - sonst `insider_fetcher.get_summary_input(resolved.cik, since, use_cache)` → `compute_insider_summary(...)`. **Fail-soft-Grenze (explizit):** der try/except fängt **NUR `DataSourceError`** → `coverage_state="fetch_failed"` (analog forward-estimates in `quant_join`; Insider ist additiv, bricht den Deep-Dive nie ab). **Alles andere — `ValidationError`, `KeyError`, echte Logik-Bugs — propagiert (fail-loud, vgl. ValidationError→Exit-3-Lehre).** Kein Catch-all; „darf nie abbrechen" gilt nur für Datenquellen-Fehler, nicht für Programmfehler.
  - `since = (today - insider_lookback_days).isoformat()`.
  - Ergebnis → `record.insider_summary` + an `run_synthesis` durchgereicht.
- **`compose.build_insider_fetcher()`** → `CachedInsiderFetcher(edgar=EdgarClientImpl(settings.edgar_user_agent), cache_dir=Path("cache/insider"))`.
- **CLI** (`__main__.py`): `--no-insider` (skip-Stage, ergonomischer Schnell-Iterations-Pfad bei 60–70 s Erst-Lauf). Wiring in `main()`.

## 10. Dossier & Frontmatter

- Neue Sektion **`## Insider-Transaktionen`** nach dem Bewertungsblock: `render_insider_block(record.insider_summary, record.form_type)`.
- `SourceCoverage.insider` dynamisch (ersetzt „folgt B.2"): z. B. `ok` → „12M Form-4: N/N geparst, X signifikant (a Käufe, b Verkäufe)"; `empty`/`fetch_failed`/`fpi_exempt`/`skipped`/`partial` entsprechend.
- **Frontmatter-Digest** (Obsidian-Konsistenz, maschinen-lesbar): `insider_coverage_state`, `insider_n_filings`, `insider_significant_count`, `insider_net_buy`, `insider_net_sell`.

## 11. Config

`app/config.py`: `insider_lookback_days: int = 365`. (Kein TTL-Setting — Cache immutable.) `INSIDER_CACHE_SCHEMA_VERSION = 1` lebt im `insider_cache`-Modul. `INSIDER_SIGNIFICANCE_USD = 1_000_000` als Modul-Konstante in `insider_summary` (Single-Source, tunbar).

## 12. Test-Plan (TDD — RED zuerst, pro Unit)

- **parser**: `nonDerivative` Roundtrip (S/P); `derivativeTable` → is_derivative=True/routine; 10b5-1 Tri-State (aff=1→True, =0→False, absent→None; defensiv noAff); fehlender Preis → value None; unbekannter Code → routine+WARNING; Rolle aus Titel (CEO/CFO/PEO/PFO/Director/Officer/10%).
- **summary**: Drei-Eimer-Netting; Signifikanz je Trigger ($1M / CEO/CFO / Per-Owner-Aggregat); Per-Owner-Aggregat markiert ALLE Konstituenten significant; Dedup (mehrfach-Trigger = 1×); Käufe immer signifikant; **immaterieller Sell (<$1M, kein CEO/CFO) ≠ Routine** (eigener Zähler); **Reconciliation-Invariante** `n_transactions_total == sig_buys+sig_sells+immaterial+routine`; role-Präzedenz (Director∧Officer deterministisch); by_role.
- **cache**: accession-keyed Hit/Miss; schema_version-Gate; korrupt → Miss+WARNING; immutable (kein TTL-Ablauf); pre-Netting (Transaktionen, nicht Summary).
- **fetcher (coverage-states)**: `ok`/`partial`/`empty`/`fetch_failed` — **explizit `empty` ≠ `fetch_failed`** (der (2)↔(3)-Kollaps-Test); `partial` = k/N; per-XML-fail-soft.
- **block-renderer**: alle 6 Zustände; einheiten-explizite Nenner-Zeile (Filings ≠ Transaktionen); %-Suffix fail-soft **+ Vorzeichen** (A→`+`, D→`−`, Formeln §7, Nenner≤0→weglassen); Owner-Gruppierung bei Aggregat-Trigger; 10b5-1-Suffix-Tri-State.
- **synthesis**: P15 **dreistufig** — `ok`∧n_parsed>0 → 🟢 möglich; `partial` → **Cap auf 🟡**; `empty`/`fetch_failed`/`fpi`/`skipped`/None → 🔴; **P14 bleibt 🔴**; `Form-4`-Marker nicht zu Inferenz kollabiert, kein Downgrade; Insider-Block im Prompt co-präsent.
- **pipeline/compose**: FPI-Skip (20-F, kein Fetch); `--no-insider`-Skip; fail-soft-Wrap (DataSourceError → fetch_failed, Deep-Dive läuft weiter); `since`-Berechnung.
- **Volle Suite** ≥ 96 % (kein Regress unter aktuellem Stand), `uv run python -m pytest`.

## 13. Bewusst zurückgestellt (Honest-Label)

- **10b5-1 / exercise-and-sell als Signal-Discriminator** — `is_10b5_1` wird geparst, gespeichert, neutral gerendert, aber **nicht** in Signifikanz/Netting genutzt. Nachrüstbar **ohne Refetch** (Pre-Netting-Cache, §5).
- **%-Holdings als Signifikanz-Trigger** — diese Phase nur Anzeige; Trigger nach Akzeptanz-Lauf nachrüstbar (Pre-Netting-Cache).
- **`files`-Overflow** jenseits des `recent`-Fensters (ultra-aktive Filer mit >recent Form-4 in 12M) — Backlog; diese Phase WARNING + Coverage-Hinweis.
- **20-F-Insider** (FPI) — manuelle Director's-Dealings-Routine (Phase-2-Backlog, vgl. PROJEKTSTAND Phase-1-Lücken).

## 14. Entscheidungs-Log (Brainstorm + Spec-Schärfungen)

- W0→A: alle 12M, accession-keyed (immutable, no-TTL), pre-Netting, Nenner-Honest-Label, fail-soft pro Fetch.
- W1: Drei-Eimer (P buy / S sell / A,M,F,G routine), Net nur `nonDerivativeTable`.
- W2: Signifikanz $1M ∨ CEO/CFO ∨ Per-Owner-Aggregat; `isDirector`-pauschal gestrichen; %-Holdings nur Anzeige.
- W3: eigenes `insider_summary`-Record-Feld (kein quant-Huckepack); pydantic BaseModel/extra=forbid (nicht frozen — Code-Konvention).
- W4: FPI-by-`form_type`; vier+zwei Coverage-States; (empty)↔(fetch_failed)-Kollaps strukturell verhindert.
- S-A: P15-only Floor-Lift (P14 bleibt 🔴, P11 **nicht** Anker); `Form-4`-Marker; 2a.3-Hybrid (Code-Cap + sichtbarer Hinweis); 🔴 = fehlende Quelle, co-präsentes Honest-Label.
- S-F: 10b5-1 teilgepinnt (aff=1 bestätigt; =0/absent in TDD zu verifizieren), Tri-State befüllt, defensiv auf aff/noAff-Paar, neutral gerendert, nicht im Netting.
- Frontmatter-Digest: ja. `--no-insider`: ja (ergonomisch, billig).

**Spec-Review-Amendments (2026-06-01, post-Review):**
1. **Filing- vs. Transaktions-Einheiten** — `n_transactions_total` ergänzt; Reconciliation-Invariante; `immaterial_sell_count` (nicht-signifikanter diskretionärer Sell ≠ Routine); Nenner-Zeile einheiten-explizit. (Kern-Versprechen Denominator-Ehrlichkeit.)
2. **%-Suffix Vorzeichen + Formel** — an `acquired_disposed` gekoppelt (A→`+`, D→`−`); Formeln explizit (D: `shares/(shares_after+shares)`, A: `shares/(shares_after-shares)`, Nenner≤0→weglassen). Behebt Render-Bug bei P-Buys.
3. **Per-Owner-Aggregat → significant** — markiert ALLE Konstituenten, Renderer gruppiert per Owner; kein synthetischer Eintrag.
4. role-Präzedenz §6.3 (Display-Determinismus). 10b5-1 Claim ehrlich + aff/noAff-Paar. `partial` → P15-Cap 🟡 (Evidenzstärke). Fail-soft-Grenze: NUR `DataSourceError` degradiert, Logik-Bugs propagieren (fail-loud).
