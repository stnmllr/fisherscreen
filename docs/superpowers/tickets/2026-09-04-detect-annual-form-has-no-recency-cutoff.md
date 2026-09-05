# Ticket: `detect_annual_form` kennt kein Aktualitätsfenster — ein 2020er 20-F gilt als „reicht ein"

**Opened:** 2026-09-04
**Priority:** korrektheitsrelevant, aber schmal. Betrifft ehemalige Filer, die sich deregistriert haben. Erzeugt kein falsches Dossier *ohne* Warnung — die Vintage-Kennzeichnung greift —, aber es entsteht ein Dossier auf jahrealten Zahlen, wo ein Quant-only-Dossier ehrlicher wäre.
**Status:** FIXED 2026-09-05 — siehe „Resolution" unten.

## Resolution

`detect_annual_form` liest jetzt `form` und `filingDate` index-parallel aus demselben
Fetch, nimmt das **neueste** 10-K/20-F nach Datum und gibt `None` zurück, wenn es älter
ist als `DEFAULT_ANNUAL_FORM_MAX_AGE_DAYS` (540 Tage = 18 Monate, überschreibbar per
`FISHERSCREEN_ANNUAL_FORM_MAX_AGE_DAYS`). Rückgabewert bleibt `10-K | 20-F | None`.

**Das Fenster ist gemessen, nicht gewählt** — `scripts/measure_annual_form_recency.py`
über 69 Titel am 2026-09-05:

| Gruppe | Titel | Alter des jüngsten Jahresformulars |
|---|---|---|
| aktive Filer | 56 | ≤ 7,0 Monate |
| — | 0 | 7,0 → 18,2 Monate |
| deregistriert | 13 | 18,2 – 266,6 Monate |

Vier Dinge, die die Messung gegenüber der Vermutung oben verändert hat:

1. **Die Abnahmefrage ist objektiv beantwortet, nicht eingeschätzt.** Der Scope oben
   fragt, ob unter den Verlierern ein Titel ist, der tatsächlich noch einreicht. Das
   Messinstrument liest deshalb die **Form-15-Filings** mit (`15-12B` / `15F-12B` /
   `15F-12G`, die Bescheinigung über die Beendigung der Registrierung). **Alle dreizehn
   Verlierer haben eine.** Keiner ist ein verspäteter Filer — das Urteil hängt an einem
   Dokument der SEC, nicht an einer Meinung über den Emittenten.
2. **24 Monate wurde verworfen**, obwohl das Ticket 18–24 vorschlug: TEF.MC ist seit
   2026-01-20 abgemeldet und sein jüngstes 20-F 18,2 Monate alt — bei 24 Monaten bekäme
   es noch ein halbes Jahr lang ein volles Dossier auf toten Zahlen.
3. **Die Zahl „46 positive Zensus-Verdikte" im Scope stammt aus Zensus v1** und ist
   überholt; maßgeblich ist v3 nach dem Matcher-Umbau mit 60.
4. **Die Wirkung reicht über BT hinaus.** Die 13 sind sämtlich Zensus-Positive. Die
   Quote „hat eine SEC-Quelle" sinkt damit von 60 auf 47 von 416 EU-Titeln, **14,4 % →
   11,3 %** — genau die Zahl, die im Vault die ESAP-Entscheidung trägt, und sie bewegt
   sich in die Richtung, die die Lücke größer macht. Kein bestehendes Dossier ist
   betroffen: keiner der 13 steht in den September-Crosshits.

Drei Folgen, die der Fix mittragen musste:

- **Die Reihenfolge im Array ist keine tragende Annahme mehr.** `recent` ist heute
  newest-first, aber der SEC-Vertrag sagt das nirgends, und ein Emittent, der von 20-F
  auf 10-K wechselt, muss das neuere Formular melden. Fehlende Datumsangaben scheitern
  laut: ohne sie bliebe nur der datumslose Scan, und der **ist** der Defekt.
- **Beide `no_annual_form`-Notizen waren danach falsch.** „Reicht weder 10-K noch 20-F
  ein" trifft auf einen Deregistrierten nicht zu — er reichte ein und hörte auf. Sie
  nennen jetzt das Fenster.
- **Der ADR-Cache brauchte ein Werkzeug, das es nicht gab.** Der Schnitt entwertet
  *positive* Einträge (`resolved_20f` → `no_annual_form`), und die positive TTL beträgt
  180 Tage. `purge_adr_negative_verdicts.py` bewahrte die positiven ausdrücklich; es
  heißt jetzt `purge_adr_verdicts.py` und nimmt `--verdicts positive|negative|all`.

**`BT-A.L` bleibt in der Override-Tabelle** — anders als der Scope oben in Aussicht
stellte. Der Zensus v3 zeigt den Titel im Bucket `unverifiable_identity`: OpenFIGI
liefert für das Symbol `BRITANNIA GROUP PLC`, die Namensprüfung weist korrekt zurück.
Ohne die Zeile bekäme BT ein Quant-only-Dossier mit der Begründung „Identität
ungeprüft" statt des tatsächlichen, handgeprüften Befunds. Die Zeile ist nach dem Fix
erstmals **maschinell nachprüfbar**, und genau das war der andere versprochene Gewinn:
`test_negative_row_named_cik_still_shows_no_annual_form` überspringt sie nicht mehr,
sondern prüft sie — die Live-Probe hat ihren einzigen Skip verloren.

Bewusst nicht mitgemacht: `get_latest_annual_filing` bekommt **keinen** eigenen Schnitt.
Es wird nur mit einem `form_type` aufgerufen, den `detect_annual_form` gerade
freigegeben hat, und zieht dann dasselbe jüngste Formular; zwei Schnitte wären zwei
Definitionen eines Fensters. Ebenfalls offen und unberührt: die 40-F/F-6-Lücke
(Phase 2) und `VINTAGE_THRESHOLD_DAYS`.

Offen als Folgearbeit: ein erneuter Zensuslauf, der die 11,3 % belegt statt sie
herzuleiten, und die Zahl im Vault-Entscheidungsdokument.

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
