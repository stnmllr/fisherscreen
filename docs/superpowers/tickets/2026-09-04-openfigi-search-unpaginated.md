# Ticket: `search_issuer` liest nur die erste Seite — RELX, Standard Chartered und Enel gelten dadurch als „ohne US-Notierung"

**Opened:** 2026-09-04
**Priority:** hoch. Erzeugt **falsche Verdikte**, nicht nur unvollständige Anzeige — und trifft mit `not_sec_registrant` den größten Topf des EU-Zähllaufs. Zusammen mit `tickets/2026-09-04-eu-identity-matcher-blocks-a-third-of-europe.md` macht es den Zähllauf als Entscheidungsgrundlage unbrauchbar.
**Status:** FIXED 2026-09-04 (PR #50) — siehe „Resolution" unten.

## Resolution

Die Suche wurde **nicht paginiert, sondern ersetzt**. Der Scope oben verlangte, die
Alternative ernsthaft zu prüfen, bevor paginiert wird — sie trug: die US-Linien eines
Emittenten hängen an der Aktiengattung seiner Heimatlinie, und `shareClassFIGI` ist ein
kanonischer Identifikator. `OpenFIGIClientImpl.lines_by_share_class` holt sie mit **einem**
`/v3/mapping`-Call, vollständig, ohne `next`-Cursor und ohne Seitendeckel (`1d40a5c`).

Das löst zwei Probleme statt eines. Die Pagination hätte nur die Vollständigkeit der
Trefferliste repariert; der Anker macht zusätzlich den **Namensvergleich auf dem
US-Pfad überflüssig** — `pick_us_adr_line` bekommt Zeilen, die per Konstruktion demselben
Emittenten gehören, und `_same_issuer` konnte ersatzlos entfallen. Damit ist auch
`tickets/2026-09-03-same-issuer-abbreviation-gap.md` gegenstandslos geworden.

Der Rückfall auf `search_issuer` wurde **gelöscht statt als zweites Netz behalten**
(`8ee31b5`): der Zensus zeigte ihn als tot, und ein stiller Rückfall auf den defekten Pfad
hätte genau die Verdikte zurückgebracht, die dieses Ticket beschreibt. Heimatlinien ohne
`shareClassFIGI` scheitern jetzt laut (`no_share_class_anchor`) — ein eigener Zensus-Topf,
kein Verdikt über den Emittenten.

**Belegt am Zensus v3 (2026-09-04), an den vier im Ticket genannten Fällen:** alle vier
haben den Topf `no_us_line` verlassen. `REL.L` ist heute `resolved_20f` (RLXXF, CIK
0000929869) — der Kopffall des Tickets bekommt ein volles Dossier. `STAN.L`, `ENEL.MI` und
`BNP.PA` sind `not_sec_registrant` mit benannter OTC-Linie (SCBFF, ESOCF, BNPQF): auch das
ist eine Korrektur, denn „keine US-Notierung" war falsch, „US-Linie vorhanden, aber
unsponsored und ohne CIK" ist der zutreffende Befund. Der Topf `no_us_line` schrumpfte
insgesamt von 15 auf 7.

Offen geblieben und ausgelagert: unsponsored ADRs, die in einer **eigenen** Aktiengattung
liegen und deshalb am Anker vorbeilaufen —
`tickets/2026-09-04-unsponsored-adr-own-share-class.md` (`ALLFG.AS`, `MONY.L`).

## Befund

`OpenFIGIClientImpl.search_issuer` (`app/services/openfigi_client.py`) setzt genau einen
POST auf `/v3/search` ab und gibt `res["data"]` zurück. Die API paginiert per
`next`-Cursor; der Client wertet ihn nicht aus.

Gemessen:

```
search_issuer('RELX PLC')               -> 100 Zeilen, davon US: 0   next-Cursor: ja
search_issuer('STANDARD CHARTERED PLC') -> 100 Zeilen, davon US: 0   next-Cursor: ja
search_issuer('ENEL SPA')               -> 100 Zeilen, davon US: 0   next-Cursor: ja
```

Exakt 100 Zeilen ist die Seitengröße. Große europäische Emittenten notieren an dutzenden
Handelsplätzen, ihre US-Linien liegen also regelmäßig jenseits der ersten Seite.

**RELX ist ein 20-F-Filer mit NYSE-Notierung.** Der Zähllauf hat ihn als `no_us_line`
gebucht — „reines EU-Listing, keine US-Notierung". Das ist schlicht falsch.

## Warum das schwerer wiegt als der Docstring annimmt

`pick_us_adr_line` (`app/deepdive/eu_adr_resolution.py:135-149`) kennt das Problem bereits
und stuft es als unkritisch ein:

> *„the live acceptance (2026-06-17) showed OpenFIGI's single /search page does not always
> contain the canonical NYSE ADR (NVO, UL), so adr_ticker can fall back to the issuer's OTC
> foreign-ordinary 'F' line … Same CIK, same 20-F — only the displayed symbol differs.
> Getting the canonical ADR reliably needs a paginated/better search and yields no CIK
> gain (deferred, YAGNI)."*

Diese Begründung trägt nur, **solange überhaupt eine US-Linie auf Seite 1 liegt**. Dann
ist der CIK identisch und nur das angezeigte Symbol schlechter. Der Zähllauf zeigt zwei
Fälle, in denen sie nicht trägt:

1. **Keine einzige US-Linie auf Seite 1** → Verdikt `no_us_line`, also „reines
   EU-Listing". Falsch für RELX, Standard Chartered, Enel, BNP.
2. **Nur eine graue OTC-Linie auf Seite 1**, während das gesponserte ADR mit CIK auf
   Seite 2 liegt → `edgar.get_cik` schlägt fehl → Verdikt `not_sec_registrant`. Der
   Emittent ist registriert, das Dossier behauptet das Gegenteil.

Fall 2 trifft potenziell den größten Topf des Zähllaufs: **177 Titel (42,5 %)**. Wie viele
davon echt sind, ist derzeit unbekannt.

Der YAGNI-Vermerk war also richtig gedacht und falsch begrenzt: die Pagination ändert
nicht nur das Anzeigesymbol, sie ändert das **Verdikt**.

## Scope

- `search_issuer` paginiert, mit hartem Deckel (Seitenzahl **und** Gesamtzeilen), damit ein
  Emittent mit tausenden Linien den Lauf nicht sprengt. Keyless-Rate-Limits sind der
  begrenzende Faktor — der Zähllauf braucht heute schon ~16 s pro Titel.
- **Früher Abbruch:** sobald eine US-Linie mit CIK gefunden ist, ist Weiterblättern
  zwecklos. Das hält die Zusatzkosten für den Normalfall bei null.
- Die Alternative ernsthaft prüfen, bevor paginiert wird: `/v3/mapping` mit
  `idType=ID_ISIN` oder der `shareClassFIGI` aus der Heimatlinie liefert die
  Geschwisterlinien eines Papiers direkt und ohne Volltextsuche. Das ist vermutlich der
  bessere Weg und deckt sich mit
  `tickets/2026-06-03-isin-canonical-anchor-openfigi.md`.
- Den Docstring von `pick_us_adr_line` korrigieren — er dokumentiert derzeit eine
  Begründung, die widerlegt ist.
- **Danach den Zähllauf wiederholen.** Erst mit paginierter Suche *und* repariertem
  Identitäts-Matcher ist seine Zahl belastbar.

## Nicht in diesem Ticket

- Der Identitäts-Matcher — eigenes Ticket, andere Ursache, gleiche Konsequenz für die
  Messung.
- Die EU-Native-Quellenschicht. Beide Tickets zusammen entscheiden erst, ob sie gebraucht
  wird.

## Reproduktion

```
uv run python scripts\count_eu_sec_sources.py --analyse-no-us-line
```
zeigt `REL.L`, `STAN.L`, `ENEL.MI`, `BNP.PA` mit `US-Linien=0`.
