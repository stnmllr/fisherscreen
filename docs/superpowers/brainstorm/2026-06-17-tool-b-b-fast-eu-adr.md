# Tool B Phase B-Fast — EU-ADR-Pfad: Brainstorm/Design

**Datum:** 2026-06-17
**Status:** Design-Spec, brainstorm-validiert. Terminiert in einer `writing-plans`-Session.
**Vorlauf:** B-Fast-Brainstorm `docs/superpowers/brainstorm/2026-06-17-tool-b-phase-b-fast.md` (ADR-BF-1/2/3/5/6), US-Pfad-Plan `docs/superpowers/plans/2026-06-17-tool-b-phase-b-fast.md` (PR #42), Pre-Flight-Befund `docs/superpowers/diagnostic-reports/2026-06-17-adr-resolution-preflight.md` (Verdikt **GO**).
**Erprobte Methode:** `docs/superpowers/audits/2026-06-05-dual-line-sweep/classify_dual_line.py` (OpenFIGI `/mapping` TICKER+exchCode, `norm_issuer`-Namensnormalisierung).

> **Voraussetzung:** Dieser Pfad baut auf dem US-Pfad (PR #42) auf — `ADRResolver`
> mit injiziertem `EdgarClient`, `detect_annual_form`. Branch zweigt von `main`
> **nach** dem Merge von #42 ab (sonst von `feature/b-fast-adr-resolution`).

---

## 1. Kontext: was steht, was diese Phase ergänzt

Der **Pre-Flight ist GO** (2/3 sauber: ASML→CIK 937966, SAP→CIK 1000184, korrekt, null Falsch-Matches; NVO fail-safe leer wegen Lokalsymbol-Format). Damit ist der Pfad `Yahoo-Ticker → OpenFIGI US-ADR-Linie → SEC-CIK` tragfähig. Diese Phase baut den Live-Resolver, den der US-Pfad bewusst aufgeschoben hat (die OpenFIGI-Response-Form war erst durch den Pre-Flight bekannt).

**Gesetzt aus B-Fast-Brainstorm (unverändert):** statische Tabelle als Override-Layer (ADR-BF-1), OpenFIGI als neuer DI-Service (ADR-BF-2), Failure≠Empty (ADR-BF-5), lokaler 3-Schichten-Cache (ADR-BF-6), `detect_annual_form` für den Form-Type (ADR-BF-4, schon live).

**Zwei Anforderungen, die der Pre-Flight erzwungen hat:** robuste Lokalsymbol-Normalisierung (der NVO-Miss) und ADR-Linien-Selektion (mehrere US-Zeilen/Emittent).

---

## 2. Architektur-Entscheidungen (ADRs)

### ADR-EU-1 — OpenFIGI als thin DI-Service

`app/services/openfigi_client.py` (neu): thin Wrapper, **httpx** (async/Konsistenz; das Audit nutzte `urllib`), DI-mockbar. Endpoint `https://api.openfigi.com/v3/`. **Keylos** (Pre-Flight lief keylos erfolgreich); `FISHERSCREEN_OPENFIGI_API_KEY` als optionaler Override (höheres Rate-Limit). Zwei Methoden:
- `map_ticker(local: str, exch_code: str) -> dict | None` → `/mapping` mit `idType=TICKER`, `securityType2="Common Stock"`; Home-Identität (`name`, `shareClassFIGI`) oder `None` bei „no data".
- `search_issuer(name: str) -> list[dict]` → `/search` mit `marketSecDes="Equity"`; rohe Treffer-Liste.

**Fail-loud (ADR-BF-5):** 429/5xx nach Backoff → `DataSourceError`. **Nie** ein verschlucktes Leer-Ergebnis bei einem echten Fehler (das Audit-`_figi_post` ist die Vorlage: explizites Raise nach Retries).

### ADR-EU-2 — Variantenleiter + Namens-Sanity-Check (Falschtreffer-Schutz)

Yahoo-Ticker → OpenFIGI-Lokalsymbol ist nicht 1:1 (der NVO-Miss: `"NOVO B"`+DC traf nicht). **Variantenleiter:** pro Yahoo-Ticker eine kleine **geordnete** Kandidatenmenge des lokalen Symbols gegen den/die Home-exchCode(s) probieren — abgeleitet aus dem Suffix (Audit-`SUFFIX_HOME_EXCH`):
- `split('.')[0]` (z. B. `ASML.AS` → `ASML`)
- `-` → Leerzeichen (`NOVO-B.CO` → `NOVO B`)
- `-` → entfernt (`NOVO-B.CO` → `NOVOB`)
- ggf. Klassensuffix abtrennen

**Entscheidend — der Namens-Sanity-Check (nicht „erste Antwort gewinnt"):** Eine Kandidatenform wird **nur akzeptiert**, wenn der von `/mapping` zurückgelieferte Emittentenname zur **Referenz** passt. Referenz = **yfinance `longName`** des Yahoo-Tickers (über den im Deepdive-Compose vorhandenen yfinance-Client), normalisiert mit dem **`norm_issuer`** aus dem Dual-Line-Audit (Legal-Forms + Leerzeichen droppen). „Erste **passende** Identität gewinnt." Das ist die Versicherung gegen den Variantenleiter-Falschtreffer (ROCHE → ROCHE BOBOIS lässt grüßen).

**Keine Referenz / kein Match auf allen Kandidaten → fail-loud** (`DeepDiveError`), nie eine unverifizierte Identität annehmen ([[distinguish-failure-from-empty-result]]).

### ADR-EU-3 — ADR-Linien-Selektion

Aus `search_issuer(name)`: Treffer auf US-exchCodes filtern (`US/UN/UW/UQ/UA/UV/UR/PQ` — Audit-`SUFFIX_HOME_EXCH["(US)"]`) **und** auf denselben Emittenten (`norm_issuer`-Gleichheit gegen die Home-Identität). Mehrere US-Zeilen je Emittent sind normal (ASML: 4×ADR + `ASMLF`-OTC). **Die CIK ist über alle Linien identisch** → operatives Ergebnis ist die **CIK** (`get_cik(us_ticker)`). Als `adr_ticker` (kosmetisch) die `Depositary Receipt`-Zeile bevorzugen. Mehrere **verschiedene** CIKs für denselben Emittenten = Mehrdeutigkeit → fail-loud + Override-Tabellen-Eintrag als manuelle Auflösung.

### ADR-EU-4 — eigenes Modul, Resolver delegiert

`app/deepdive/eu_adr_resolution.py` (neu): kapselt Variantenleiter, Namens-Check, Linien-Selektion, Cache-Lookup/-Persist. Der `ADRResolver` ruft es im `_EU_MARKER`-Zweig (heute `DeepDiveError`) auf, statt selbst zu wachsen. Deps injiziert: OpenFIGI-Client, EDGAR-Client (`get_cik`/`detect_annual_form`), yfinance-Client (Referenzname), Cache-Pfad. `compose.build_adr_resolver` verdrahtet sie.

### ADR-EU-5 — Drei-Schichten-Auflösung + lokaler Cache

1. **Override** `data/adr_table.json` (committed, kein TTL) — zuerst geprüft (unverändert).
2. **Dynamischer Cache** `cache/adr_resolved.json` (gitignored) — `{yahoo_ticker: {adr_ticker, cik, form_type, _cached_at}}`, TTL via `FISHERSCREEN_ADR_CACHE_TTL_DAYS` (Default **180** — ADR-Mappings driften selten). Getrennt von der Override-Datei.
3. **Live** OpenFIGI + EDGAR (ADR-EU-2/3), Erfolg → Schicht 2 persistiert.

`_cached_at`-Idiom analog `filing_cache.py`/`historical_cache.py`. CIK-Drift wird über Override (1) + TTL aufgefangen.

---

## 3. Resolution-Flow (Prosa)

```
resolve(ticker):
  [1] Override-Tabelle Treffer?                 → return.
  [2] cache/adr_resolved.json frisch?           → return.
  [3] "." im Ticker → eu_adr_resolution:
        ref = norm_issuer(yfinance.longName(ticker))      # Referenzname; fehlt → fail-loud
        for cand in variant_ladder(ticker):               # geordnete Lokalsymbol-Formen
            ident = openfigi.map_ticker(cand, home_exch)
            if ident and norm_issuer(ident.name) == ref:   # NAMENS-SANITY-CHECK
                break
        else: raise DeepDiveError("kein verifizierbares OpenFIGI-Match …")
        us = pick_us_adr_line(openfigi.search_issuer(ident.name), ref)  # ADR-EU-3
        us is None        → DeepDiveError("kein US-ADR — EU-Native-Gap, Phase 2")
        cik = edgar.get_cik(us.ticker);  not cik → DeepDiveError
        form = edgar.detect_annual_form(cik); None → DeepDiveError
        persist(ticker, adr_ticker=us.ticker, cik=cik.zfill(10), form); return
  [4] kein "." (US-Ticker) → US-Pfad (PR #42, unverändert).
  Transienter OpenFIGI/EDGAR-Fehler an jeder Stelle → DataSourceError (Failure≠Empty).
```

---

## 4. Honest-Label-Grenzen

- **Reine EU-Titel ohne US-ADR** (RMV.L, SCT.L, ABBN.SW): `pick_us_adr_line` leer → fail-loud, **EU-Native-Layer = Phase 2** (IR-PDF/Bundesanzeiger/Companies House).
- **Variantenleiter ist gegen bekannte Misses kalibriert, nicht erschöpfend:** eine neue Filer-Klasse, deren Lokalsymbol keine Kandidatenform trifft, fällt fail-loud (kein Falsch-Match dank Namens-Check) → Ticket + Leiter-Erweiterung, nicht stiller Fehlschlag.
- **P14-Candor** bleibt 🔴 (Phase 2, unverändert). **Marketaux** → Isolations-Phase. **DEF-14A/10-Q** → Phase 2.

---

## 5. Akzeptanz-Kriterien

$0 (kein Gemini), erweitert um den EU-Pfad. Tool B resolved + (für Erfolgsfälle) zieht das Filing:

1. **`NOVO-B.CO` — Variantenleiter gegen den dokumentierten NVO-Miss, mit Ground Truth (Pflicht-Gate).**
   NVO ist der Filer, dessen Lokalsymbol-Format (`"NOVO B"`+DC) im Pre-Flight fehlschlug und die Variantenleiter überhaupt nötig machte — **und** er ist über die statische Tabelle mit **bekannter Ziel-CIK `0000353278`** aufgelöst. Test: **Cache leeren + Override-Tabelle umgehen** (EU-Resolution direkt aufrufen, nicht über den override-first-`ADRResolver`) → der Live-Pfad (Variantenleiter → OpenFIGI → `NVO` → `get_cik`) muss **dieselbe CIK `0000353278`** finden. *Beweist den Fix gegen genau das Problem, das ihn nötig machte — sonst ungetestet.* **B-Fast gilt NICHT als „erledigt", bevor dieser Fall grün ist.**
2. **`SAP.DE`** (20-F-ADR-Filer, **nicht** in der Tabelle, Pre-Flight-vorbewiesen): voller Pfad → CIK `1000184`, `detect_annual_form` → `20-F`, Filing gezogen. *Beweist resolve→fetch end-to-end.*
3. **`ULVR.L`** (Unilever, frischer Filer außerhalb des Pre-Flight-Sets): Variantenleiter + Namens-Check → US-ADR `UL` → CIK → Filing. *Beweist die Mechanik auf einem nicht-vorbewiesenen Filer.*
4. **`RMV.L`** (reiner EU-Titel ohne ADR): **fail-loud** `DeepDiveError`, klare Message.
5. **Transienter OpenFIGI/EDGAR-Fehler** → `DataSourceError` (strukturell verschieden von 4) — Unit-abgedeckt.

Akzeptanz-Skript erweitert `scripts/acceptance_adr_resolution.py` (oder eigenes EU-Skript). Falls Unilever wider Erwarten kein sauberes US-ADR liefert: durch einen anderen bekannten 20-F-ADR-Titel ersetzen (Akzeptanz-Ziel muss nur die Mechanik beweisen, nicht aus dem Survivor-Pool stammen). NVO (Fall 1) ist nicht ersetzbar — er ist der Verifikationspunkt für die Variantenleiter.

---

## 6. Sequenzierung & Aufwand

Eigener Branch, eigene Merge-Einheit. Gestufte Tasks (TDD, jeweils Unit mit gemocktem OpenFIGI/EDGAR/yfinance — **kein** Netz in Unit-Tests):

| Schritt | Inhalt | Test |
|---|---|---|
| 1 | `services/openfigi_client.py` (map_ticker, search_issuer, Backoff, fail-loud) | Unit, httpx gemockt |
| 2 | `eu_adr_resolution.py`: Variantenleiter + Namens-Check (`norm_issuer`) + `pick_us_adr_line` + Cache | Unit, DI-Mocks; Falschtreffer-Schutz-Test (Kandidat liefert Fremdname → abgelehnt) |
| 3 | `ADRResolver` EU-Zweig delegiert an `eu_adr_resolution`; `compose` verdrahtet OpenFIGI+yfinance | Unit, DI-Mocks |
| 4 | $0-Akzeptanz erweitern (**NOVO-B.CO Ground-Truth-Pflicht-Gate** + SAP.DE + ULVR.L + RMV.L) | manuell, Netz (Stephan) |

**Pflicht-Verifikationspunkt:** Die Variantenleiter (ADR-EU-2) ist eine Hypothese gegen den dokumentierten NVO-Miss, kein bewiesener Fix. Akzeptanzfall 1 (NOVO-B.CO gegen Ground-Truth-CIK `0000353278`) muss grün sein, bevor B-Fast als erledigt gilt — der Fix wird gegen genau das Problem getestet, das ihn nötig machte.

**Aufwand: ~2–3 Sessions.** `norm_issuer` + `SUFFIX_HOME_EXCH` werden aus dem Audit-Skript in Produktionscode gehoben (mit Tests), nicht neu erfunden.

---

## 7. Offene Fragen (mit Empfehlung)

1. **`norm_issuer`-Strenge.** Audit-Version droppt Legal-Forms (AG/SE/NV/PLC…) + Leerzeichen. **Empfehlung:** unverändert übernehmen — sie hielt „ROCHE HOLDING" == „ROCHE HOLDING AG" zusammen und „ROCHE BOBOIS" getrennt (genau der Falschtreffer-Schutz). Bei einem echten Mismatch-Fall später nachschärfen.
2. **yfinance-`longName` fehlt** (seltene Attrition). **Empfehlung:** kein Referenzname → fail-loud (`DeepDiveError`), nie unverifiziert akzeptieren. Konsistent mit ADR-EU-2.
3. **Akzeptanz-Skript: erweitern vs. eigenes.** **Empfehlung:** das bestehende `scripts/acceptance_adr_resolution.py` um die EU-Fälle erweitern (ein Ort für die B-Fast-Akzeptanz).

---

*Ende. Nächster Schritt: Review-Gate durch Stephan, dann `writing-plans`.*
