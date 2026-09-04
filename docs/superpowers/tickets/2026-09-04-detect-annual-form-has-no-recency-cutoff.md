# Ticket: `detect_annual_form` kennt kein Aktualitätsfenster — ein 2020er 20-F gilt als „reicht ein"

**Opened:** 2026-09-04
**Priority:** korrektheitsrelevant, aber schmal. Betrifft ehemalige Filer, die sich deregistriert haben. Erzeugt kein falsches Dossier *ohne* Warnung — die Vintage-Kennzeichnung greift —, aber es entsteht ein Dossier auf jahrealten Zahlen, wo ein Quant-only-Dossier ehrlicher wäre.
**Status:** open

## Befund

`EdgarClientImpl.detect_annual_form(cik)` durchsucht das `recent`-Fenster der
SEC-Submissions nach `10-K`/`20-F` und liefert den gefundenen Typ — **ohne Datumsschnitt**.
Das Fenster umfasst bei großen Emittenten Hunderte Filings über viele Jahre.

Gemessen an BT Group (CIK `0000756620`, 867 Filings im Fenster):

```
20-F-Filings: 2020-05-21, 2019-05-23, 2018-05-24, 2017-05-25, 2016-05-19
neuestes Filing insgesamt: SC 13G/A (2024-02-06)
detect_annual_form -> 20-F
```

BT hat sein NYSE-ADR eingestellt und sich deregistriert; das letzte 20-F ist **über sechs
Jahre alt**. Der Resolver meldet trotzdem „20-F", Tool B würde das Filing von 2020 ziehen
und daraus ein Dossier bauen.

## Wie schlimm ist es wirklich

Nicht so schlimm, wie es klingt — und das ist wichtig für die Priorisierung:

- Die **Vintage-Kennzeichnung greift**. `_format_vintage_hint` feuert oberhalb von
  `VINTAGE_THRESHOLD_DAYS` (180 Tage), das Dossier trägt also einen Aktualitätshinweis,
  und die Confidence der Punkte 5/6/12 wird gekappt.
- Es entsteht also kein *stilles* Falschdossier, sondern ein gekennzeichnetes altes.

Aber: die Kappung betrifft drei von fünfzehn Punkten, und das Dossier präsentiert im
Übrigen sechs Jahre alte Substanz als Hard Scuttlebutt. Für einen Emittenten, der die
SEC-Berichterstattung *eingestellt* hat, ist ein Quant-only-Dossier mit ehrlichem Etikett
die bessere Antwort als ein volles auf totem Material.

## Warum es jetzt auffiel

`BT-A.L` musste als Override-Zeile aufgenommen werden
(`data/adr_table.json`, `no_annual_form`, verified 2026-09-04), weil der Resolver dort
sonst ein positives Verdikt gefällt hätte. Die Zeile ist damit ein **Workaround für diesen
Defekt**, kein Befund über BT — und sie ist die einzige Override-Zeile, deren Aussage die
Live-Probe nicht nachprüfen kann: `test_negative_row_named_cik_still_shows_no_annual_form`
überspringt sie ausdrücklich, weil `detect_annual_form` „hat vor sechs Jahren zuletzt
eingereicht" nicht von „reicht ein" unterscheiden kann. Sie hängt allein an der
`verified_on`-Frist.

Mit einem Aktualitätsschnitt wäre die Override-Zeile überflüssig und die Live-Probe könnte
auch sie prüfen.

## Scope

- **Ein Fenster festlegen und begründen.** Ein Jahresbericht erscheint jährlich; ein
  Emittent, dessen letztes 10-K/20-F älter als etwa 18–24 Monate ist, reicht nicht mehr
  ein. Der genaue Wert ist eine Entscheidung, kein Fakt — zu eng, und ein verspäteter
  Filer fällt heraus; zu weit, und Deregistrierte bleiben drin.
- **Fenster gegen den Bestand messen, nicht schätzen.** Die Watchlist-Dossiers und die 46
  positiven Zensus-Verdikte sind der Prüfbestand: wie viele davon würde ein 18-Monats-
  Fenster verlieren, und ist darunter ein Titel, der *tatsächlich* noch einreicht?
- **`BT-A.L` danach neu bewerten.** Wenn der Schnitt greift, kann die Override-Zeile
  entfallen — und die Live-Probe verliert ihren Skip.
- Der Rückgabewert bleibt `10-K | 20-F | None`; „hat mal eingereicht, tut es nicht mehr"
  ist genau `None`, kein neuer Zustand.

## Nicht in diesem Ticket

- Die Vintage-Kennzeichnung selbst (`VINTAGE_THRESHOLD_DAYS`). Sie tut, was sie soll, und
  arbeitet auf einer anderen Ebene: sie qualifiziert ein vorhandenes Filing, sie
  entscheidet nicht, ob eines existiert.
- Die Frage, ob ein deregistrierter Emittent überhaupt ein Dossier bekommen soll. Mit dem
  Quant-only-Pfad ist sie beantwortet: ja, ehrlich gekennzeichnet.

## Reproduktion

```
uv run python -c "from app.config import settings; from app.services.edgar_client import EdgarClientImpl; e=EdgarClientImpl(user_agent=settings.edgar_user_agent); print(e.detect_annual_form('0000756620'))"
```
liefert `20-F`; das jüngste 20-F unter dieser CIK stammt von 2020-05-21.
