# Prepasses holen drei Abschlüsse, verwenden einen

**Status:** Backlog (Entscheidung Stephan 2026-10-08) · Herkunft: `docs/superpowers/specs/2026-10-08-monthly-run-deadline-design.md`

## Problem

`_assess_definedness_basket` (`app/screener/runner.py:412`, Abruf `:214`) und
`_assess_revenue_growth_trajectory` (`:415-417`, Abruf `:284`) rufen bei jedem Monatslauf
ungecacht `get_annual_statements` auf (`app/services/cached_yfinance_client.py:59-62`). Das holt
income_stmt, cashflow und balance_sheet (`app/services/yfinance_client.py:251-259`), verwendet wird
nur `[0]` (income_stmt). Geschätzt ~800 s pro Lauf (aus Firestore-Zeitstempeln abgeleitet, nicht gemessen).
`CachedRevenueSeries` (`app/services/revenue_series_cache.py:71-89`) hat dasselbe Muster.

## Vorschlag

- Eigener `get_income_statement(ticker)` im yfinance-Wrapper; Prepasses und Revenue-Cache nutzen ihn.
  Spart rund zwei Drittel der Prepass-Zeit, reine Strukturänderung.
- Vorher Phasendauern loggen, damit die ~800 s gemessen statt abgeleitet sind.
- **Nicht** in diesem Ticket: Trajectory-Prepass aus `dev_revenue_series` speisen — das ändert die
  Datenfrische (bis 150 Tage alt) und braucht eine eigene Entscheidung.

## Dringlichkeit

Niedrig, solange der Lauf als Cloud Run Job läuft (keine 1800-s-Grenze mehr).
