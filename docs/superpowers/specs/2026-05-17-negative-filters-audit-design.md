# Design: Negativ-Filter-Audit-Doku (`docs/negative-filters-status.md`)

**Datum:** 2026-05-17
**TODO:** Phase-2 #10 (Quick Win vor 2026-06-01-Lauf)
**Branch:** `chore/negative-filters-audit`
**Typ:** Reines Audit-/Doku-Artefakt — kein Code, kein Test, keine Verhaltensänderung.

---

## Problem

PROJEKTSTAND markiert den Negativ-Filter-Status als „⚠️ Unklar / Audit
notwendig": V3 §4.1 spezifiziert 8–9 Knock-out-Kriterien, aber welche davon
im Code real wirken — und auf welcher Datenbasis — ist nirgends dokumentiert.
Ohne diese Klarheit ist jede Score-Interpretation unehrlich (man weiß nicht,
ob ein Titel einen Filter passiert hat oder der Filter nur nicht lief), und
die Tool-B-EDGAR-Pipeline hat keine belastbare Ausgangsbasis.

## Ziel

Eine einzige Markdown-Datei `docs/negative-filters-status.md` (Repo-Root-
`docs/`, exakt wie in TODO #10 spezifiziert), die für jeden effektiven
Filter ehrlich festhält: V3-Soll, Code-Ist, Status, Datenquelle,
Aktivierungsaufwand — plus die Querschnitts-Befunde, die in keine
Einzelzeile passen.

## Nicht-Ziele (YAGNI / Disziplin)

- **Keine Priorisierung / Roadmap** der Gap-Schließung — das sind
  PROJEKTSTAND-TODOs, nicht Audit-Inhalt.
- **Kein Fix der V3-Doc-Drift** (8-vs-9-Zählung, L1–L5-Drift) — separater
  Backlog-Punkt; hier nur *dokumentieren*, nicht beheben.
- **Keine Code-Änderung**, kein Test, keine Filter-Aktivierung.
- **Keine Stundenschätzungen** — altern schlecht, suggerieren falsche
  Genauigkeit.

## Scope-Entscheidung (bewusst über TODO-Wortlaut hinaus)

TODO #10 sagt „Tabelle aller 8 V3-Filter". Die Doku deckt bewusst **alle
effektiven Filter** ab — die 9 V3-§4.1-Kriterien **plus** den Nicht-V3-
Volume-Safeguard (`MIN_AVG_DAILY_VOLUME`) — weil ehrliche Score-
Interpretation jeden real wirkenden Filter braucht, nicht nur die
spezifizierten. Diese Scope-Erweiterung wird im Methodik-Absatz des
Dokuments **transparent begründet**, nicht versteckt.

## Dokumentstruktur (4 Abschnitte)

### Abschnitt 1 — Methodik (2–3 Sätze)

Erklärt: TODO #10 nennt „8 V3-Filter"; dieses Audit deckt zusätzlich den
real aktiven Nicht-V3-Volume-Filter ab, weil die Score-Basis von *allen*
wirkenden Filtern bestimmt wird. Verweis auf Decisions-Log 2026-05-17
(Volume-Filter-Begründung) und V3-Architektur §4.1 als Soll-Quelle.

### Abschnitt 2 — Statustabelle

Eine Zeile je Filter. Spalten:

`Filter | V3-Bezug (§4.1 / Fisher-Punkt) | V3-Soll-Schwelle | Code-Ist | Status | Datenquelle | Aktivierungsaufwand`

**Status-Vokabular (fixiert):**

- **Aktiv** — implementiert und wirkt wie V3 spezifiziert
- **Aktiv (vereinfacht)** — implementiert, aber methodisch reduziert ggü. V3
  (z. B. Single-Value statt Mehrjahres-Historie)
- **Stub** — Funktion existiert, gibt aber konstant Pass zurück
- **Nicht implementiert** — kein Code, kein Datenfeld vorhanden

**Aktivierungsaufwand — Grobskala (fixierte Definitionen, keine Stunden):**

- **Trivial** — Schwellen-/Config-Wert, keine neue Datenquelle
- **Klein** — neues Feld aus vorhandenem yfinance-`info`-Dict + eine
  Filterfunktion + Tests
- **Mittel** — neue Datenquelle (z. B. yfinance financials/balance-sheet-
  Historie) + Mehrjahres-Aggregationslogik + Tests
- **Groß** — neue externe Integration ohne saubere API (z. B. SEC
  Litigation, Nicht-US-Regulatoren BaFin/FCA/AMF/CNMV)
- **Unklar** — keine bekannte verlässliche Datenquelle; Research-Spike nötig

**Abzudeckende Zeilen** (Reihenfolge wie V3 §4.1, Volume am Ende):

| # | Filter | erwarteter Status (Investigations-Ergebnis) |
|---|---|---|
| 1 | Insolvenz / Chapter 11 / Going Concern | teils: Going-Concern via EFTS (US-only), Chapter-11/Insolvenz-Status nicht geprüft |
| 2 | Marktkapitalisierung < 2 Mrd EUR | Aktiv (`passes_market_cap_filter`, FX-normalisiert) |
| 3 | Bruttomarge < 30 % in 8/10 Jahren | Aktiv (vereinfacht) — Single-Value `grossMargins` ≥ 0.30 |
| 4 | Negative Bruttomarge in 2/3 letzten Jahren | Nicht implementiert |
| 5 | Umsatz-CAGR 10J < 0 % | Aktiv (vereinfacht) — Single-Value YoY `revenueGrowth` ≥ 0 |
| 6 | Aktien-Outstanding-Wachstum > 5 % p.a. / 5J | Nicht implementiert (kein Datenfeld) |
| 7 | Verluste in 5/10 letzten Jahren | Nicht implementiert (keine Net-Income-Historie) |
| 8 | Aktive SEC-Enforcement | Stub (`has_active_enforcement` → konstant False) |
| 9 | Restatement letzte 3 Jahre | Aktiv (US m. CIK; EU `edgar_skipped`) |
| + | Volume ≥ 100k Avg-Daily (Nicht-V3) | Aktiv (`passes_volume_filter`) |

Jede Zeile referenziert den belegenden Code als `datei:funktion`.

### Abschnitt 3 — Querschnitts-Befunde

Was in keine Einzelzeile passt:

- **EU-CIK-Blindfleck** (prominent platziert): `has_restatement` /
  `has_going_concern` / `has_active_enforcement` greifen nur bei
  auflösbarer CIK (`get_cik` via `company_tickers.json`, US-zentriert).
  Alle ~485 EU-Ticker erhalten `edgar_skipped=True` → drei EDGAR-Filter
  sind für ~⅓ des Universums still inaktiv. Beleg:
  `runner.py:run_edgar_filter`, `filters.py:apply_edgar_filters`.
- **8-vs-9-Diskrepanz**: V3 §4.1-Tabelle hat 9 Kriterienzeilen;
  PROJEKTSTAND konsolidiert auf „8". Explizit aufgelöst (Going-Concern
  und Insolvenz in V3 in einer Zeile gebündelt), **nicht** gefixt.
- **Cache-Verhalten**: EDGAR-Signale (restatement + going_concern)
  gemeinsam mit 7d-TTL gecacht; `has_active_enforcement` ungecacht
  (Stub). Beleg: `cached_edgar_client.py`.

### Abschnitt 4 — Implikationen für Score-Interpretation (strikt deskriptiv)

**„Was ist", nicht „was zu tun ist".** Beschreibt sachlich, was die
dokumentierten Lücken für die Lesart der Mai-/Juni-Ergebnisse bedeuten
(z. B. „ein EU-Titel ohne Restatement-Flag wurde nicht geprüft, nicht
freigesprochen") und welche Datenlücken die Tool-B-EDGAR-Pipeline
vorfindet. **Keine** Empfehlungen, **keine** Roadmap, **keine**
Priorisierung — diese Disziplin macht das Dokument langlebig.

## Datenbasis (bereits investigiert — fix)

`app/screener/filters.py`, `app/screener/runner.py`,
`app/services/edgar_client.py`, `app/services/cached_edgar_client.py`,
`app/models/screener_record.py`, V3-Architektur §4.1
(`D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`).

## Korrektheits-Disziplin (kritisch — es ist ein Audit)

Jede Statuszeile MUSS durch eine konkrete `datei:funktion`-Referenz auf
realen Code belegbar sein. Kein behaupteter Status ohne Code-Beleg. Das
Review prüft die Tabelle **Zeile für Zeile** gegen den realen Code — kein
„close enough". Ein falsch als „Aktiv" deklarierter Stub ist ein
Audit-Versagen, kein kosmetischer Fehler.

## Akzeptanzkriterien

- [ ] Datei `docs/negative-filters-status.md` existiert (Repo-Root-`docs/`)
- [ ] Methodik-Absatz begründet Volume-Filter-Einschluss transparent
- [ ] Statustabelle deckt alle 9 V3-§4.1-Kriterien + Volume ab
- [ ] Jede Zeile hat `datei:funktion`-Codebeleg, Status aus fixiertem Vokabular
- [ ] Aktivierungsaufwand nur Grobskala (Trivial/Klein/Mittel/Groß/Unklar), keine Stunden
- [ ] EU-CIK-Blindfleck prominent in Abschnitt 3
- [ ] 8-vs-9-Diskrepanz explizit aufgelöst, V3-Doc nicht geändert
- [ ] Abschnitt 4 rein deskriptiv — keine Roadmap/Empfehlung/Priorisierung
- [ ] Keine Code-/Teständerung im Diff (nur die eine .md-Datei)
- [ ] Review verifiziert jede Statuszeile gegen den genannten Code
