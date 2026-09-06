# Ticket: Zwei Viewer-Parser-Tests sind auf `main` rot — eine Wache, die funktioniert, und ein Test, der es nicht kann

**Opened:** 2026-09-06
**Priority:** niedrig für die Ausgabe, hoch für die Ehrlichkeit der Suite. Es wird keine falsche Zahl angezeigt. Aber `-m integration` ist auf `main` seit dem 2026-09-03 rot, und eine dauerhaft rote Suite ist eine, die niemand mehr liest — der nächste echte Befund geht darin unter.
**Status:** open

## Befund

```
uv run python -m pytest tests\viewer\test_dossier_parser.py -m integration
FAILED test_real_watchlist_parses_every_dossier
FAILED test_real_dossiers_have_no_unknown_valuation_or_capital_segments
```

Beide brachen mit demselben Ereignis auf — dem ersten Quant-only-Dossier
(`EDV.L_2026-09-03.md`) —, haben aber **verschiedene Ursachen**, und nur eine davon ist
ein Mangel am Produkt. Sie zusammen als „die zwei roten Viewer-Tests" zu behandeln wäre
genau die Vermischung, die den einen Befund unter dem anderen begräbt.

### 1. `test_real_dossiers_have_no_unknown_valuation_or_capital_segments` — die Wache tut, was sie soll

```
{'EDV.L_2026-09-03.md:Bewertungs-Range': ['n/a (FX: Listing≠Reporting)']}
```

Ihr eigener Docstring sagt es: *„Guard against a new metric being added to the generator
without the viewer's vocabulary noticing."* Genau das ist passiert. Das FX-Gate
(`app/deepdive/valuation_history.py`) schreibt bei Listing- ≠ Reporting-Währung den
Platzhalter `n/a (FX: Listing≠Reporting)` in die Bewertungs-Range-Zeile, und das
Vokabular des Parsers kennt diesen Wert nicht.

**Nichts geht dabei verloren und nichts wird falsch angezeigt.**
`_metric_block` (`app/viewer/render_detail.py:231-243`) rendert unbekannte Werte als
`<span class="tag">` — der Text erscheint, nur als nackter Chip statt als erklärter
Zustand. Der Leser sieht „n/a (FX: Listing≠Reporting)" ohne Hinweis darauf, dass das eine
bewusste Enthaltung ist und keine fehlende Berechnung.

Das ist der Teil mit echtem Inhalt: **der Viewer soll diesen Zustand benennen können.**
„Range nicht berechenbar, weil Notierungs- und Berichtswährung auseinanderfallen" ist eine
Aussage über die Datenlage, keine Lücke — und der Viewer ist der Kanal, der laut
CLAUDE.md ausschließlich *anzeigt*, was im Dossier steht. Er zeigt es an; er erklärt es
nur nicht.

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

## Scope

- **Das FX-Gate-Ergebnis ins Vokabular aufnehmen**, damit die Range-Zeile als bewusste
  Enthaltung lesbar ist statt als unbeschrifteter Chip. Der Wortlaut kommt aus dem
  Generator und darf im Viewer **nicht neu berechnet oder umgedeutet** werden — die
  Grenze aus CLAUDE.md („nur Anzeige") gilt: erkennen und kennzeichnen, nicht
  interpretieren.
- **Den Zähltest auf die Eigenschaft umstellen, die er meint.** Nicht „es sind 23", sondern
  „eine Datei, deren Name das One-Pager-Muster trägt, ergibt `None`; jede andere ergibt ein
  `Dossier`". Das ist prüfbar, ohne einen Bestand zu pinnen, den der Betrieb verändert.
- **Prüfen, ob dieselbe Klasse anderswo steckt.** `_real_dossiers_present` gattet mehrere
  Tests auf dasselbe Verzeichnis; ein zweiter gepinnter Zählwert wäre derselbe Defekt.

## Nicht in diesem Ticket

- Das FX-Gate selbst (`app/deepdive/valuation_history.py`). Es ist korrekt und war 2026-09-03
  ausdrücklich als richtig bestätigt — es verweigert die Mehrjahres-Range, statt Pence-Preise
  mit Pfund-Fundamentaldaten zu mischen.
- Die übrigen Cross-Currency-Etiketten:
  `tickets/2026-09-03-toolB-cross-currency-mislabels.md`.
- Der Viewer-Deploy: `tickets/2026-08-20-viewer-deploy-fisher-subpath.md`.

## Reproduktion

```
uv run python -m pytest tests\viewer\test_dossier_parser.py -m integration
```
Auf `main` rot, verifiziert am 2026-09-05 gegen den unveränderten Stand — die Fehler
stammen nicht aus einem offenen Branch.
