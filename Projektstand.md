# FisherScreen — Projektstand

> **Single Source of Truth für den aktuellen Stand.**
> Wird am Ende jeder Arbeitssession aktualisiert.
> Verwandte Dokumente: `D:\programme\stef-vault\10_Projekte\FisherScreen\FisherScreen_Architektur_v3.md` (Architektur, extern),
> `docs/superpowers/brainstorm/` (Architektur-Entscheidungen),
> `docs/superpowers/plans/` (ausgeführte Implementations-Pläne).

---

## Letztes Update: 2026-05-12

## Status

**Aktueller Phase**: Phase 1.1 vollständig implementiert, noch nicht in `main` gemergt.
**Branch**: `feature/phase-1-1-data-pipeline` — 16 Commits, 87 Tests, 99% Coverage.

## Erledigt zuletzt

- 2026-05-10: Repo-Setup vollständig (10 Tasks, 23 Tests, 100% Coverage)
- 2026-05-11: Phase-1-Master-Brainstorm (`docs/superpowers/brainstorm/2026-05-11-phase-1-structure.md`)
- 2026-05-11: WatchGuard EPDR-Verhalten dokumentiert in CLAUDE.md
- 2026-05-12: **Phase 1.1 Data Pipeline + Basisfilter komplett implementiert** (8 Tasks, Plan `docs/superpowers/plans/2026-05-12-phase-1-1-data-pipeline.md`)

### Phase-1.1-Details (2026-05-12)

| Datei | Was |
|---|---|
| `app/config.py` | `ticker_collection`-Setting ergänzt |
| `app/models/screener_record.py` | `ScreenerRecord` Pydantic-Modell mit `from_yfinance_info()` |
| `app/services/firestore_client.py` | `FirestoreClientImpl` mit ADC fail-fast smoke call |
| `app/services/yfinance_client.py` | `YFinanceClientImpl`, thin wrapper |
| `app/services/cached_yfinance_client.py` | 24h-TTL-Cache über Firestore |
| `app/screener/filters.py` | 4 Basisfilter + `apply_basis_filters()` |
| `app/screener/runner.py` | `run_basis_filter()` — Ticker-Iteration, per-Ticker-Fehlerbehandlung |
| `app/screener/compose.py` | Composition root — einzige Stelle mit konkreten Implementierungen |

**Qualitäts-Korrekturen durch Code-Review (nicht im Plan):**
- bid/ask zero-normalization in `from_yfinance_info()` (yfinance liefert 0 statt None für OTC-Titel)
- `get_financials` Rückgabetyp `Any` statt `dict` (yfinance liefert pandas DataFrame)
- `ValidationError` in runner gefangen — malformed yfinance dicts crashen nicht den gesamten Lauf
- `filter_passed_basis = False` explizit auf failing records gesetzt (vorher `None` — stille Drei-Wert-Logik)
- `build_screener_pipeline()` gibt `YFinanceClient` Protocol zurück, nicht die konkrete Klasse

## Nächste Session

**Ziel**: PR erstellen + mergen, danach Phase 1.2 (EDGAR-Signale) planen

**Vorbereitung vorab (vor Phase 1.2-Start):**
- [x] GCP-Projekt `fisherscreen-prod` vorhanden
- [x] `gcloud auth application-default login` eingerichtet
- [ ] Firestore-API im Projekt `fisherscreen-prod` aktivieren (prüfen: GCP Console → APIs)
- [ ] `.env` mit `FISHERSCREEN_GCP_PROJECT_ID=fisherscreen-prod` befüllen

**Phase-1.2-Scope** (aus Brainstorm-Doku):
- `edgar_client.py`: `has_restatement` (submissions.json → 8-K Item 4.02) + `has_going_concern` (EFTS Full-Text)
- `has_active_enforcement` = Stub + Logger-Warnung
- Rate-Limiting, User-Agent-Validierung
- Caching: EDGAR-Ergebnisse per CIK in `dev_edgar_cache` mit TTL 7d
- Läuft nur auf dem reduzierten Set aus Phase 1.1 — niemals alle 2100 Ticker

## Offene Punkte (nicht-blockierend)

- [ ] PR `feature/phase-1-1-data-pipeline` → `main` erstellen und mergen
- [ ] IT-Ticket WatchGuard EPDR (strukturelle Lösung statt Workaround)
- [ ] Output-Pfad-Konflikt klären vor Phase 1.4: CLAUDE.md nutzt Top-Level `Universum/`, `Watchlist/`, `Portfolio/`; Brainstorm Decision D entschied `output/Universum/` etc.
- [ ] mypy strict / `@runtime_checkable` auf Protocols erwägen (I-2 aus Final Review) — vor Phase 2
- [ ] GICS-50 (Communication Services) zu F&E-Branchen hinzufügen? – nach erstem Lauf bewerten
- [ ] Status Telefon-Agent-Migration prüfen (Memory ist unklar)

## Parallele Projekte

- **Telefon-Agent**: Gemini-Migration. Memory sagt "anstehend, Deadline 1.6.2026", aber unklar ob bereits durch. **Beim nächsten Login in Telefon-Agent-Repo prüfen.**
- **RechPro**: Aktuell stabil, keine Aktivität geplant.

## Geänderte Annahmen / Pivots

- **`filter_passed_basis` ist binär nach apply_basis_filters**: Ursprünglich war `None` = "nicht geprüft" toleriert. Entschieden: nach einem Filter-Lauf ist der Zustand für jeden Record eindeutig (`True` oder `False`). `None` bleibt nur für noch nicht gelaufene Records gültig.
- **`get_financials` Rückgabetyp**: yfinance gibt einen pandas DataFrame zurück, kein dict. Annotation im Protocol auf `Any` gesetzt — wird relevant, wenn Phase 1.x Finanzdaten auswertet.
