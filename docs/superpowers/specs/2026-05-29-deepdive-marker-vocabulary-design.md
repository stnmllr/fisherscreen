# 2a.1c — Marker-Spec-Gap: Source-Marker-Vokabular durchsetzen

> Spec, Phase 1.2. Status: genehmigt (Brainstorm + Code-Review 2026-05-29).
> Scope: **code-only, unit-test-only**. Keine bezahlte Re-Verifikation, kein Prompt-Edit,
> kein 5J-Range-Vorgriff (Phase 1.3), kein PROJEKTSTAND-Edit vor Merge.

## Problem

Das Synthesis-Modell (Gemini) erfindet vereinzelt Source-Marker außerhalb des im
SOURCES-Prompt-Block gelisteten Vokabulars. Diese Marker werden heute **ungeprüft ins
Dossier durchgereicht**.

### Start-Check gegen echten Code (verifiziert 2026-05-29)

- **Es gibt keine Whitelist-Datenstruktur.** Das erlaubte Vokabular existiert nur als
  Prosa im SOURCES-Prompt-Block (`synthesis.py:87–92`): `<form> §<item>`, `yfinance, 5J`,
  `Marktkontext`, `Inferenz`. Das ist eine **soft** Prompt-Instruktion, die das Modell
  unterläuft.
- **Hard-enforced wird ausschließlich der Filing-Section-Cite** (`_validate_sources`,
  `synthesis.py:262–308`, via `_SECTION_CITE_RE` Z. 29). Jeder Nicht-Section-Marker
  trifft `else: continue` (Z. 281) und passiert **unverändert**.
- **Marker sind reine Anzeige** (`dossier_generator.py:78,84`: `[{s}]` ans reasoning
  angehängt). Kein Downstream-Parser, keine Anchor-Links. Es geht um **Glaubwürdigkeit
  der Quellenangabe**, nicht um Breakage.

### Live belegte erfundene Marker (byte-genau, MSFT/GOOGL-Dossiers 2026-05-27/-28)

Alle referenzieren **echtes, im Prompt gesendetes Quant-Material** — legitime harte
Quant-Quellen mit nicht-kanonischem Namen. Capture-Class-Edge (case / `-` / `_` / `&` /
Suffix) bestätigt:

| Konzept | gesichtete Varianten |
|---|---|
| Quant-Snapshot | `Quant-Snapshot` |
| Forward Estimates | `forward_estimates` · `Forward-Estimates` |
| Peer-Vergleich | `peer_comparison` · `Peer-Comparison` |
| Historie | `historical_series` |
| Trend | `trend_metrics` |
| Bewertung | `Bewertung` · `Bewertung & Kapitalstruktur` |

## Entscheidung

**Mischform: kanonisieren + Collapse.** Pro Marker eines Punkts, in Reihenfolge:

1. **Section-Cite-Guard — ZUERST, in `_normalize_sources` selbst.** Jeder Marker, der
   `_SECTION_CITE_RE.search(s)` matcht, wird **unverändert durchgereicht** und nie
   normalisiert. Kritisch: dieser Guard muss **vor** `_norm_marker` greifen, weil
   `_normalize_sources` **vor** `_validate_sources` läuft. Ohne ihn würde `_norm_marker`
   den Bindestrich in `20-F §4B` falten → `20f§4b` → kein Vokabular-Treffer → Collapse
   auf `Inferenz`, bevor `_validate_sources` den Cite je sieht → **Grounding zerstört**
   (genau der Wurzelfix aus Lesson w / 1.5.2). `.search`, **nicht** `.fullmatch` — sonst
   matcht `§4B` nicht und fällt durch. Die nachgelagerte `_validate_sources`-Logik
   (Whole-List-Collapse bei nicht-gesendeter / fehlgelabelter Section inkl. 🟢→🟡-
   Downgrade) bleibt **unverändert**. Anti-Regress: nicht anfassen.
2. **Normalisierter Key** über alle Nicht-Section-Marker:
   - **Key ∈ Quant-Vokabular** → ersetze durch kanonisch **`yfinance, 5J`**.
     **Keine Confidence-Änderung** (echte harte Quant-Quelle).
   - **Key ∈ Kanonisch-Soft** (`Marktkontext`, `Inferenz`) bzw. = Collapse-Ziel
     (`yfinance, 5J`) → **unverändert** durchreichen.
   - **Sonst (genuin erfunden)** → ersetze durch **`Inferenz`** + `logging.warning`.
3. **Order-preserving Dedup** (mehrere Quant-Sub-Marker → ein `yfinance, 5J`;
   mehrere Unknowns → ein `Inferenz`).

### Normalizer (Capture-Class-Härtung)

```python
def _norm_marker(s: str) -> str:
    return re.sub(r"[\s_\-&,]+", "", s.strip().lower())
```

- Fold-Klasse enthält **das Komma** (`,`). Begründung unten (Bug 1).
- Faltet `peer_comparison` = `Peer-Comparison` → `peercomparison`,
  `forward_estimates` = `Forward-Estimates` → `forwardestimates`, etc.

### Vokabular — explizit deklariert (Tupel + abgeleitete Map), keine Ableitung aus `model_fields`

Das Vokabular wird **explizit** neben `_SECTION_CITE_RE` deklariert, **nicht** aus
`QuantSnapshot.model_fields` abgeleitet.

**Begründung (Code-Review-Befund):** Gemini sieht nie `QuantSnapshot.model_fields`,
sondern den **gerenderten** `valuation_block`-Text (`## Bewertung & Kapitalstruktur`,
`valuation_block.py:8`, sowie Labels wie „Forward-Konsens", „Analyst Consensus").
Dass die snake_case-Marker = Feldnamen sind, ist eine **Namens-Koinzidenz**, keine
kausale Bindung. Eine abgeleitete Liste würde
(a) bei einem Feld-Rename ohne Label-Rename einen weiterhin legitim erfundenen Marker
**still zu `Inferenz` kollabieren** (Regression an scheinbar unbeteiligter Stelle), und
(b) `gemini_dimensions` (Tool-A-Gemini-Dims, **nicht** yfinance) fälschlich auf
`yfinance, 5J` mappen. Das explizite Set ist auditierbar; das `logging.warning` aus
Schritt 2 ist der Wachstums-Mechanismus: neuer Quant-Marker → Log feuert einmal →
eine Zeile nachziehen.

Roh-Strings (vor Normalisierung), seeded aus den byte-belegten Live-Markern:

```python
_QUANT_MARKER_VOCAB = ("Quant-Snapshot", "forward_estimates", "peer_comparison",
                       "historical_series", "trend_metrics",
                       "Bewertung", "Bewertung & Kapitalstruktur")
_SOFT_MARKER_VOCAB = ("yfinance, 5J", "Marktkontext", "Inferenz")
```

Die Lookup-Keys werden **durch denselben `_norm_marker`** erzeugt
(`{_norm_marker(s) for s in _QUANT_MARKER_VOCAB}` etc.) — beide Seiten sind per
Konstruktion konsistent.

## Code-Review-Befunde (eingearbeitet)

### Bug 1 — Normalizer fraß den kanonischen Zielstring (behoben)

`_norm_marker("yfinance, 5J")` ergäbe mit Fold-Klasse `[\s_\-&]+` den Wert `yfinance,5j`
(Komma bleibt stehen) ≠ ein von Hand notierter Key `yfinance5j`. Der **eigene
kanonische Marker** fiele in den Sonst-Zweig → Collapse auf `Inferenz` + Warning.
**Doppelter Fix:** (a) Komma in die Fold-Klasse aufgenommen; (b) Vokabular-Keys werden
mit `_norm_marker` selbst erzeugt, nie von Hand. Property-Test sichert
`normalize(canonical) ∈ vocab`.

### A — Confidence-Interaktion (Ordering tragend)

Der bestehende Downgrade (`synthesis.py:215`) feuert bei `validated != sources` (roh).
Reine Kanonisierung (`Quant-Snapshot` → `yfinance, 5J`) **darf keinen Downgrade
auslösen** — sonst fiele jeder Quant-zitierende Punkt fälschlich von 🟢 auf 🟡 mit
irreführender „hallucinated section"-Warnung. **Restructure:** Kanonisierung +
Unknown-Collapse + Dedup laufen **vor** `_validate_sources`; der `!=`-Downgrade
vergleicht gegen die bereits-kanonisierte Liste und feuert damit nur noch bei echtem
Section-Collapse. Die Warnung Z. 216–219 bleibt wortgetreu korrekt.

### B — Unknown-Collapse kappt Confidence nicht separat (relies on Dedup)

Erfundene Marker werden per-Marker durch `Inferenz` ersetzt; valide Geschwister
(Section-Cites, Quant) bleiben. Bleibt danach nur `["Inferenz"]`, greift der
**bestehende** Validator `_inference_only_caps_confidence` (`deep_dive_record.py:55`,
exakt `self.sources == ["Inferenz"]`). Kein neuer Confidence-Code. **Voraussetzung:**
Zwei distinkte Unknowns → `["Inferenz", "Inferenz"]` müssen **erst durch den Dedup
(Schritt 3)** auf `["Inferenz"]` fallen, bevor die exakte Listengleichheit greift.

**Out-of-scope (bewusst stehengelassen):** ein Punkt mit nur `[Marktkontext]` bleibt
ungecappt — bestehendes Verhalten, nicht 2a.1c.

### Operative Konsequenz (kein Code-Change, bewusst halten)

Der Spec kippt das **Default** für nicht-katalogisierte Nicht-Section-Marker von
„pass-through" auf „`Inferenz` + Log". Beim nächsten echten Lauf sind daher neue Warnings
**erwartbar** — für legitime-aber-nicht-katalogisierte Quant-Labels, die das Modell
gerendert sieht, z. B. bare `[yfinance]` (`_norm_marker` → `yfinance` ≠ `yfinance5j` →
**kollabiert!**), `[Forward-Konsens]`, `[Analyst Consensus]`. Das ist **by design**:
konservativ (untertreibt statt zu überschätzen), geloggt, Ein-Zeilen-Fix (Roh-String ins
`_QUANT_MARKER_VOCAB` nachziehen). Es ist die schmale, temporäre Wiederkehr des
Option-3-Problems bis zum Katalog-Nachzug.

`unit-test-only / keine bezahlte Re-Verifikation` ist für die **Korrektheit** richtig; die
**Vollständigkeit** zeigt sich erst im echten Lauf. → **Faktischer Completeness-Check:**
beim nächsten ohnehin anfallenden Deep-Dive das Warning-Log anschauen, nicht extra Geld
ausgeben. (Hinweis aus Code-Review 2026-05-29.)

## Komponenten / Schnittstellen

- **`synthesis.py`** — neue reine Funktion `_normalize_sources(sources) -> list[str]`
  (Section-Cite-Guard via `_SECTION_CITE_RE.search` **zuerst** → Kanonisierung →
  Unknown-Collapse → Dedup; Quant-/Soft-Vokabular + `_norm_marker`).
  Aufruf im Punkt-Loop **vor** `_validate_sources`; der `!=`-Downgrade-Vergleich nutzt
  die normalisierte Liste als Baseline.
- **`_validate_sources`** — unverändert (Section-Cite-Logik).
- **`deep_dive_record.py` / `dossier_generator.py`** — unverändert.

## Test-Plan (TDD, RED zuerst, Suite ≥ 96 %)

Fixtures aus den byte-belegten Live-Dossiers.

1. **Varianten-Normalisierung** je Konzept, parametrisiert über case / `-` / `_` / **`&`**
   → `yfinance, 5J`. Das `&` ist eigene Fold-Klassen-Kante: `Bewertung & Kapitalstruktur`
   (byte-belegt) **explizit** in den Param-Set.
2. **Roundtrip-Property:** `_norm_marker(c) ∈ keyset` für jedes `c` in
   `_QUANT_MARKER_VOCAB ∪ _SOFT_MARKER_VOCAB` (sichert Bug 1, inkl. `yfinance, 5J`).
3. **Dedup:** `[Quant-Snapshot, historical_series, trend_metrics]` → `[yfinance, 5J]`.
4. **Mixed (plain Section):** `[10-K §7, Quant-Snapshot]` → `[10-K §7, yfinance, 5J]`
   (Section erhalten).
5. **§4B-Section-Guard (load-bearing, Lesson w / 1.5.2):**
   `_normalize_sources(["20-F §4B"]) == ["20-F §4B"]`, **keine** Warning. Muss **ROT**
   werden, wenn die Section-Erkennung in `_normalize_sources` fehlt **oder** `.fullmatch`
   statt `.search` nutzt. Das ist die eigentliche Anti-Regress gegen den 1.5.2-Wurzelfix.
6. **Unknown** → `Inferenz` + `logging.warning` (via `caplog`).
7. **Pass-through:** `Marktkontext` / `Inferenz` / `yfinance, 5J` unverändert, keine Warning.
8. **Keine Warning bei Kanonisierung:** bekannter Quant-Marker → `yfinance, 5J` läuft
   **ohne** Warning (nur Unknowns warnen) — assert in Test 1/3.
9. **Anti-Regress Confidence (load-bearing):** Punkt mit `[Quant-Snapshot]` 🟢 bleibt 🟢.
   Muss unter falscher Ordering (Vergleich gegen Roh-Liste) wirklich **ROT** werden.
10. **B — Cap via Dedup:** Punkt mit zwei distinkten Unknown-Markern →
    `["Inferenz"]` → 🟡.
11. **B-Dual — Unknown versenkt Grounding nicht:** Punkt mit `[10-K §7, <unknown>]` →
    `[10-K §7, Inferenz]`, **nicht** gecappt, 🟢 bleibt 🟢 (Gegenstück zu Test 9).
12. **Anti-Regress Section:** halluzinierter Section-Cite kollabiert weiterhin zu
    `["Inferenz"]` + 🟢→🟡-Downgrade.

## Stop-Bedingungen (aus Plan übernommen)

- Capture-Class-Edge bei Marker-Varianten unklar → STOP, gegen reale Dossier-Strings
  byte-prüfen.
- Coverage < 96 % → STOP.
- Working-Tree-Drift im Commit → STOP, bereinigen.
- Kein Push ohne explizites Go.
