# Phase 1 (Tool A lokal) — Struktur-Brainstorm

**Datum:** 2026-05-11
**Status:** Entscheidungen getroffen, bereit für writing-plans

---

## Kontext

Tool A ist der monatliche Screener: startet mit dem GICS-Universum (~2100 Ticker),
läuft negative Filter durch und gibt eine priorisierte Watchlist zurück.
Phase 1 = vollständig lokal lauffähig, ohne Cloud-Run-Deployment.

---

## Entschiedene Fragen

### A) Firestore: Native von Tag 1

**Entscheidung:** Nativer Firestore gegen GCP-Projekt `fisherscreen-prod` ab Phase 1.1.
Lokale Entwicklung via `gcloud auth application-default login` (ADC).
Während Phase 1 Prefix `dev_` auf allen Collections.

**Abgelehnte Alternativen:**

| Variante | Abgelehnt weil |
|----------|----------------|
| JSON-Datei-Cache | Brückentechnologie — in Phase 2 wegzuwerfen, doppelte Arbeit |
| Firestore-Emulator | Java + SDK-Setup, nicht vertretbar für Single-Developer-Tool |
| Nativer Firestore | ✅ Gewählt — realitätsnah, Free-Tier-gedeckt, keine Schulden |

**Konsequenz:** Sub-Phase 1.1 umfasst yfinance + Firestore-Client (real) + Datenmodell +
Basisfilter. Firestore-Caching für yfinance-Daten mit TTL ab Tag 1.

### B) EDGAR-Sequenzierung: Bewusst nach Basisfilter

**Entscheidung:** EDGAR-Lookups erst auf dem reduzierten Set nach Phase 1.1.
Niemals alle 2100 Ticker per EFTS abfragen.

**Begründung:**
- Faktor ~5x weniger Requests: ~2100 → ~400 nach Basisfilter
- SEC Fair Access Policy nicht überreizen
- Penny Stocks brauchen keine Going-Concern-Prüfung — fallen am Market-Cap-Filter raus

### C) EDGAR-Option: Differenzierte Teilimplementierung

**Entscheidung:** Option 3 — zwei Signale echt implementiert, eines explizit gestubbt.

| Signal | Methode | Datenqualität |
|--------|---------|---------------|
| `has_restatement` | submissions.json → 8-K Item 4.02 (Non-reliance) | 95%+ |
| `has_going_concern` | EFTS Full-Text → `"raise substantial doubt"` in 10-K/10-Q (24 Monate) | ~85% |
| `has_active_enforcement` | `return False` + Logger-Warnung + explizites TODO | n/a |

**Warum Enforcement zurückstellen:**
- AAER-Latenz: Meldung erscheint 2–3 Jahre nach Verfahrensbeginn → Signal zu spät
- Kein CIK-basiertes API → Name-Matching instabil (Tochterfirmen, Umbenennungen)
- Reputationsschäden durch Enforcement erscheinen früher in News (Marketaux, Phase 2)
- False Positives bei Going Concern sind für einen Negativfilter akzeptabel (lieber konservativ)

### D) Output-Pfad: Repo-relativ, kein Obsidian-Vault-Setting

**Entscheidung:** Output-Pfade sind repo-relativ. Kein `FISHERSCREEN_OBSIDIAN_VAULT_PATH`
in der Config.

```
output/
  Universum/     ← alle gefilterten Ticker mit Score
  Watchlist/     ← Top-Kandidaten nach Gemini-Scoring
  Portfolio/     ← manuell gepflegte Positionen (Phase 2)
```

Obsidian-Sync via Git-Plugin (Obsidian liest das Repo-Verzeichnis direkt).
Kein direkter Filesystem-Write in einen Obsidian-Vault-Pfad.

**Konsequenz für Phase 2 (Cloud Run):** Cloud Run schreibt dieselben repo-relativen Pfade
in einen gemounteten GCS-Bucket oder per GitHub Actions push — kein Umbau des Output-Layers.

---

## Sub-Phasen-Struktur

### Phase 1.1 — Data Pipeline + Basisfilter

**Scope:**
- `yfinance_client.py` (real): Ticker-Info, Historical, Financials
- `firestore_client.py` (real): get/set/delete mit TTL-Metadaten
- Datenmodell: `ScreenerRecord` (Pydantic, alle Felder für Basisfilter + EDGAR + Score)
- Basisfilter: Market Cap, Durchschnittsvolumen, Penny Stock (< $1), Liquidität (Bid-Ask)
- Caching-Strategie: yfinance-Daten per Ticker mit TTL 24h in Firestore `dev_ticker_cache`

**Output:** Reduziertes Ticker-Set (~400 von ~2100), bereit für Phase 1.2.

**Dependencies:** GCP-Projekt `fisherscreen-prod` vorhanden, ADC konfiguriert.

---

### Phase 1.2 — EDGAR-Signale

**Scope:**
- `edgar_client.py` (real): `has_restatement`, `has_going_concern`; `has_active_enforcement` = Stub
- Rate-Limiting: `asyncio.sleep` zwischen EFTS-Calls, User-Agent-Header validieren
- Caching: EDGAR-Ergebnisse per CIK in Firestore `dev_edgar_cache` mit TTL 7d

**Input:** Reduziertes Set aus Phase 1.1 (CIK-Lookup über yfinance `info['cik']`).
**Output:** Set bereinigt um Going-Concern- und Restatement-Unternehmen.

**Kritische Bedingung:** EDGAR-Lookup läuft **nie** über alle 2100 Ticker.
Der Einstiegspunkt ist immer das gefilterte Set aus Phase 1.1.

---

### Phase 1.3 — Gemini-Scoring

**Scope:**
- `gemini_client.py` (real): Gemini Flash Lite für Massen-Scoring
- Fisher-Prinzipien-Bewertung: 1–5 relevante Prinzipien pro Ticker anhand verfügbarer Daten
- Token-Zähler pro Run; Cost-Cap bei 500k Tokens (bereits in Config)
- Caching: Gemini-Scores in Firestore `dev_gemini_scores` mit TTL 30d

**Input:** Set nach Phase 1.2 (Negativfilter durchlaufen).
**Output:** `ScreenerRecord` mit Score-Feldern, sortiert nach Gesamt-Score.

---

### Phase 1.4 — Markdown-Output

**Scope:**
- Markdown-Generator: ein File pro Ticker in `output/Universum/`, `output/Watchlist/`
- Frontmatter mit Score, Datum, GICS-Sektor, Marktkapitalisierung
- Index-Datei: `output/Universum/_index.md` mit Tabelle (Ticker, Score, Top-Flags)
- Kein `FISHERSCREEN_OBSIDIAN_VAULT_PATH` in Settings

**Input:** Vollständige `ScreenerRecord`-Liste aus Phase 1.3.
**Output:** Markdown-Dateien im Repo, von Obsidian via Git-Plugin gelesen.

---

## Risiko-Mapping

| Risiko | Phase | W'keit | Impact | Mitigation |
|--------|-------|--------|--------|-----------|
| EFTS rate limit (429) | 1.2 | Hoch | Mittel | Nach Basisfilter ~400 Ticker; exponential backoff |
| EDGAR User-Agent fehlt → 403 | 1.2 | Mittel | Hoch | Früh-Validierung in `edgar_client.__init__`; in `.env.example` prominent |
| Gemini Token-Cap überschritten | 1.3 | Mittel | Mittel | Token-Zähler per Run; Cap in Code (nicht nur Config) |
| yfinance liefert `None` für Pflichtfelder | 1.1 | Mittel | Mittel | `ScreenerRecord` toleriert `None`; Filter loggt und überspringt |
| Firestore-ADC nicht konfiguriert | 1.1 | Niedrig | Hoch | Fehler früh und klar: `DataSourceError("ADC not configured")` |
| Enforcement-Stub wird permanent | Post-1.4 | Hoch | Niedrig | Logger-Warnung bei jedem Call sichert Sichtbarkeit |
| CIK-Lookup schlägt für Ticker fehl | 1.2 | Mittel | Niedrig | EDGAR-Check überspringen, im Record flaggen: `edgar_skipped=True` |
| False Positives Going Concern | 1.2 | Niedrig | Niedrig | Konservativfilter akzeptabel; im Markdown-Output flaggen |

---

## Nicht in Phase 1

Folgende Punkte sind bewusst ausgeklammert:

- `has_active_enforcement` — Stub, explizit dokumentiert, Phase 2
- Apify (Glassdoor/Kununu) — kostenpflichtig, Tool A nutzt keine Paid APIs
- Marketaux News — kostenpflichtig, Tool A nutzt keine Paid APIs
- Cloud Run Deployment — Phase 2
- Firestore Security Rules — Phase 2 (lokale ADC-Entwicklung reicht)
- Portfolio-Collection — manuell, Phase 2

---

## Nächste Schritte: writing-plans-Sessions

Jede Sub-Phase bekommt eine eigene writing-plans-Session und einen eigenen Feature-Branch.

| Session | Plan-Datei | Feature-Branch |
|---------|-----------|----------------|
| Phase 1.1 | `docs/superpowers/plans/2026-05-XX-phase-1-1-data-pipeline.md` | `feature/phase-1-1-data-pipeline` |
| Phase 1.2 | `docs/superpowers/plans/2026-05-XX-phase-1-2-edgar-signals.md` | `feature/phase-1-2-edgar-signals` |
| Phase 1.3 | `docs/superpowers/plans/2026-05-XX-phase-1-3-gemini-scoring.md` | `feature/phase-1-3-gemini-scoring` |
| Phase 1.4 | `docs/superpowers/plans/2026-05-XX-phase-1-4-markdown-output.md` | `feature/phase-1-4-markdown-output` |

**Einstieg empfohlen:** Phase 1.1 — Data Pipeline. Begründung: Alle anderen Phasen
hängen an `ScreenerRecord` (Datenmodell) und dem Firestore-Client. Das Modell
muss zuerst stabil sein, damit die anderen Pläne konkrete Typen und Felder benennen können.
