# Ticket: Zwei Viewer-Parser-Tests sind auf `main` rot — und dahinter steckt eine Warnung an einer Zeile ohne Zahlen

**Opened:** 2026-09-06
**Priority:** niedrig für die Ausgabe, hoch für die Ehrlichkeit der Suite. Es wird keine falsche Zahl angezeigt. Aber `-m integration` ist auf `main` seit dem 2026-09-03 rot, und eine dauerhaft rote Suite ist eine, die niemand mehr liest — der nächste echte Befund geht darin unter.
**Status:** FIXED 2026-09-06 — siehe „Resolution" unten.

## Resolution

Drei Dinge geändert, alle in `app/viewer` bzw. dessen Tests. Der Generator ist unangetastet.

**1. Der eigentliche Defekt: ⚠ an einer Zeile, die `n/a` sagt.**
`_range_line` (`app/viewer/render_detail.py`) übergab die **ganze Rohzeile** als Wert an
`_DefectCollector.take`. Die beginnt mit dem Label (`Bewertungs-Range: n/a (…)`), nicht mit
`n/a` — also griff die vorhandene Unterdrückung nicht, und `EDV.L` trug einen ⚠-Marker samt
Fußnote über einen EV-Definitions-Vergleich, den es auf einer `n/a`-Zeile nicht gibt.

Die Regel dagegen existierte längst und ist wörtlich dokumentiert: *„A cell without a value
is left alone: `D/E ⚠ n/a` warns about a number that is not on the page."* Sie wurde nur mit
dem falschen Argument gefüttert. Der Fix trennt das Label am ersten `": "` ab und übergibt
den Wertteil; gerendert wird weiter verbatim. Kein neues Konzept, `has_display_value` und
`take` unverändert.

Eine Zeile **ohne** `": "` fällt bewusst auf die ganze Zeile zurück und behielte damit ihren
Marker: „ich kann den Wert nicht abtrennen" ist kein Grund, eine bekannte Warnung
stillzulegen.

**2. Der Extras-Wächter prüfte einen Kanal ohne Konsumenten.**
`Bewertungs-Range` ist aus der Prüfliste von
`test_real_dossiers_have_no_unknown_valuation_or_capital_segments` entfernt. Begründung im
Docstring: Der Block steht bewusst **nicht** in `METRIC_BLOCKS`, wird von `_range_line`
verbatim gerendert, und `metric_extras["Bewertungs-Range"]` hat gar keinen Konsumenten —
dort kann nichts still verlorengehen. Für `Bewertung` und `Kapitalstruktur` bleibt der
Wächter scharf, denn deren Extras erreichen über `_metric_block` tatsächlich die Seite.

**3. Der Zähltest hatte zwei gepinnte Werte, nicht einen.**
Neben `len(dossiers) == 23` stand eine gepinnte 10-Ticker-Liste — sie wäre an `EDV.L`
genauso zerbrochen, pytest hat sie nur nie erreicht, weil der Count vorher failte. Beide
sind jetzt aus den vorhandenen Dateien abgeleitet: One-Pager-Namensmuster → `None`, alles
übrige → `Dossier`, Ticker-Liste aus den geparsten Dossiers. Ein `assert dossiers`
verhindert, dass der Test bei leerem Verzeichnis still durchläuft.

### Akzeptanz-Evidenz

Vorher, `output/site/ticker/EDV.L.html`:

```html
<div class="range-line">Bewertungs-Range: n/a (FX: Listing≠Reporting)
  <span class="defect" title="Die Range-Zeile stellt den .info-Enterprise-Value (TTM) …">⚠</span></div>
```

Nachher:

```html
<div class="range-line">Bewertungs-Range: n/a (FX: Listing≠Reporting)</div>
```

Fußnoten-Eintrag `⚠ Bewertungs-Range:` in `EDV.L` **0×**, in `GOOGL`/`FICO`/`ARGX` (echte
Range) unverändert **1×** — der Regressions-Zaun hält. Suite 1586 hermetisch grün / 96,69 %,
Integrationstests 7 passed (vorher 2 failed / 5 passed).

### Wo dieses Ticket selbst falsch lag

Der ursprüngliche Befund unten behauptet, die FX-Zeile rendere als **unbeschrifteter Chip**
und der Viewer könne den Zustand „nicht benennen". Beides ist falsch, geprüft am gebauten
HTML: `Bewertungs-Range` steht nicht in `METRIC_BLOCKS`, wird über `_range_line` **verbatim**
ausgegeben, und `metric_extras` erreicht für diesen Block nie den Renderer. Es gab nie eine
Anzeigelücke.

Der Fehler in der Diagnose kam daher, dass der Weg vom Testnamen (`…unknown_valuation…
segments`) auf die Anzeige geschlossen wurde, statt in die gerenderte Ausgabe zu sehen. Der
Test prüft ein Feld, das für diesen Block gar nicht gelesen wird — und genau deshalb feuerte
er ohne sichtbares Symptom. Die Lehre ist die schon einmal aufgeschriebene: **die gerenderte
Endausgabe ansehen, nicht vom Zwischenzustand auf sie schließen.**

### Was bewusst NICHT geändert wurde

- **Der Wortlaut `n/a (FX: Listing≠Reporting)` bleibt.** Er ist Teil einer im Generator
  dokumentierten und durchgängigen Konvention: *„Every derived field that cannot be computed
  renders `n/a (<reason>)` naming the missing input."* Eine einzelne Zeile davon
  auszunehmen macht die Konvention schlechter, nicht die Zeile besser. Und der Wortlaut ist
  Sache des Generators — der Viewer zeigt an (CLAUDE.md), er formuliert nicht um.
- **Die beiden Währungen zu nennen** (`Listing GBP ≠ Reporting USD` statt der abstrakten
  Form) wäre die einzige inhaltliche Verbesserung. Sie kostet aber mehr, als sie einbringt:
  `compute_valuation_history` kennt `listing_ccy`/`financial_ccy` nur im Gate, `ValuationHistory`
  trägt sie nicht, und das Modell ist **gecacht und schema-versioniert** — es liefe auf einen
  Schema-Bump auf dem bezahlten Tool-B-Pfad für einen kosmetischen Gewinn hinaus. Aufgehoben,
  falls die Dossier-Vorlage ohnehin einmal angefasst wird, zusammen mit
  `tickets/2026-09-03-toolB-cross-currency-mislabels.md`.
- **Die übrigen `_real_dossiers_present`-Tests.** Sie greifen namentlich auf einzelne
  Dateien zu (`KO_2026-05-26.md`). Das ist eine andere, schwächere Kopplung: verschwindet
  die Datei, wird der Test rot statt still falsch.

## Befund (ursprünglich, 2026-09-06 — Diagnose zu Punkt 1 überholt, siehe oben)

```
uv run python -m pytest tests\viewer\test_dossier_parser.py -m integration
FAILED test_real_watchlist_parses_every_dossier
FAILED test_real_dossiers_have_no_unknown_valuation_or_capital_segments
```

Beide brachen mit demselben Ereignis auf — dem ersten Quant-only-Dossier
(`EDV.L_2026-09-03.md`) —, haben aber **verschiedene Ursachen**, und nur eine davon ist
ein Mangel am Produkt. Sie zusammen als „die zwei roten Viewer-Tests" zu behandeln wäre
genau die Vermischung, die den einen Befund unter dem anderen begräbt. Das galt und gilt —
nur war der Mangel ein anderer als hier zunächst beschrieben.

### 1. `test_real_dossiers_have_no_unknown_valuation_or_capital_segments`

```
{'EDV.L_2026-09-03.md:Bewertungs-Range': ['n/a (FX: Listing≠Reporting)']}
```

Ihr Docstring sagt: *„Guard against a new metric being added to the generator without the
viewer's vocabulary noticing."* Das FX-Gate (`app/deepdive/valuation_history.py`) schreibt
bei Listing- ≠ Reporting-Währung den Platzhalter `n/a (FX: Listing≠Reporting)`, und das
Vokabular des Parsers kennt diesen Wert nicht.

> **Überholt:** Die ursprüngliche Fassung schloss daraus auf eine Anzeigelücke („nackter
> Chip"). Tatsächlich rendert der Block verbatim; die Prüfung greift für ihn ins Leere.
> Siehe Resolution.

### 2. `test_real_watchlist_parses_every_dossier` — der Test kann nicht grün bleiben

```python
"""23 of the 25 .md files are dossiers; the 2 one-pagers are not."""
assert len(dossiers) == 23
```

Er zählt Dateien in `output/Watchlist/`. Das Verzeichnis ist **gitignored** und enthält
lokal erzeugte Artefakte; jeder Deep Dive erhöht die Zahl. Aktuell 26 Dateien, 24
Dossiers, 2 One-Pager — der Test verlangt 23.

Das ist kein Regressionsbefund, sondern eine eingebaute Verfallszeit: der Test wird bei
jedem produktiven Lauf erneut rot und war nur so lange grün, wie niemand Tool B benutzt
hat. Ein gepinnter Zählwert auf ungetrackte Artefakte kann die Eigenschaft, die er meint
(„One-Pager sind keine Dossiers"), gar nicht ausdrücken.

## Reproduktion

```
uv run python -m pytest tests\viewer\test_dossier_parser.py -m integration
```
Auf `main` rot, verifiziert am 2026-09-05 gegen den unveränderten Stand — die Fehler
stammen nicht aus einem offenen Branch.
