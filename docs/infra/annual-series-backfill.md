# Betrieb: EDGAR-Jahresreihen vorwärmen (`dev_edgar_annual_series`)

**Wann:** einmal jährlich, **vor** einem Monatslauf. Nicht danach, nicht mittendrin.
**Dauer:** kalt ~16 min, warm ~1 min. Resumierbar — ein Abbruch kostet nichts.
**Kosten:** $0 (SEC ist kostenfrei, Firestore-Schreiben im Free-Tier).

## Warum überhaupt

Der Scoring-Pfad des Monatslaufs geht **nie** zur SEC. Er liest ausschließlich aus
`dev_edgar_annual_series` und benutzt auch abgelaufene Einträge — eine Stetigkeit über zehn
Jahre ändert sich nicht dadurch, dass das jüngste Jahr fehlt. Damit kann der Monatslauf die
1800-s-Deadline nicht durch Nachladen reißen.

Der Preis: **veraltete Reihen fallen von selbst nicht auf.** Genau dafür ist dieser Lauf da.

## Wann er fällig ist

Jeder Monatslauf schreibt zwei Zahlen nach `dev_screener_runs`:

| Feld | Bedeutung |
|---|---|
| `steadiness_stale` | Titel, deren Reihe benutzt, aber abgelaufen war |
| `steadiness_missing` | Titel ohne verwertbaren Eintrag — bekommen `n/a` |

Steigt `steadiness_stale` über ein paar Dutzend, ist der Backfill fällig. Steigt
`steadiness_missing` **ohne** dass sich das Universum geändert hat, stimmt etwas nicht — dann
zuerst nachsehen, nicht blind nachladen (eine geänderte Extraktion entwertet Einträge
absichtlich; siehe `EXTRACTION_SCHEMA`).

## Ausführen

```
set FISHERSCREEN_EDGAR_USER_AGENT=FisherScreen/1.0 name@example.com
uv run python -m scripts.backfill_edgar_annual_series --dry-run
uv run python -m scripts.backfill_edgar_annual_series
```

Der `--dry-run` löst nur die CIKs auf und rührt weder SEC noch Firestore an — er beantwortet
„wie viele Titel wären es?", bevor 16 Minuten laufen.

Ein erneuter Aufruf ist billig: bereits gecachte Einträge sind Treffer. Nach einem Abbruch
einfach noch einmal starten.

**Exit-Code ungleich null heißt: mindestens ein Titel ist nicht gewärmt worden.** Die
betroffenen CIKs stehen am Ende der Ausgabe. Ein transienter Fehler bricht den Lauf bewusst
nicht ab — er wird gezählt und beim nächsten Aufruf nachgeholt.

## Was der Lauf zuletzt ergab (2026-09-08)

890 eindeutige CIKs, 859 mit verwertbaren Reihen, 31 ohne greifendes Konzept, 0 Fehler,
15,7 min. Die 31 sind erwartet: Banken melden Zinsertrag statt `Revenues`, REITs taggen kein
`OperatingIncomeLoss`. Sie tragen eine 60-Tage-Negativ-TTL und werden turnusmäßig erneut
geprüft — nicht akademisch: Exxon steht seit einer Neuregistrierung unter einer anderen CIK
ohne Faktenbestand.

## Nicht vergessen

Das Vault-Runbook (`Wissen\Finanzen\FisherScreen\`) führt die manuellen Schritte rund um den
Monatslauf. Dort gehört eine Zeile hin, die auf diese Datei zeigt — sonst steht die
Jahresaufgabe nur im Repo und niemand sieht sie zum richtigen Zeitpunkt.
