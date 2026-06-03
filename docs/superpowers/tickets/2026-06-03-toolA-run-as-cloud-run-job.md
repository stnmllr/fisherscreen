# Tool-A-Lauf als Cloud-Run-Job statt blockierendem HTTP-Request

**Status:** Architektur-Backlog — NICHT jetzt gebaut.
**Erstellt:** 2026-06-03 (Nebenbefund der vier Failure-Mode-Fixes)

## Problem

`POST /run/monthly` (voll **und** `?dry_run=true`) führt den gesamten Universums-Lauf
**synchron im HTTP-Request** aus. Der kalte Integrations-Dry-Run am 2026-06-03 lief
**~28 min** (1699 s) in einem einzigen blockierenden Request; ein voller bezahlter Lauf
(mit Gemini-Scoring) liegt eher bei 30–60 min.

Folgen:
- **curl-/Client-Timeouts** sind die Norm, nicht die Ausnahme — der Client trennt, bevor
  der Server fertig ist. Das Ergebnis lebt nur in den Cloud-Run-Logs (die Drop-/Aggregat-
  Zeilen am Lauf-Ende), nicht in einer abgreifbaren Antwort. Die ganze
  „aus-den-Logs-lesen"-Verifikation dieser Session ist ein Symptom davon.
- **Cloud-Run-Request-Timeout** ist hart bei 3600 s. Ein Lauf, der das überschreitet
  (mehr Titel, EFTS-Flakiness mit langem Backoff, langsames Gemini), wird **mitten im Lauf
  abgebrochen** — und die am Ende geloggte Drop-Liste geht verloren.
- **Retries des Cloud Scheduler** (max 2) können einen langlaufenden Request doppelt
  auslösen, wenn das erste Mal als Timeout gewertet wird.

## Vorschlag

Den Lauf von der Request-Latenz entkoppeln:

1. **Cloud Run Job** (statt Service-Request) für den Monatslauf — vom Scheduler getriggert,
   kein HTTP-Timeout, beliebige Laufzeit; **oder** der Endpoint nimmt den Auftrag an
   (202 Accepted) und arbeitet asynchron weiter.
2. **Persistierter Output** des Laufs (Report-JSON + Drop-/Aggregat-Listen) in
   Firestore/GCS unter einer `run_id`, sodass das Ergebnis **abgreifbar** ist statt nur
   in flüchtigen Logs — die Dry-Run-Vorschau und die Verifikation lesen dann das
   persistierte Artefakt, nicht die Logs.
3. Der bestehende `dev_screener_runs`-Cost-Tracking-Record ist der natürliche Anker für
   diese `run_id`.

## Out of Scope (jetzt)

- Die vier Failure-Mode-Fixes (Logging, yfinance-Resolution, EFTS-Backoff, GC-Polarität)
  sind unabhängig und bereits live; dieses Ticket ändert nur die **Ausführungs-/Liefer-
  Architektur**, nicht die Filter-Logik.
