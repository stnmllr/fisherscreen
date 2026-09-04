# Ticket: Unsponsored ADRs liegen in einer eigenen Aktiengattung — der `shareClassFIGI`-Anker sieht sie nicht

**Opened:** 2026-09-04
**Priority:** niedrig nach Messung, aber die Klasse ist real. Betrifft heute nachweislich 2 von 416 EU-Titeln; die wahre Größe ist unbekannt, weil der bisherige Suchpfad selbst defekt war.
**Status:** open

## Kontext

Der Wechsel von der Volltextsuche auf den `shareClassFIGI`-Anker
(`tickets/2026-09-04-openfigi-search-unpaginated.md`) hat im Zähllauf 13 Titel korrigiert
und **einen regressiert**. Die Regression ist kein Zufall, sondern eine Eigenschaft der
Gattung.

**`ALLFG.AS` (Allfunds Group):**

```
Heimatlinie ALLFG NA   ALLFUNDS GROUP PLC          shareClassFIGI = BBG00ZXRMBB5
ADR         AFNDY US   ALLFUNDS GROUP PLC ADR UNSP shareClassFIGI = BBG01Z88QXG7
```

Zwei verschiedene Gattungs-FIGIs. Der Anker liefert die Geschwister der *Stammaktie*, das
unsponsored ADR gehört nicht dazu. Vor der Umstellung fand die Volltextsuche `AFNDY`
(CIK 2101973), jetzt lautet das Verdikt `no_us_line`.

**`MONY.L` (MONY Group)** ist derselbe Fall mit einer zusätzlichen Pointe: die US-Linie
ist `MNSKY` / „MONEYSUPERMARKET.CO-UNSP ADR". MONY Group hieß früher
Moneysupermarket.com. Der alte Namensfilter `_same_issuer` verwarf sie also wegen einer
**Umfirmierung** — es ist die richtige Firma —, und der neue Anker findet sie aus dem
Gattungsgrund ebenfalls nicht. Beide Pfade scheitern, aus unterschiedlichen Gründen.

## Warum die naheliegende Lösung nicht gewählt wurde

„Anker **und** Suche vereinigen" wäre die vollständige Antwort und wurde bewusst
zurückgestellt:

- **Gemessener Nutzen heute: ein Titel.** `ALLFG.AS` — und der hat ohnehin kein
  Jahresformular (`no_annual_form`), die Deep-Dive-Eignung ändert sich also nicht, nur die
  Präzision des Grundes. `MONY.L` gewönne die Vereinigung nicht, weil der Namensfilter die
  umfirmierte Linie weiterhin verwürfe.
- **Gemessenes Risiko: der Namensfilter hält nicht.** `norm_issuer("ROCHE HOLDING AG")`
  schrumpft auf `"ROCHE"` (`" HOLDING"` steht in `_LEGAL_FORMS`), und `"ROCHE"` ist ein
  Präfix von `"ROCHEBOBOIS-UNSPONADR"` — `_same_issuer` akzeptiert Bobois. Eine
  Vereinigung brächte diesen Kanal zurück, und ein falsch aufgelöster Emittent erzeugt ein
  plausibles Dossier über die falsche Firma.

Ein Zweig, der einen Titel gewinnt und dafür einen belegten Falschtreffer-Kanal öffnet,
ist kein guter Tausch.

## Scope

- **Gemeinsam mit dem Identitäts-Matcher lösen**
  (`tickets/2026-09-04-eu-identity-matcher-blocks-a-third-of-europe.md`). Sobald der
  Namensvergleich belastbar ist — also mit Gegenkorb belegt —, wird die Vereinigung
  Anker ∪ Suche sicher und billig. Vorher nicht.
- **Vorher die Klassengröße messen.** Die heutigen 2 sind eine Untergrenze: der Suchpfad
  war durch die fehlende Pagination selbst blind, und 147 Titel erreichen die Frage gar
  nicht. Ein Zähllauf nach dem Matcher-Fix beziffert die Klasse erstmals ehrlich.
- **Alternative prüfen, die ohne Namensvergleich auskommt:** OpenFIGI kennt neben
  `shareClassFIGI` auch `compositeFIGI`. Ob eine der beiden Beziehungen ein unsponsored
  ADR mit seiner Stammaktie verbindet, ist eine Messung von zwei Calls — und wäre die
  saubere Lösung, weil sie kanonisch bleibt.

## Nicht in diesem Ticket

- Der Namensvergleich selbst und die 147 nicht auflösbaren Identitäten.
- Der bisherige `search_issuer`-Rückfall in `_classify_us_line`. Der ist an eine andere
  Bedingung geknüpft (`shareClassFIGI` fehlt) und feuert nachweislich **nie** — über alle
  416 Titel null Warnungen, bei 26 sichtbaren Warnungen anderer Art im selben Log. Er ist
  tot und gehört gelöscht, nicht umgewidmet.

## Reproduktion

```
uv run python scripts\count_eu_sec_sources.py --out cache\eu_sec_source_census_v2.json
```
`ALLFG.AS` und `MONY.L` stehen im Topf `no_us_line`.
