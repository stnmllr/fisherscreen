# Tool B (Deep Dive) — Phase B-Fast: Brainstorm

**Datum:** 2026-06-17
**Status:** Struktur-Brainstorm, Single-Point. Terminiert in **einer** kurzen
`writing-plans`-Session (Begründung §6). Kein Code, kein Plan, kein Commit in dieser Session.
**Vorlauf:** Master-Brainstorm `docs/superpowers/brainstorm/2026-05-18-tool-b-master.md`,
B.1-Spec `docs/superpowers/specs/2026-05-18-tool-b-phase-b1-design.md`,
Pareto-Plan `docs/superpowers/plans/2026-05-27-phase-1-pareto-b2.md`.
**Referenz-Spec:** `D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\FisherScreen_Architektur_v3.md`

> Tool B läuft heute end-to-end **nur für die 5 statischen ADR-Tabelleneinträge**
> (NOVO-B.CO, GOOGL, ASML, KO, MSFT). Jeder andere Ticker — auch beliebige
> US-Titel — bricht ab, weil die CIK nicht aufgelöst wird. B-Fast hebt genau
> diese eine Blockade und macht Tool B für die erreichbare Teilmenge der ~25
> Tool-A-Survivor lauffähig. Mehr nicht.

---

## 1. Kontext: was wir haben, was fehlt, Re-Bündelung

### 1.1 Re-Bündelung gegen Master-B.2/B.3/B.4

„B-Fast" ist ein neuer, bewusst minimaler Schnitt. Der Name vermeidet die
Dreifach-Belegung von „B.2" (Master-Brainstorm B.2 = dyn. ADR + EU-Voll + 10-Q +
Insider; Pareto-Plan „Phase 1 — Pareto-B.2" mit Sub-Phasen 1.1–1.6). B-Fast zieht
aus dem alten Scope **genau einen** Hebel vor:

| Quelle | Inhalt | In B-Fast? |
|---|---|---|
| Master-B.2, Punkt 1 | **Dynamische ADR-Resolution + US-CIK-Fix** | ✅ **der einzige Inhalt** |
| Master-B.2, Rest | EU-Voll (IR-PDF), 10-Q, Insider-EU | → Phase 2 (EU-Native-Layer) |
| Master-B.3 | Marketaux + Soft Scuttlebutt | → Isolations-Phase (Trust-Boundary, Master §2.8) |
| Master-B.4 | CEO-Tonalität (P14) | → **gestrichen aus B-Fast**, Phase 2 (§1.3) |
| Pareto 1.5 | DEF-14A-Proxy | → Phase 2 (US-domestic-only; Form-4 deckt P15-Alignment) |

Akzeptanz-Gate 1.6 (drei reale Deep-Dives, Stephan-Urteil) folgt **direkt nach
B-Fast** — dafür muss Tool B überhaupt erst auf reale Survivor-Ticker laufen.

### 1.2 Der blockierende Defekt (verifiziert am Code)

- `app/deepdive/adr_resolver.py:43-50`: Tabelle → Treffer; sonst, wenn der Ticker
  ein `.` trägt, `DeepDiveError`; sonst US-Passthrough mit **`cik=""`**.
- `app/deepdive/pipeline.py:71-76`: leerer CIK → `DeepDiveError`
  („US-passthrough CIK resolution is Phase B.2"). **Auch beliebige US-Ticker
  scheitern also heute.** Die CIK-Resolution ist der harte Block.
- `app/services/edgar_client.py:129` `get_cik(ticker)` löst US-Ticker → CIK über
  `company_tickers.json` (US-only) — der US-Fix ist vorhandene, nur nicht
  verdrahtete Infrastruktur.

### 1.3 Warum CEO-Tonalität (P14) gestrichen ist — Pre-Flight-Befund

Pre-Flight 2026-06-17 (Stephan, Websuche): Hit-Rate des CEO-/Shareholder-Letters
über den EDGAR-Pull = **0/6**.

- **US-Filer (AVGO, LLY, AAPL):** kein Letter im 10-K. Das Genre ist bei modernen
  US-Large-Caps weitgehend ausgestorben; Management-Kommunikation läuft über
  Earnings Calls + Pressemitteilungen. Wo ein Letter existiert (LLY), liegt er als
  ESG-Doc auf der Website, **nicht** SEC-gefiled. *(Diese Spalte ist die
  belastbare Evidenz: diese Filer sind über EDGAR erreichbar.)*
- **EU/UK-Filer (ABB, Rightmove, Softcat):** Letter existiert und ist inhaltlich
  hochwertig — liegt aber im Glossy-/Integrated-Report-PDF auf der IR-Website,
  nicht im SEC-Primärdoc. *(Diese drei sind ohnehin reine Nicht-SEC-Filer = der
  EU-Native-Gap, schon als Phase 2 markiert — sie testen die erreichbare Menge
  streng genommen nicht.)*
- **Ungetestet, aber strukturell gleich:** EU-**20-F-ADR**-Filer (NVO/ASML/SAP),
  die B-Fast erreicht. Deren Chairman-Statement liegt im Glossy-Annual-Report /
  Exhibit, nicht im 20-F-Primärdoc (Items 4/5/18). Option A (nur Primärdoc) = ~0
  auch hier; nur ein Exhibit-Pull (EX-13/EX-99) könnte bergen — genau die
  Scope-Klasse, die mit DEF-14A gerade geschnitten wurde.

`app/services/edgar_client.py:350-377` (`get_latest_annual_filing`) zieht ohnehin
**nur das `primaryDocument`**, keine Exhibits — der Letter ist also für die
erreichbare Menge nicht da.

**Schluss:** Der Letter ist ein **EU-PDF-Problem, kein EDGAR-Problem**. P14
(Offenheit) bleibt ehrlich **🔴** (Honest-Label, Methodik-Grenze, kein
Tool-Defekt; `synthesis.py:367-368` hält den 🔴-Hardcode). CEO-Tonalität wandert
als Phase-2-Backlog-Marker, gebündelt mit dem **EU-Native-Source-Layer**
(IR-PDF/Bundesanzeiger/Companies House) — dort liegt sowohl die Quelle als auch
die nötige PDF-Fetch-Fähigkeit. **Backlog-Notiz:** US-Candor (Letter tot → ggf.
bezahlte Earnings-Calls) und EU-Candor (IR-PDF-Letter) brauchen
*unterschiedliche* Lösungen — nicht als eine denken.

---

## 2. Architektur-Entscheidungen (ADRs)

Vorschläge dieses Brainstorms; Review-Gate durch Stephan vor der Plan-Session.

### ADR-BF-1 — Statische Tabelle bleibt Override-Layer, drei Schichten

Die statische `data/adr_table.json` wird **nicht ersetzt**, sondern zum
autoritativen manuellen Override. Auflösung in drei Schichten:

1. **Override (committed, kein TTL):** `data/adr_table.json` — manuelle Autorität
   für Sonderfälle und bekannte CIK-Drift-Korrekturen. Zuerst geprüft.
2. **Dynamischer Cache (gitignored, TTL):** `cache/adr_resolved.json` — erfolgreich
   live aufgelöste Einträge, ADR-4-analog mit `_cached_at`-Feld (Muster aus
   `filing_cache.py` / `historical_cache.py`). Getrennt von der Override-Datei,
   damit der Cache die versionierte Tabelle nie verschmutzt.
3. **Live:** OpenFIGI + EDGAR (§ADR-BF-2/3/4), Ergebnis wird in Schicht 2 persistiert.

`load_adr_table` (`adr_table.py`) bleibt unverändert als Quelle für Schicht 1.

### ADR-BF-2 — OpenFIGI als neuer DI-Service, `/v3/mapping` TICKER+exchCode

OpenFIGI existiert heute **nur** als Audit-Skript
(`docs/superpowers/audits/2026-06-05-dual-line-sweep/classify_dual_line.py`) +
Ticket (`docs/superpowers/tickets/2026-06-03-isin-canonical-anchor-openfigi.md`).
B-Fast promotet die erprobte Methode zu Produktionscode:
`app/services/openfigi_client.py`, thin Wrapper, DI-mockbar (Service-Layer-Konvention,
CLAUDE.md), **httpx** statt `urllib` (async/Konsistenz). Endpoint
`https://api.openfigi.com/v3/`.

- **Primär: `/mapping` per `idType=TICKER` + `exchCode` (Home-Börse).** Liefert
  saubere Emittenten-Identität (`name`, `shareClassFIGI`). Bewiesen korrekt auf
  `RO.SW → "ROCHE HOLDING AG-BR"`.
- **`/search` nur als Härtung, nie als primärer Treiber** — zu verrauscht
  (`"ROCHE"` matchte „ROCHE BOBOIS"). yfinance `.isin` ist ebenfalls unzuverlässig
  (lieferte Fremd-ISIN für RO.SW) → **nicht** als Identitätspfad nutzen.
- 429/5xx-Backoff + **explizites Fehler-Raise** (kein stilles Leer-Ergebnis, siehe
  ADR-BF-5). Eigene Env-Var `FISHERSCREEN_OPENFIGI_API_KEY` (optional; OpenFIGI
  läuft auch keylos mit niedrigerem Rate-Limit — Pre-Flight klärt, ob nötig).

### ADR-BF-3 — ADR-Ziel ≠ Home-Exchange-Sibling → eigene Selektion + Pre-Flight-Gate

**Wichtige Ehrlichkeit:** Die erprobte Roche-Methode disambiguierte
*Home-Exchange-Aktienklassen* (Bearer/Registered/Participation), um eine liquide
Linie im Universum zu finden. B-Fast braucht etwas anderes: die **US-ADR-Linie +
ihre SEC-CIK**. Das ist ein anderes Ziel-Listing (US-Börse, securityType ADR),
und der Pfad OpenFIGI → ADR-Ticker → CIK ist **neu, nicht erprobt**.

- Flow: Home-Identität (`shareClassFIGI`) → US-gelistete Linie desselben Emittenten
  (US-exchCodes wie `US/UN/UW/UQ…`, ADR-Security-Type) → US-Symbol →
  `edgar_client.get_cik(us_symbol)` → CIK.
- **Gate (Kern-Risiko-Gate des gesamten B-Fast, nicht Vorab-Task unter ferner
  liefen):** Der gesamte EU-ADR-Pfad hängt an diesem unbewiesenen Schritt. Bevor
  *irgendein* EU-Pfad-Code geschrieben wird, läuft ein echtes **Go/No-Go-Gate mit
  dokumentiertem Befund** — derselbe Disziplin-Standard wie der CEO-Letter-Pre-Flight,
  der B-Fast gerade um ein ganzes Feature verkleinert hat (erst Evidenz, dann Code):
  - Pre-Flight gegen **NVO, ASML, SAP** (alle 20-F-ADR-Filer), optional ein vierter
    ADR-Filer-Typ.
  - Dokumentierter Befund je Filer: liefert OpenFIGI eine **eindeutige** US-ADR-Linie?
    Löst `get_cik` auf dem ADR-Symbol die CIK auf? Gibt es Mehrdeutigkeiten (mehrere
    US-Linien)?
  - **Explizite Fork:** Scheitert der Pre-Flight für die 20-F-ADR-**Klasse** oder ist
    er unzuverlässig, **schrumpft B-Fast auf den US-Pfad allein** (`get_cik`-
    Verdrahtung — der einfache, sichere Teil), und der **EU-ADR-Pfad wird selbst
    Phase-2-Material**. Der Plan benennt diese Möglichkeit explizit, statt zu
    unterstellen, der EU-Pfad funktioniere. Einzelne fail-loud-Filer (ADR-BF-5) sind
    davon unbenommen — das Gate entscheidet über die *Klasse*, nicht den Einzelfall.

### ADR-BF-4 — Form-Type aus EDGAR-Submissions detektieren, nicht raten

Statt `form_type` zu raten (heute hart in der Tabelle): aus
`submissions/CIK….json` ableiten, welche Jahresform der Filer tatsächlich nutzt
(20-F für FPI, 10-K für US-Domestic). `get_latest_annual_filing` iteriert bereits
`recent.form`; eine `detect_annual_form(cik)`-Erweiterung prüft Vorhandensein von
`20-F` vs `10-K`. Kein Annual-Form vorhanden → fail-loud.

### ADR-BF-5 — Failure ≠ Empty: API-Fehler ↔ echtes Kein-ADR strukturell trennen

Lehre [[distinguish-failure-from-empty-result]]: ein verschluckter
externer-Call-Fehler, der wie ein leeres Ergebnis aussieht, maskiert still.

- **Transienter OpenFIGI-/EDGAR-Fehler** (429/5xx/Netz) → `DataSourceError`
  (Exit-Code 2), niemals als „kein ADR" interpretiert.
- **Echtes Kein-ADR** (Emittent hat kein US-Listing) → `DeepDiveError` (Exit-Code 1)
  mit handlungsleitender Message: *„<ticker> hat kein US-ADR/US-Listing — reiner
  EU-Titel, EU-Native-Source-Layer ist Phase 2."* In der Pipeline über
  `resolver.resolve()` (pipeline.py:70) surfaced, wie heute.

### ADR-BF-6 — Dynamischer Cache lokal (ADR-4-analog), nicht Firestore

Tool B ist CLI-lokal (ADR-2); ADR-4 hat Lokal-FS-Cache als Konvention gesetzt
(`filing_cache`, `historical_cache`). Der ADR-Cache folgt dem: `cache/adr_resolved.json`,
`_cached_at`-TTL **lang** (Vorschlag 180 Tage — ADR-Mappings driften selten), via
`FISHERSCREEN_ADR_CACHE_TTL_DAYS`. CIK-Drift wird über die Override-Tabelle
(Schicht 1) und den TTL aufgefangen. Firestore (`dev_adr_resolution`) wäre
Tool-A-konsistent, fügt dem heute reinen Resolver aber eine Firestore-Abhängigkeit
zu — für einen Single-User-CLI-Workflow ohne Mehrwert. **Empfehlung: lokal.**

### ADR-BF-7 — Einzel-Ticker-CLI bleibt; kein Batch-Reader in B-Fast

Wie kommen die ~25 Survivor in Tool B? B-Fast löst die CIK-Resolution *pro Ticker*,
adressiert aber nicht den Tool-A→Tool-B-Übergang (Master §7 Pkt 3, bisher offen).
**Entscheidung:** B-Fast behält den heutigen Einzel-Ticker-Pfad
(`uv run python -m app.deepdive deepdive <TICKER>`). Akzeptanz-Gate 1.6 macht ohnehin
nur **drei** manuelle Deep-Dives — ein Batch-/Listen-Reader (z. B. die aktuelle
Crosshits-Liste einlesen) ist **Phase-2-Komfort**, kein B-Fast-Scope (und V3-Prinzip 7
„Pull, nie Batch" mahnt hier ohnehin zur Vorsicht). Bewusst entschieden, nicht
implizit offen.

---

## 3. Resolver-Flow (Prosa)

```
resolve(ticker):
  [1] Override:  ticker in data/adr_table.json?  → nutze Eintrag.            (Schicht 1)
  [2] Cache:     ticker in cache/adr_resolved.json und frisch?  → nutze.     (Schicht 2)
  [3] US-Pfad (kein "." im Ticker):
        cik = edgar.get_cik(ticker)                 # company_tickers.json
        cik gefunden → form = detect_annual_form(cik); persistiere; return
        nicht gefunden → DeepDiveError (US-Ticker nicht im SEC-Ticker-Map)
  [4] EU-Pfad ("." im Ticker):
        a. ident = openfigi.map(TICKER=local, exchCode=home)   # /v3/mapping
        b. us_line = openfigi US-ADR-Linie desselben Emittenten (ADR-BF-3)
        c. cik = edgar.get_cik(us_line.ticker)
        d. form = detect_annual_form(cik)
        irgendeine Stufe leer  → DeepDiveError (kein US-ADR → EU-Native-Gap, Phase 2)
        transienter API-Fehler → DataSourceError  (ADR-BF-5)
        Erfolg → persistiere in cache/adr_resolved.json; return
```

**Wo sitzt die neue Logik (Erweiterung, nicht Ersatz):**
- `app/services/openfigi_client.py` — **neu** (thin Wrapper, DI).
- `app/deepdive/adr_resolver.py` — **erweitert**: bekommt `openfigi`, `edgar`
  (für `get_cik` + `detect_annual_form`) und den dynamischen Cache injiziert;
  der heutige `cik=""`-Passthrough (Zeile 50) und der Pipeline-Guard
  (pipeline.py:71-76) entfallen, weil der CIK jetzt real aufgelöst wird.
- `app/deepdive/compose.py` — `build_adr_resolver()` verdrahtet die neuen Deps.
- `app/deepdive/adr_table.py` / `data/adr_table.json` — unverändert (Override-Quelle).

---

## 4. Honest-Label-Grenzen von B-Fast (explizit)

- **Reine EU-Titel ohne US-ADR** (z. B. RMV.L, SCT.L, ABBN.SW): kein EDGAR-Filing,
  kein Transcript → fail-loud, **EU-Native-Source-Layer = Phase 2**. „B-Fast
  lauffähig" heißt: lauffähig für die Teilmenge der Survivor **mit US-ADR oder
  US-Listing**.
- **P14 (Offenheit) bleibt 🔴** — CEO-Tonalität deferred (§1.3), Phase 2.
- **OpenFIGI-ADR-Pfad ist neu** (Roche-Methode war home-exchange) → Pre-Flight als
  Go/No-Go-Gate (ADR-BF-3). Bei No-Go schrumpft B-Fast bewusst auf den US-Pfad allein,
  EU-ADR wird Phase 2; einzelne unsichere Filer fallen ohnehin fail-loud statt
  Falsch-Match.
- **Kein 10-Q, keine Exhibits, kein DEF-14A** — unverändert Phase-2-Backlog.

---

## 5. Akzeptanz-Kriterien B-Fast (Vorbedingung für 1.6)

Tool B läuft end-to-end (Dossier wird erzeugt) für:

1. **US-Ticker NICHT in der statischen Tabelle** (z. B. AVGO): CIK dynamisch
   aufgelöst, 10-K gezogen, Dossier generiert.
2. **EU-ADR-Ticker dynamisch aufgelöst** (ein 20-F-ADR-Filer außerhalb der
   5-Einträge-Tabelle): OpenFIGI → ADR → CIK → 20-F, Dossier generiert.
   *Konditional:* nur bei Pre-Flight-**Go** (ADR-BF-3). Bei **No-Go** entfällt dieser
   Fall — B-Fast = US-Pfad allein, EU-ADR-Pfad ist dann Phase 2.
3. **Reiner EU-Titel ohne ADR** (z. B. RMV.L): **fail-loud** `DeepDiveError` mit
   klarer Message, Exit 1 — **kein** stiller Falsch-CIK.
4. **Transienter OpenFIGI/EDGAR-Fehler** → `DataSourceError`, Exit 2 (strukturell
   verschieden von Fall 3).

Akzeptanz ist **$0** (keine Gemini-Synthesis nötig, um Resolution + Filing-Pull zu
prüfen — `--no-cache` + Abbruch vor Stage 5, oder ein Resolver-Smoke-Skript unter
`scripts/`). Volllauf mit Gemini erst im Rahmen von 1.6.

---

## 6. Sequenzierung, Aufwand, Brainstorm-vs-Plan

**Ist B-Fast als Single-Point noch ein Brainstorm?** Knapp ja — es gibt echte
Weichen (ADR-Ziel ≠ Home-Sibling, Drei-Schichten-Cache, Failure-≠-Empty,
Form-Detektion), die vor TDD fixiert sein müssen. Aber **eine** kurze
Brainstorm-Runde (dieser Doc) reicht; danach **eine** Plan-Session. Kein
Mehr-Sessions-Brainstorm.

**Interne Reihenfolge — Schritt 0 ist ein gatedes Go/No-Go, kein Vorab-Task:**

| Schritt | Inhalt | Gate / Test |
|---|---|---|
| **0** | **ADR-Pre-Flight = Kern-Risiko-Gate (ADR-BF-3):** OpenFIGI → US-ADR-Linie → CIK gegen NVO/ASML/SAP beweisen, Befund dokumentieren | **Go/No-Go** vor jedem EU-Pfad-Code; Skript unter `scripts/`, manuell |
| 2a | `adr_resolver.py` **US-Pfad** (sicherer Kern, **gate-unabhängig**): `get_cik`-Verdrahtung + `detect_annual_form` + Guard-Entfernung (pipeline.py:71-76) | Unit, DI-Mocks |
| 1 | `services/openfigi_client.py` (thin Wrapper, httpx, Backoff, fail-loud) | Unit, OpenFIGI gemockt — **nur bei Go** |
| 2b | `adr_resolver.py` **EU-Pfad**: 3-Schichten-Cache + OpenFIGI-Auflösung + Failure-≠-Empty | Unit, DI-Mocks — **nur bei Go** |
| 3 | `compose.py`-Verdrahtung + Akzeptanz-Smoke | E2E gemockt + $0-Smoke |

**Zwei mögliche Endgestalten (Fork aus Schritt 0):** **(A) Go** → US- + EU-ADR-Pfad
(voller B-Fast). **(B) No-Go** → nur US-Pfad (2a/3), EU-ADR-Pfad wird Phase-2-Material.
Schritt 2a ist in beiden Fällen der sichere Kern und kann unabhängig vom Gate laufen.

**Geschätzter Aufwand: ~2–3 Sessions** bei Go (1 Pre-Flight-Gate + 1–2 TDD), plus der
$0-Akzeptanz-Smoke; bei No-Go (US-Pfad allein) eher **1–2 Sessions**. Kleiner als
jede Pareto-Sub-Phase mit bezahltem Lauf.

---

## 7. Offene Fragen (mit Empfehlung, vor/in der Plan-Session zu schließen)

1. **OpenFIGI-Key nötig?** Keylos hat striktes Rate-Limit. Bei ~25 Tickern selten
   → **Empfehlung: keylos starten**, Env-Var `FISHERSCREEN_OPENFIGI_API_KEY` als
   optionaler Override vorsehen. Pre-Flight bestätigt.
2. **ADR-Cache-TTL.** ADR-Mappings driften selten → **Empfehlung: 180 Tage**,
   Override-Tabelle fängt bekannte Drift. Bei beobachteter Drift später kürzen.
3. **Mehrere US-ADR-Linien pro Emittent** (selten). **Empfehlung:** die Linie mit
   auflösender SEC-CIK bevorzugen; bei Mehrdeutigkeit fail-loud + Override-Tabellen-
   Eintrag als manuelle Auflösung (statt raten).
4. **`detect_annual_form`: Filer mit weder 10-K noch 20-F** (z. B. nur 40-F-Kanadier
   im Survivor-Pool?). **Empfehlung:** fail-loud mit Form-Liste in der Message;
   40-F/andere Formen sind Phase-2-Scope, nicht still annehmen.

---

*Ende des Brainstorms. Nächster Schritt: Review-Gate durch Stephan, dann eine
`writing-plans`-Session. Kein Code/Commit in dieser Session.*
