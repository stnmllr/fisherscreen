# Build enforcement screening (currently inert no-op)

**Status:** Future work — NOT built now.
**Erstellt:** 2026-06-03 (im Rahmen von PR-A „Log-Hygiene")

## Aktueller Zustand

`EdgarClientImpl.has_active_enforcement(cik)` in `app/services/edgar_client.py`
gibt konstant `False` zurück — es ist ein bewusst inertes No-op. Der Aufruf-Seam
in `app/screener/runner.py::_evaluate_edgar` und der Protocol-Vertrag bleiben
erhalten, damit die spätere Implementierung ohne Schnittstellen-Änderung
einklinken kann.

In PR-A wurde das pro-CIK-`logger.warning(...)` entfernt: bei einem vollen Lauf
erzeugte es **538 WARNING-Zeilen** reines Rauschen (eine pro US-CIK), die die
eigentlichen Aggregat-Logs (`basis_filter`, `edgar_skipped total=...`,
Runner-Stage-Counts) überdeckten. Die Methode ist jetzt still: gleiches
Verhalten (`False`), kein Log.

## Offen: Datenquelle

Die Datenquelle für ein echtes Enforcement-Signal ist **noch offen**. Kandidaten:

- **SEC Litigation Releases** — keine saubere API, Scraping/HTML-Parsing nötig.
- **AAERs (Accounting & Auditing Enforcement Releases)** — speziell auf
  Bilanz-/Prüfungsverstöße fokussiert, hohe Relevanz für Integritäts-Signal.
- **SEC Administrative Proceedings** — administrative Verfahren der SEC.

EU-Pendants (BaFin/FCA/AMF/CNMV) sind ein separater, ebenfalls offener
Blindfleck und nicht Teil dieses Tickets.

## Relevanz

Fisher Punkt 15 (Integrität des Managements): Ein **aktives** SEC-Enforcement-
Verfahren ist ein Negativ-Filter-Signal (Knock-out-Kandidat). Sobald eine
belastbare Datenquelle gewählt ist, soll `has_active_enforcement` ein echtes
`True`/`False` liefern und in die Negativ-Filter-Kaskade einfließen
(`app/screener/filters.py`).

## Definition of Done (Skizze, nicht jetzt)

1. Datenquelle auswählen und dokumentieren.
2. `has_active_enforcement` real implementieren (mit Caching analog
   `cached_edgar_client.py`, da netz-/parse-teuer).
3. Tests fixtures-only (kein echter Netz-Call), inkl. positiver Enforcement-Fall.
4. Filter-Kaskade verdrahten und im Negativ-Filter-Audit dokumentieren.
