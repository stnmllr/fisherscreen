# Marker-Vocabulary (2a.1c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Source-Marker außerhalb des kontrollierten Vokabulars werden nicht mehr ungeprüft ins Dossier durchgereicht: bekannte Quant-Sub-Marker → kanonisch `yfinance, 5J`, genuin unbekannte → `Inferenz` + Warning.

**Architecture:** Eine neue reine Funktion `_normalize_sources` in `app/deepdive/synthesis.py` läuft im Punkt-Loop **vor** `_validate_sources`. Sie schützt Filing-Section-Cites per `_SECTION_CITE_RE.search`-Guard (zuerst), kanonisiert bekannte Marker über ein explizites `frozenset`-Vokabular und einen capture-class-faltenden Normalizer, kollabiert Unbekanntes zu `Inferenz` und dedupliziert order-preserving. Der bestehende Confidence-Downgrade keyt nach dem Umbau auf einen echten Section-Collapse (`validated != normalized`), nicht auf bloße Kanonisierung.

**Tech Stack:** Python 3.12, pytest (DI-Mock-Pattern via `MagicMock`), `re`, pydantic (bestehender `FisherPoint`-Validator). Lokaler Testaufruf via `uv run python -m pytest` (SOPRA-EPDR: kein `.exe`-Shim).

**Spec:** `docs/superpowers/specs/2026-05-29-deepdive-marker-vocabulary-design.md`

---

## File Structure

- **Modify:** `app/deepdive/synthesis.py`
  - Neue Modul-Konstanten `_CANONICAL_QUANT`, `_QUANT_MARKER_VOCAB`, `_SOFT_MARKER_VOCAB`, `_MARKER_CANON` direkt nach `_BODY_HEADING_PAT` (nach Z. 34).
  - Neue reine Funktionen `_norm_marker`, `_normalize_sources` ebendort.
  - Punkt-Loop in `run_synthesis` (Z. 212–222): `_normalize_sources`-Aufruf + A-Ordering-Umbau.
- **Modify:** `tests/deepdive/test_synthesis.py` — neue Tests am Dateiende anhängen (Sektion `# --- 2a.1c marker vocabulary ---`).

Keine neuen Dateien. `dossier_generator.py`, `deep_dive_record.py`, `valuation_block.py` bleiben unverändert.

---

## Task 1: Normalizer + Vokabular-Konstanten + Roundtrip-Property

**Files:**
- Modify: `app/deepdive/synthesis.py` (nach Z. 34, `_BODY_HEADING_PAT`)
- Test: `tests/deepdive/test_synthesis.py`

- [ ] **Step 1: Write the failing test (roundtrip property — sichert Bug 1, das Komma)**

Am Dateiende von `tests/deepdive/test_synthesis.py` anhängen:

```python
# --- 2a.1c marker vocabulary -----------------------------------------------

def test_norm_marker_roundtrip_canonical_in_vocab():
    """Every canonical vocabulary string must normalize to a key that the
    canon map actually carries. Guards Bug 1: 'yfinance, 5J' must fold to the
    same key its own lookup uses (comma in the fold class)."""
    from app.deepdive.synthesis import (
        _MARKER_CANON, _norm_marker, _QUANT_MARKER_VOCAB, _SOFT_MARKER_VOCAB,
    )
    for c in (*_QUANT_MARKER_VOCAB, *_SOFT_MARKER_VOCAB):
        assert _norm_marker(c) in _MARKER_CANON, f"{c!r} not roundtrip-stable"
    # the comma case explicitly
    assert _norm_marker("yfinance, 5J") in _MARKER_CANON
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py::test_norm_marker_roundtrip_canonical_in_vocab -v`
Expected: FAIL with `ImportError: cannot import name '_MARKER_CANON'` (Symbole existieren noch nicht).

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/synthesis.py` direkt nach `_BODY_HEADING_PAT` (Z. 34) einfügen:

```python
# 2a.1c — source-marker vocabulary. The model invents non-section markers that
# reference real quant material (e.g. "Quant-Snapshot", "Forward-Estimates").
# Known quant sub-markers are canonicalized to a single quant marker; genuinely
# unknown markers collapse to "Inferenz" with a warning. The vocabulary is an
# EXPLICIT set (NOT derived from QuantSnapshot.model_fields): Gemini sees the
# rendered valuation block, not field names, so a field rename must never
# silently drop a still-emitted marker. The warning log drives growth: a new
# marker fires once, then gets one line added here.
_CANONICAL_QUANT = "yfinance, 5J"

_QUANT_MARKER_VOCAB = (
    "Quant-Snapshot",
    "forward_estimates",
    "peer_comparison",
    "historical_series",
    "trend_metrics",
    "Bewertung",
    "Bewertung & Kapitalstruktur",
)
_SOFT_MARKER_VOCAB = ("yfinance, 5J", "Marktkontext", "Inferenz")


def _norm_marker(s: str) -> str:
    """Fold a marker to a comparison key: lowercase + strip + collapse the
    capture-class separators (whitespace, _, -, &, comma). The comma is in the
    class so the canonical 'yfinance, 5J' folds to the same key its lookup uses
    (Bug 1)."""
    return re.sub(r"[\s_\-&,]+", "", s.strip().lower())


# key -> canonical display form. Built via _norm_marker over BOTH vocabularies,
# so keys and canonical strings are consistent by construction (no hand-typed
# key can drift from its source string).
_MARKER_CANON: dict[str, str] = {}
for _m in _SOFT_MARKER_VOCAB:
    _MARKER_CANON[_norm_marker(_m)] = _m
for _m in _QUANT_MARKER_VOCAB:
    _MARKER_CANON[_norm_marker(_m)] = _CANONICAL_QUANT
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py::test_norm_marker_roundtrip_canonical_in_vocab -v`
Expected: PASS

- [ ] **Step 5: Commit**

```
git add app/deepdive/synthesis.py tests/deepdive/test_synthesis.py
git commit -m "Add marker-vocabulary constants and folding normalizer (2a.1c)"
```

---

## Task 2: `_normalize_sources` — Section-Guard, Kanonisierung, Collapse, Dedup

**Files:**
- Modify: `app/deepdive/synthesis.py` (Funktion direkt nach `_MARKER_CANON`)
- Test: `tests/deepdive/test_synthesis.py`

- [ ] **Step 1: Write the failing tests (pure-function behaviour)**

Am Dateiende von `tests/deepdive/test_synthesis.py` anhängen:

```python
import logging  # module-scope; pytest is already imported at the top of the file


@pytest.mark.parametrize("variant", [
    "Quant-Snapshot", "quant_snapshot", "quant snapshot",
    "forward_estimates", "Forward-Estimates", "forward estimates",
    "peer_comparison", "Peer-Comparison",
    "historical_series", "trend_metrics",
    "Bewertung", "Bewertung & Kapitalstruktur",  # '&' fold-class edge (byte-belegt)
])
def test_normalize_known_quant_variants_to_canonical(variant):
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources([variant]) == ["yfinance, 5J"]


def test_normalize_dedups_multiple_quant_markers():
    from app.deepdive.synthesis import _normalize_sources
    out = _normalize_sources(["Quant-Snapshot", "historical_series", "trend_metrics"])
    assert out == ["yfinance, 5J"]


def test_normalize_keeps_plain_section_cite_with_quant():
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["10-K §7", "Quant-Snapshot"]) == ["10-K §7", "yfinance, 5J"]


def test_normalize_section_guard_subparagraph_4b_passes_through():
    """Load-bearing (Lesson w / 1.5.2): the section guard must run via
    _SECTION_CITE_RE.search BEFORE _norm_marker, else '20-F §4B' folds the
    hyphen to '20f§4b', misses the vocab, and collapses to Inferenz — destroying
    grounding. Goes RED if the guard is missing or uses .fullmatch."""
    from app.deepdive.synthesis import _normalize_sources
    out = _normalize_sources(["20-F §4B"])
    assert out == ["20-F §4B"]


def test_normalize_section_guard_subparagraph_4b_no_warning(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        _normalize_sources(["20-F §4B"])
    assert "controlled vocabulary" not in caplog.text


def test_normalize_unknown_marker_collapses_to_inference_with_warning(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        out = _normalize_sources(["made_up_marker"])
    assert out == ["Inferenz"]
    assert "controlled vocabulary" in caplog.text
    assert "made_up_marker" in caplog.text


def test_normalize_passes_through_soft_markers():
    from app.deepdive.synthesis import _normalize_sources
    assert _normalize_sources(["Marktkontext"]) == ["Marktkontext"]
    assert _normalize_sources(["Inferenz"]) == ["Inferenz"]
    assert _normalize_sources(["yfinance, 5J"]) == ["yfinance, 5J"]


def test_normalize_no_warning_on_canonicalization(caplog):
    from app.deepdive.synthesis import _normalize_sources
    with caplog.at_level(logging.WARNING, logger="app.deepdive.synthesis"):
        _normalize_sources(["Quant-Snapshot", "Marktkontext", "yfinance, 5J"])
    assert "controlled vocabulary" not in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -k normalize -v`
Expected: FAIL with `ImportError: cannot import name '_normalize_sources'`.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/synthesis.py` direkt nach dem `_MARKER_CANON`-Aufbau (aus Task 1) einfügen:

```python
def _normalize_sources(sources: list[str]) -> list[str]:
    """Enforce the source-marker vocabulary (2a.1c). Runs BEFORE _validate_sources.

    - Filing-section cites (_SECTION_CITE_RE.search) pass through untouched. This
      guard MUST precede _norm_marker: otherwise '20-F §4B' folds to '20f§4b',
      misses the vocabulary, and collapses to Inferenz before _validate_sources
      ever sees it (destroys grounding — Lesson w / 1.5.2). .search, not
      .fullmatch, so a sub-paragraph like §4B still matches.
    - Known quant sub-markers -> _CANONICAL_QUANT; known soft markers -> their
      canonical form. Neither carries a confidence impact.
    - Anything else -> 'Inferenz' + warning (the warning is the catalogue-growth
      signal).
    - Order-preserving dedup at the end, so two distinct unknowns collapse to
      ['Inferenz'] and the FisherPoint validator's exact == ['Inferenz'] cap
      can fire."""
    out: list[str] = []
    for s in sources:
        if _SECTION_CITE_RE.search(s):
            out.append(s)
            continue
        canon = _MARKER_CANON.get(_norm_marker(s))
        if canon is not None:
            out.append(canon)
        else:
            logger.warning(
                "source %r not in controlled vocabulary -> Inferenz", s
            )
            out.append("Inferenz")
    seen: set[str] = set()
    deduped: list[str] = []
    for s in out:
        if s not in seen:
            seen.add(s)
            deduped.append(s)
    return deduped
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -k normalize -v`
Expected: PASS (all parametrized variants + dedup + section-guard + unknown + soft + no-warning).

- [ ] **Step 5: Commit**

```
git add app/deepdive/synthesis.py tests/deepdive/test_synthesis.py
git commit -m "Add _normalize_sources with section guard, canonicalization, dedup (2a.1c)"
```

---

## Task 3: Wire into `run_synthesis` loop — A-Ordering + Confidence-Anti-Regress

**Files:**
- Modify: `app/deepdive/synthesis.py:212-222` (Punkt-Loop)
- Test: `tests/deepdive/test_synthesis.py`

- [ ] **Step 1: Write the failing tests (confidence interaction via run_synthesis)**

Am Dateiende von `tests/deepdive/test_synthesis.py` anhängen:

```python
def test_quant_marker_canonicalized_and_keeps_green():
    """Load-bearing for A-ordering: pure canonicalization (Quant-Snapshot ->
    yfinance, 5J) must NOT trigger the section-collapse downgrade. Goes RED if
    the downgrade compares against the raw (pre-normalization) source list."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["Quant-Snapshot"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["yfinance, 5J"]
    assert pts[0].confidence == "🟢"


def test_two_unknown_markers_dedup_then_cap_to_yellow():
    """B: two distinct unknowns -> ['Inferenz', 'Inferenz'] -> dedup ->
    ['Inferenz'] -> FisherPoint validator caps 🟢 to 🟡."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["made_up_one", "made_up_two"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"


def test_unknown_marker_does_not_sink_grounded_point():
    """B-dual: a grounded point ([10-K §7, <unknown>]) keeps its section cite,
    is NOT capped (sources != ['Inferenz']), and stays 🟢."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["10-K §7", "made_up_marker"]
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="10-K",
        sections={"10-K_item7": "ITEM 7 MANAGEMENT DISCUSSION. We discuss."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["10-K §7", "Inferenz"]
    assert pts[0].confidence == "🟢"


def test_anti_regress_hallucinated_section_still_collapses_and_downgrades():
    """Anti-regress: a never-sent section cite still collapses to ['Inferenz']
    and downgrades 🟢 -> 🟡 after the normalize-before-validate refactor."""
    syn = MagicMock()
    data = _good_points()
    data["points"][0]["sources"] = ["20-F §99"]  # never sent
    data["points"][0]["confidence"] = "🟢"
    syn.synthesize.return_value = data
    pts = run_synthesis(
        ticker="X", form_type="20-F",
        sections={"20-F_item5": "ITEM 5 OPERATING REVIEW. We review."},
        quant=_qs(), synthesizer=syn, max_input_tokens=200000)
    assert pts[0].sources == ["Inferenz"]
    assert pts[0].confidence == "🟡"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -k "canonicalized_and_keeps_green or two_unknown_markers or does_not_sink or anti_regress_hallucinated" -v`
Expected: `test_quant_marker_canonicalized_and_keeps_green`, `test_two_unknown_markers_dedup_then_cap_to_yellow`, `test_unknown_marker_does_not_sink_grounded_point` FAIL (sources noch nicht normalisiert — `_normalize_sources` ist noch nicht im Loop verdrahtet). `test_anti_regress_hallucinated_section_still_collapses_and_downgrades` PASSt evtl. schon (bestehendes Verhalten) — das ist ok.

- [ ] **Step 3: Write minimal implementation**

In `app/deepdive/synthesis.py` den Block Z. 213–222 ersetzen.

Vorher:

```python
        sources = list(rp.get("sources", []))
        validated = _validate_sources(sources, form_type, sent_keys, sections)
        if validated != sources:
            logger.warning(
                "point %s: hallucinated section cite -> downgraded to Inferenz",
                rp.get("number"),
            )
            rp = {**rp, "sources": validated}
            if rp.get("confidence") == "🟢":
                rp["confidence"] = "🟡"
```

Nachher:

```python
        sources = list(rp.get("sources", []))
        normalized = _normalize_sources(sources)
        validated = _validate_sources(normalized, form_type, sent_keys, sections)
        rp = {**rp, "sources": validated}
        # The confidence downgrade keys on a SECTION collapse (validated differs
        # from the already-normalized list), NOT on mere canonicalization —
        # otherwise every quant-citing point would be falsely demoted from 🟢.
        if validated != normalized:
            logger.warning(
                "point %s: hallucinated section cite -> downgraded to Inferenz",
                rp.get("number"),
            )
            if rp.get("confidence") == "🟢":
                rp["confidence"] = "🟡"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -k "canonicalized_and_keeps_green or two_unknown_markers or does_not_sink or anti_regress_hallucinated" -v`
Expected: PASS (alle vier).

- [ ] **Step 5: Run the full suite + coverage gate**

Run: `uv run python -m pytest`
Expected: PASS, Coverage ≥ 96 % (zentral in `[tool.pytest.ini_options]` konfiguriert). Insbesondere müssen die bestehenden `test_hallucinated_section_downgraded_to_inference`, `test_mixed_sources_with_one_hallucination_collapses_all`, `test_inference_only_caps_confidence` weiterhin grün sein (Anti-Regress des Refactors).

- [ ] **Step 6: Commit**

```
git add app/deepdive/synthesis.py tests/deepdive/test_synthesis.py
git commit -m "Wire _normalize_sources before _validate_sources with collapse-keyed downgrade (2a.1c)"
```

---

## Stop-Bedingungen

- Coverage < 96 % → STOP.
- Ein bestehender Test bricht und der Bruch ist **nicht** eine bewusste Verhaltensänderung dieses Specs → STOP, Root-Cause vor Weiterarbeit.
- Working-Tree-Drift (`data/adr_table.json`, `output/Universum/2026-05-Changes.md`, untracked `scripts/diagnose_*`, Baselines) gerät in einen Commit → STOP, gezielt entfernen (`git restore --staged`).
- Kein Push, kein PROJEKTSTAND-Edit, kein Merge ohne explizites Go von Stephan.

## Verifikations-Hinweis (kein Code-Schritt)

Reine Korrektheit ist unit-test-only abgedeckt (deterministisch, kein LLM). **Vollständigkeit** des Vokabulars zeigt sich erst im echten Lauf: beim nächsten ohnehin anfallenden Deep-Dive das `app.deepdive.synthesis`-Warning-Log auf `not in controlled vocabulary`-Zeilen prüfen (erwartbare Kandidaten: bare `yfinance`, `Forward-Konsens`, `Analyst Consensus`) → ggf. je eine Zeile in `_QUANT_MARKER_VOCAB` nachziehen. Keine bezahlte Re-Verifikation nötig.
