# Resolution-Daten-Qualitäts-Klassifikation (Ticket Punkt 0b) — Design

> Status: Spec, vor Implementierung. Branch `feature/gate-universe-fixes`.
> Datum: 2026-06-07. Folge zu 0a; generalisiert den Masking-Bug, den 0a aufdeckte.

## Ziel

Symbole, die mit fehlenden/unbrauchbaren Kerndaten auflösen, leaken an die Basis-Gates und
werden vom None-Guard still auf **BENIGN** gemappt — eine reale, screenbare Firma (oder Müll)
verschwindet unsichtbar. 0b klassifiziert diese **in der Resolution, vor jedem Gate**, als
Daten-Qualitäts-REVIEW. Eine kohärente Regel statt drei Gate-Guards.

## Befund (Evidenz aus dem 0a-GATE-2-Cold-Run)

Drei maskierte Pfade, zwei verschiedene Gates, inkonsistente None-vs-0-Behandlung:
- `RNL.PA` (Renault-Nachranganleihe), `GLB.IR` (CBO-SPV): `market_cap`=None → leaken bis
  **GATE_VOLUME**, BENIGN.
- `ML.PA` (Michelin, reale Firma): yfinance `marketCap=0` (Volumen vorhanden) → stirbt schon an
  **GATE_MARKET_CAP**, BENIGN. **Rutscht durch einen „mc UND vol fehlen"-AND-Test.**
- **Dritte Lücke (b):** `market_cap` da, aber `currency` fehlt → `_resolve` gibt None → leakt ans
  market_cap-Gate → BENIGN. Uninterpretierbare Symbolantwort (Zahl ohne Währung = wertlos).
- **FX (c), systemisch:** `market_cap` + `currency` da, nur die FX-Rate fehlt → reale Firma stirbt
  still BENIGN. Blast-Radius: ein FX-Ausfall maskiert **alle** Nicht-EUR-Symbole eines Laufs auf
  einmal; die Reconciliation hält dabei (zählt sie als Drops) — wie die 110 Kontaminanten fängt
  nur ein **expliziter reason_code** das, nicht der Erhaltungssatz.

## Code-Befund, der die Lösung vereinfacht

`ScreenerRecord.from_yfinance_info` (`screener_record.py:63-64`) macht
`market_cap=info.get("marketCap") or None` und `avg_daily_volume=info.get("averageVolume") or None`
→ **`0` kollabiert schon bei der Konstruktion zu `None`** (beide Felder). Damit ist „None-oder-0"
am Record schlicht `is None` — kein Sonder-`==0`-Test. ML.PA (`marketCap=0`) liegt als
`market_cap=None` vor und wird von der `NO_RAW_MC`-Branch automatisch erfasst.

## Lösung: Grund-Branch statt Symptom-Patch

`_resolve_market_cap_eur` (`runner.py:56-73`) **weiß bereits**, warum es None liefert, wirft die
Info aber weg. Es gibt den Grund zurück:

```
_resolve_market_cap_eur(...) -> tuple[float | None, str]
  reason ∈ {"OK", "NO_RAW_MC", "NO_CURRENCY", "NO_FX"}
```

Prüf-Reihenfolge **deterministisch** (Guardrail 4): `market_cap is None` zuerst → `NO_RAW_MC`;
dann `currency is None` → `NO_CURRENCY`; dann FX-Rate None → `NO_FX`; sonst `OK`. (Bei mc∧currency
beide fehlend gewinnt mc-zuerst → stabiler geloggter Code; Routing identisch.)

**Divert in `run_basis_filter`** (nach Zeile 92, vor `records.append`):
```
record.market_cap_eur, reason = _resolve_market_cap_eur(...)
if record.avg_daily_volume is None or reason in ("NO_RAW_MC", "NO_CURRENCY"):
    -> no_symbol_data  (RESOLUTION_NO_SYMBOL_DATA, REVIEW)   # deckt RNL/GLB, ML, currency
elif reason == "NO_FX":
    -> fx_unavailable  (RESOLUTION_FX_UNAVAILABLE, REVIEW)    # real, infra, eigener Trigger
else:  # OK
    records.append(record)                                    # gateable, wie bisher
```
Symbol-Daten-Bedingungen werden **zuerst** geprüft (vol None ∨ NO_RAW_MC ∨ NO_CURRENCY), dann
NO_FX — ein Record mit vol None **und** NO_FX zählt als NO_SYMBOL_DATA (Symbolqualität gewinnt).

**Warum FX einen eigenen Code verdient:** FX ist die **einzige** Klasse, in der „divertiert =
Nicht-Survivor" *temporär* korrekt ist, kein Dauerurteil. RNL/GLB sind keine Firmen (permanent
draußen). Ein FX-Opfer ist eine reale Firma hinter einem Infra-Bug. Ein Nicht-Null
`RESOLUTION_FX_UNAVAILABLE` ist der Trigger, **FX zu fixen**, nicht das Symbol zu beurteilen. 0b
macht „still verlorene reale Firma" → „sichtbar geflaggt, bis FX gefixt".

## Struktur-Änderungen

- `BasisFilterResult` + zwei Felder: `no_symbol_data: list[ScreenerRecord]`,
  `fx_unavailable: list[ScreenerRecord]`. `resolved` = nur noch die **gateable** (usable) Records
  (Divertierte nicht mehr enthalten); Docstring entsprechend anpassen.
- `ReasonCode` (funnel.py) + `RESOLUTION_NO_SYMBOL_DATA`, `RESOLUTION_FX_UNAVAILABLE`; beide in
  `_ALWAYS_REVIEW` (Severity immer REVIEW).
- `build_funnel`: beide als **Resolution-Stufen**-Dropouts; `resolution.dropped` = unresolved +
  degraded + no_symbol_data + fx_unavailable; `resolution.remaining` = len(resolved usable).
- **Sub-Grund-Detail (kostenlose Verbesserung a):** `Dropout` + Feld `detail: str = ""`, für
  NO_SYMBOL_DATA befüllt mit dem Sub-Grund (`NO_RAW_MC` | `NO_CURRENCY` | `NO_VOLUME`); neue Spalte
  `detail` in `dropouts.csv`. So „leeres Dict" vs. „Währung weg" vs. „kein Volumen" sichtbar, ohne
  Code-Wildwuchs (ein Bucket, ein Code). **Detail-Präzedenz** bei mehreren Mängeln deterministisch:
  `NO_RAW_MC` → `NO_CURRENCY` → `NO_VOLUME` (mc-Grund vor Volumen).

## Tests (Pflicht — Guardrails, getestet nicht angenommen)

1. **Funnel-Mathematik desynct nicht (Guardrail 1).** `basis_gates.entered` MUSS aus
   `resolution.remaining` abgeleitet werden, **nicht** unabhängig gezählt — sonst wird die
   Reconciliation eine Tautologie (zwei getrennt gefütterte Zahlen) statt ein echter Check. Test:
   bei nicht-leerer Divert-Menge gilt `resolution.remaining == basis_gates.entered` und
   `|Universum| == Σ alle Drops + crosshits/edgar-übrig`. Explizit verifizieren, dass die
   geschrumpfte `resolved`-Liste `pass_through_count` und den `sector_wide`-Nenner **nicht**
   verschiebt (ML/RNL/GLB erreichten das gross_margin-Gate ohnehin nie → Nenner unkritisch, aber
   per Test belegt).
2. **Anti-Over-Fire (Guardrail 2, der wichtigste Test).** `ATO.PA`-Klasse: realer `market_cap`
   (z.B. 728M), reales Volumen, currency + FX OK → `reason=OK` → **gated, NICHT divertiert**.
   Beweist, dass 0b legitime Small-Caps **nicht** frisst (Invariante kippt nicht in „jeder kleine
   Titel → REVIEW"). Symmetrisch zu den Divert-Tests; ohne ihn ist die Logik nur halb verifiziert.
3. **Divert-Tests (alle drei Lücken):** mc=None → NO_SYMBOL_DATA; mc=0 (→None) → NO_SYMBOL_DATA;
   currency=None (mc da) → NO_SYMBOL_DATA; vol=None → NO_SYMBOL_DATA; mc+currency da, FX-Rate None
   → NO_FX → FX_UNAVAILABLE. Plus: Sub-Grund-`detail` korrekt befüllt.
4. **NO_CURRENCY-Präzedenz (Guardrail 4):** mc=None ∧ currency=None → geloggter Grund =
   `NO_RAW_MC` (mc-zuerst), reproduzierbar.
5. **Severity:** beide neuen Codes immer REVIEW (auch ohne large-cap).

Alle offline, DI-Mocks, kein Netz.

## Acceptance (Cold-Run) — Menge + Postcondition, KEINE Zahl (Guardrail 3)

„`review_flags` steigt um die Divert-Zahl" ist **tautologisch** — nicht die Acceptance. Substanz:
- **Mengen-Prognose:** Divert-Menge **⊇ {ML.PA, RNL.PA, GLB.IR}** (als RESOLUTION_NO_SYMBOL_DATA
  REVIEW).
- **Postcondition:** **null** verbleibende `basis_gates`-BENIGN-Drops mit `market_cap`=None **oder**
  `avg_daily_volume`=None. (Der eigentliche „keine stille Maskierung mehr"-Beweis.)
- **>3 Diverts ist KEIN Fehlschlag**, sondern weitere bisher unsichtbare Maskierung, die rauskommt
  (erwartbar **≥3**). So framen — „4 statt 3" ist ein **Fund**, kein Defekt.
- `RESOLUTION_FX_UNAVAILABLE`-Count macht jede FX-Maskierung sichtbar (vermutlich 0 auf sauberem
  Lauf; Nicht-Null = FX-Fix-Trigger).
- Reconciliation hält weiter; Survivor-Set **unverändert** (Divertierte waren immer Nicht-Survivor).

## Disziplin / Grenzen

- Echte Logik-Änderung (Resolution-Klassifikation), aber **survivor-neutral** (verschiebt nur
  Bucket BENIGN→REVIEW + Gate→Resolution). Eigener TDD + Cold-Run-Acceptance-Gate, kein Push/Merge
  ohne Go.
- **Kein Retry hier (Notiz b):** `run_basis_filter` retryt den yfinance-Fetch aktuell **nicht** →
  `NO_SYMBOL_DATA` kann gelegentlich **transiente** Misses enthalten (in REVIEW unschädlich). Die
  Count **nicht** als „alles Müll" fehllesen; ein Resolution-Retry ist ein möglicher späterer
  Härtungsschritt, **nicht** 0b.
- 0b ist die Generalisierung; danach **Punkt 1** (Volumen-Gate wert- statt stückbasiert).
