---
title: Punkt 5 — Filing-Parser (Anchor-Tracing)
status: Entwurf 4 (Plan-akzeptanz-reif)
created: 2026-05-21
last_updated: 2026-05-26
diagnostic_base:
  - docs/superpowers/diagnostic-reports/ (Diagnose-Phase, drei Runden — Original + E1/E2/E3 + E1.1)
plan_phase_discussion: in this conversation (Plan-Phase Punkt 5, Entwurf 0 → 1 → 2)
---

# Punkt 5 — Filing-Parser-Anchor-Tracing Implementation Plan

## Goal

Filing-Parser von Pattern-Matching auf html2text-Output umstellen auf DOM-Anchor-Link-Tracing. Adressiert F1 (TOC-gewinnt-immer), F2 (Last-Item-Tail-Absorption), F3 (truncated-überschreibt-ambiguous), F4 (Validator-blind), F6 (Page-Header-Flutung) für SEC-EDGAR-10-K und SEC-EDGAR-20-F. F5+F7 (ASML-Typ ohne Anchor-Links) bleiben konditional als technische Schuld nach Stage 4.

## Architecture

5-Stufen-Sequenz, je eigene Branch, einzeln gemergt. Hauptpfad: BS4-basiertes Anchor-Resolver-Modul, das TOC-Anchor-Link-Hrefs auf DOM-Section-IDs auflöst, anchor-aligned HTML-Slices erzeugt, html2text pro Slice ausführt. Fallback: heutige html2text-Pattern-Matching-Logik unverändert für Filings ohne usable Anchor-Coverage.

C1-Constraint (F4 vor/mit F2): in Stage 2 fallen F1+F2+F4 simultan durch Anchor-basierte Boundaries. Stage 3 fügt body-content-aware Validator-Härtung als Defense-in-Depth dazu.

## Tech Stack

- BS4 (`beautifulsoup4>=4.14`) mit `lxml-xml`-Parser (iXBRL-Filings sind XML, nicht HTML)
- html2text (bestehend, unverändert)
- pytest mit Real-Filing-Cache-Fixtures + bestehende synthetische Spec-Tests
- Filing-Cache (bestehend aus Punkt 1): cached **Rohtext**, nicht Parser-Output — kein Versions-Bump nötig (siehe Step 2.6)

---

## F-Klassen-Coverage nach Plan

| Klasse | Beschreibung | Adressiert in Stufe | Status nach Plan |
|---|---|---|---|
| F1 | TOC-gewinnt-immer (Pipe-Form) | 2 | gelöst |
| F2 | Last-Item-Tail-Absorption | 2 | gelöst |
| F3 | `truncated` überschreibt `ambiguous` | 2 (Schema-Neudesign) | gelöst |
| F4 | Validator blind gegen mis-labeled Bodies | 2 (strukturell) + 3 (Defense-in-Depth) | gelöst |
| F5 | Section-Headings ohne ITEM-Präfix (ASML) | 4 (konditional) | konditional / technische Schuld |
| F6 | Page-Header-Flutung (NOVO) | 2 | gelöst |
| F7 | Cover-Page-Checkbox als Anker (ASML) | 4 (konditional) | konditional / technische Schuld |
| F8-Kandidat | Modell-Halluzination unter validem Cite | nicht in Scope | bewusst zurückgestellt; eigene Initiative |

## Empirisch validierte Annahmen (aus Plan-Phase-Diagnose)

| Annahme | Validierung | Status |
|---|---|---|
| 3/4 Cache-Filings haben volle Anchor-Coverage | KO 5/5, GOOGL 5/5, NOVO 3/3 | empirisch hart |
| ASML hat 0 Anchor-Coverage für SEC-Items | DOM-Probe 0/3, Marker-Investigation in Stufe 4 | empirisch hart, Mitigation konditional |
| Token-Budget für Stage-2-Prompts hält | KO worst case 13,4% des 1M-Context | empirisch hart |
| Slice-html2text-Output = Vollkontext-Substring (byte-identisch) | N1-Probe, 3/3 Stichproben 100% | empirisch hart, N=3 |
| Pattern `^[\s\S]{0,300}?\bITEM\s+N\b` fängt alle observed Body-Prefixe | N3-Probe, 13/13 Sections | empirisch hart |
| `_FORM_ITEMS`-Drop-Verhalten für intermediäre Items (N4) | Design-Entscheidung Stephan | **entschieden: (a) Drop** |

---

## Stage 1 — Anchor-Resolver-Helper-Modul

### Files

- **Create:** `app/deepdive/anchor_resolver.py`
- **Create:** `tests/deepdive/test_anchor_resolver.py`

### Modul-API

```python
from dataclasses import dataclass
from bs4 import BeautifulSoup

@dataclass(frozen=True)
class AnchorMatch:
    item_label: str        # e.g. "1", "1A", "4", "18"
    anchor_id: str         # the value inside id="..."
    dom_position: int      # position of id="..." in raw_html (for ordering)
    next_text_excerpt: str # first 250 chars of body, for diagnostics

def resolve_anchors(raw_html: str) -> list[AnchorMatch]:
    """Returns all anchor-link targets whose next-text starts with 'ITEM N',
    sorted by document position. Empty list if no usable anchor-links found
    (caller should fall back to heuristic parser)."""
    ...
```

### Tasks

- [ ] **Step 1.1: Write failing test for KO 10-K coverage**

  ```python
  def test_anchor_resolver_ko_10k_full_coverage():
      raw = (CACHE_DIR / "0000021344" / "0001628280-26-010047.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      result = resolve_anchors(raw)
      expected_items = {"1", "1A", "1B", "1C", "2", "3", "4", "5",
                        "6", "7", "7A", "8", "9", "9A", "9B", "9C",
                        "10", "11", "12", "13", "14", "15", "16"}
      found_items = {m.item_label.upper() for m in result}
      assert expected_items <= found_items, (
          f"missing: {expected_items - found_items}"
      )
      # spot-check: item 1A body excerpt starts with "ITEM 1A. RISK FACTORS"
      item_1a = next(m for m in result if m.item_label.upper() == "1A")
      assert re.match(
          r"^.{0,80}?\bITEM\s+1A\b", item_1a.next_text_excerpt, re.I | re.DOTALL
      )
  ```

  Run: `uv run python -m pytest tests/deepdive/test_anchor_resolver.py::test_anchor_resolver_ko_10k_full_coverage -v`
  Expected: FAIL (resolve_anchors not implemented yet)

- [ ] **Step 1.2: Implement resolve_anchors**

  ```python
  from __future__ import annotations
  import re
  import warnings
  from collections import defaultdict
  from dataclasses import dataclass
  from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning
  from bs4.element import Tag

  warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

  _ITEM_RE = re.compile(r"^.{0,80}?\bITEM\s+(\d+[A-Z]?)\b", re.IGNORECASE | re.DOTALL)


  @dataclass(frozen=True)
  class AnchorMatch:
      item_label: str
      anchor_id: str
      dom_position: int
      next_text_excerpt: str


  def _read_next_text(el: Tag, max_chars: int = 250) -> str:
      buf, chars, cur = [], 0, el
      own = el.get_text(" ", strip=True)
      if own:
          buf.append(own)
          chars += len(own)
      while chars < max_chars:
          sib = cur.find_next_sibling() if isinstance(cur, Tag) else None
          if sib is None:
              par = cur.parent if isinstance(cur, Tag) else None
              if par is None:
                  break
              cur = par
              continue
          cur = sib
          if isinstance(cur, Tag):
              t = cur.get_text(" ", strip=True)
              if t:
                  buf.append(t)
                  chars += len(t) + 1
      return " ".join(buf)[:max_chars]


  def resolve_anchors(raw_html: str) -> list[AnchorMatch]:
      soup = BeautifulSoup(raw_html, "lxml-xml")
      by_href: dict[str, list[str]] = defaultdict(list)
      for a in soup.find_all("a", href=True):
          h = a.get("href", "")
          if h.startswith("#"):
              t = a.get_text(" ", strip=True)
              if t:
                  by_href[h[1:]].append(t)
      matches: list[AnchorMatch] = []
      for tid in by_href.keys():
          target = soup.find(attrs={"id": tid}) or soup.find("a", attrs={"name": tid})
          if target is None:
              continue
          excerpt = _read_next_text(target, 250)
          m = _ITEM_RE.match(excerpt)
          if not m:
              continue
          # Position-Lookup mirrors the symmetric Target-Lookup above
          # (id OR name): the name fallback is required for the HTML4
          # <a name="..."> convention (test_anchor_resolver_old_a_name_convention).
          pos = raw_html.find(f'id="{tid}"')
          if pos < 0:
              pos = raw_html.find(f'name="{tid}"')
          if pos < 0:
              continue
          matches.append(
              AnchorMatch(
                  item_label=m.group(1).upper(),
                  anchor_id=tid,
                  dom_position=pos,
                  next_text_excerpt=excerpt,
              )
          )
      matches.sort(key=lambda m: m.dom_position)
      return matches
  ```

  Run: `uv run python -m pytest tests/deepdive/test_anchor_resolver.py::test_anchor_resolver_ko_10k_full_coverage -v`
  Expected: PASS

- [ ] **Step 1.3: Add failing test for GOOGL 10-K (page-header tolerance)**

  ```python
  def test_anchor_resolver_googl_10k_with_page_header_prefix():
      raw = (CACHE_DIR / "0001652044" / "0001652044-26-000018.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      result = resolve_anchors(raw)
      expected_items = {"1", "1A", "1B", "1C", "2", "3", "4", "5",
                        "6", "7", "7A", "8", "9A", "9B", "9C",
                        "10", "11", "12", "13", "14", "15", "16"}
      found_items = {m.item_label.upper() for m in result}
      assert expected_items <= found_items
      # GOOGL §1A target has prefix "Table of Contents Alphabet Inc."
      item_1a = next(m for m in result if m.item_label.upper() == "1A")
      assert "Table of Contents" in item_1a.next_text_excerpt
      assert "ITEM 1A" in item_1a.next_text_excerpt.upper()
  ```

  Run + Expected: PASS (regex `^.{0,80}?` tolerates the prefix)

- [ ] **Step 1.4: Add failing test for NOVO 20-F (bare-number style)**

  ```python
  def test_anchor_resolver_novo_20f_bare_number_style():
      raw = (CACHE_DIR / "0000353278" / "0000353278-26-000012.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      result = resolve_anchors(raw)
      items = {m.item_label.upper() for m in result}
      assert {"4", "5", "18"} <= items
      item_4 = next(m for m in result if m.item_label.upper() == "4")
      # NOVO uses "ITEM 4 INFORMATION..." (no period)
      assert re.match(
          r"^.{0,80}?\bITEM\s+4\b",
          item_4.next_text_excerpt,
          re.I | re.DOTALL,
      )
  ```

  Run + Expected: PASS

- [ ] **Step 1.5: Add failing test for ASML 20-F (empty result)**

  ```python
  def test_anchor_resolver_asml_20f_no_sec_item_anchors():
      raw = (CACHE_DIR / "0000937966" / "0001628280-26-011378.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      result = resolve_anchors(raw)
      # ASML has 0 SEC-Item TOC-anchors (only Design-Report chapter anchors
      # and Financial-Statement footnote anchors land on Item-N pattern).
      # Confirm: items 4, 5, 18 are NOT in the result.
      sec_items = {m.item_label.upper() for m in result} & {"4", "5", "18"}
      assert sec_items == set(), (
          f"unexpected SEC-item anchors found: {sec_items}"
      )
  ```

  Run + Expected: PASS

- [ ] **Step 1.6: Synthetic edge-case tests**

  ```python
  def test_anchor_resolver_empty_html():
      assert resolve_anchors("") == []

  def test_anchor_resolver_no_internal_anchors():
      html = "<html><body><p>No anchors at all</p></body></html>"
      assert resolve_anchors(html) == []

  def test_anchor_resolver_old_a_name_convention():
      html = '''<html><body>
        <a href="#sec1">Item 1.</a>
        <a name="sec1"></a>
        <p>ITEM 1. BUSINESS overview text</p>
      </body></html>'''
      result = resolve_anchors(html)
      assert len(result) == 1
      assert result[0].item_label == "1"

  def test_anchor_resolver_target_with_direct_text():
      html = (
          "<html><body>"
          '<a href="#sec1">Item 1.</a>'
          '<div id="sec1">ITEM 1. BUSINESS overview text</div>'
          "</body></html>"
      )
      result = resolve_anchors(html)
      assert len(result) == 1
      assert result[0].item_label == "1"
      assert "ITEM 1" in result[0].next_text_excerpt.upper()

  def test_anchor_resolver_href_without_matching_target():
      html = (
          "<html><body>"
          '<a href="#nonexistent">Item 1.</a>'
          "<p>ITEM 1. some text without anchor target</p>"
          "</body></html>"
      )
      assert resolve_anchors(html) == []

  def test_anchor_resolver_single_quote_id_position_mismatch():
      # BS4 finds the target (re-serialising attribute quotes as double-quote),
      # but the raw_html keeps the original single-quotes. Both id="..." and
      # name="..." position-lookups miss → match is discarded. Defensive guard
      # against attribute-quote / entity edge cases in non-canonical HTML.
      html = (
          "<html><body>"
          "<a href='#sec1'>Item 1.</a>"
          "<div id='sec1'>ITEM 1. BUSINESS overview text</div>"
          "</body></html>"
      )
      assert resolve_anchors(html) == []
  ```

  Run + Expected: PASS

- [ ] **Step 1.7: Commit**

  ```cmd
  git checkout -b feature/punkt5-stage1-anchor-resolver
  git add app/deepdive/anchor_resolver.py tests/deepdive/test_anchor_resolver.py
  git commit -m "Add anchor_resolver module for TOC-href-based section discovery"
  ```

### Verification Criterion

`uv run python -m pytest tests/deepdive/test_anchor_resolver.py -v` shows 10/10 tests PASS. Coverage report shows 100% of `anchor_resolver.py`.

### Aufwand

2 Tage.

---

## Stage 2 — Filing-Parser-Integration

### Files

- **Modify:** `app/deepdive/filing_parser.py`
- **Modify:** `app/deepdive/dossier_generator.py` (Frontmatter-Rendering für neues section_flags-Schema)
- **Modify:** `app/models/deep_dive_record.py` (Type-Hint für section_flags)
- **Modify:** `tests/deepdive/test_filing_parser.py` (Spec-Tests an neues Schema anpassen)
- **Create:** `tests/deepdive/test_filing_parser_real.py` (Real-Filing-Validierungs-Basis)

### Schema-Änderung

```python
# Before:
@dataclass
class ParsedFiling:
    sections: dict[str, str]
    section_flags: dict[str, str]  # values: ambiguous, missing, truncated

# After:
@dataclass
class SectionFlag:
    extraction: str        # "ok" | "fallback_used"
    missing: bool          # True wenn nicht im sections-dict (kein Body)
    truncated: bool
    anchor_id: str | None  # for "ok" only

    def __post_init__(self) -> None:
        # ok+missing ist semantisch widersprüchlich: ein via Anchor sauber
        # extrahiertes Item kann nicht zugleich fehlen.
        assert not (self.extraction == "ok" and self.missing), (
            "SectionFlag: extraction='ok' schließt missing=True aus"
        )

@dataclass
class ParsedFiling:
    sections: dict[str, str]
    section_flags: dict[str, SectionFlag]
```

### Cache-Schema-Bump — entfällt

`filing_cache.py` cached den **rohen Filing-Text** (`filing.document_text`) + `filing_date`-Metadaten, **nicht** den Parser-Output. `parse_filing` läuft bei jedem Deep-Dive frisch gegen den (ggf. gecachten) Rohtext. Kein Cache-Eintrag ist von der SectionFlag-Schema-Änderung betroffen → kein Versions-Bump nötig. (Befund C, Plan-Phase Stage 2 — bestätigt am realen `filing_cache.py`-Code.)

### Tasks

- [ ] **Step 2.1: Write failing real-filing test for KO 10-K**

  ```python
  # tests/deepdive/test_filing_parser_real.py
  from app.deepdive.filing_parser import parse_filing

  def test_ko_10k_anchor_extraction():
      raw = (CACHE_DIR / "0000021344" / "0001628280-26-010047.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      parsed = parse_filing(raw, "10-K")
      flags = parsed.section_flags

      # All 5 SEC items extracted via anchor path
      for item in ("1", "1A", "7", "7A", "8"):
          key = f"10-K_item{item}"
          assert key in flags
          assert flags[key].extraction == "ok"

      # Item 8 is large enough to trigger truncation cap
      assert flags["10-K_item8"].truncated is True
      # Others are not truncated
      for item in ("1", "1A", "7", "7A"):
          assert flags[f"10-K_item{item}"].truncated is False

      # Bodies start with the expected ITEM heading
      pat = re.compile(
          r"^[\s\S]{0,300}?\bITEM\s+(\d+[A-Z]?)\b", re.IGNORECASE
      )
      for item in ("1", "1A", "7", "7A", "8"):
          body = parsed.sections[f"10-K_item{item}"]
          m = pat.match(body)
          assert m is not None, f"item {item} body does not start with ITEM heading"
          assert m.group(1).upper() == item.upper()

      # Item 1 body has substantial content (not a TOC fragment)
      assert len(parsed.sections["10-K_item1"]) > 5_000
  ```

  Run: `uv run python -m pytest tests/deepdive/test_filing_parser_real.py::test_ko_10k_anchor_extraction -v`
  Expected: FAIL (parse_filing still uses today's pattern-matching path)

- [ ] **Step 2.2: Modify parse_filing to attempt anchor-based extraction**

  ```python
  # app/deepdive/filing_parser.py
  from app.deepdive.anchor_resolver import resolve_anchors, AnchorMatch
  # ... existing imports ...

  def parse_filing(raw_document: str, form_type: str) -> ParsedFiling:
      items = _FORM_ITEMS[form_type]
      anchors = resolve_anchors(raw_document)
      expected = {i.upper() for i in items}
      hits = [a for a in anchors if a.item_label in expected]

      if hits:
          return _extract_via_anchors(raw_document, form_type, items, anchors, hits)
      return _extract_via_pattern_fallback(raw_document, form_type, items)


  def _extract_via_anchors(
      raw: str,
      form_type: str,
      items: list[str],
      all_anchors: list[AnchorMatch],
      hits: list[AnchorMatch],
  ) -> ParsedFiling:
      result = ParsedFiling()
      cap_chars = _section_token_cap() * _CHARS_PER_TOKEN
      hit_by_label = {h.item_label: h for h in hits}

      for item in items:
          key = f"{form_type}_item{item}"
          label = item.upper()
          if label not in hit_by_label:
              # Anchor-Pfad-Partial-Coverage: dieses expected item hat keinen
              # Anchor-Hit. Nur synthetic beobachtet (Partial-Coverage-Wildnis,
              # siehe "Honest-Label"-Abschnitt). Schema-erzwungen: einzige
              # non-ok-extraction ist "fallback_used" → "fallback_used+missing".
              result.section_flags[key] = SectionFlag(
                  extraction="fallback_used", missing=True,
                  truncated=False, anchor_id=None,
              )
              continue
          anchor = hit_by_label[label]
          # Find next anchor in doc order (any item, not just next expected item).
          # This implements N4-decision (a) Drop: intermediate items between
          # expected items terminate the previous body — they are not themselves
          # extracted into the synthesis prompt.
          # Background: docs/superpowers/plans/punkt-5-filing-parser.md (Plan-
          # Akzeptanz Punkt 5, N4-Begründung).
          next_anchor = next(
              (a for a in all_anchors if a.dom_position > anchor.dom_position),
              None,
          )
          html_slice = _slice_aligned(raw, anchor.anchor_id,
                                     next_anchor.anchor_id if next_anchor else None)
          body = _to_text(html_slice)
          truncated = False
          if len(body) > cap_chars:
              body = body[:cap_chars] + "\n" + _TRUNCATION_MARKER
              truncated = True
          result.sections[key] = body
          result.section_flags[key] = SectionFlag(
              extraction="ok", missing=False,
              truncated=truncated, anchor_id=anchor.anchor_id,
          )
      return result


  def _slice_aligned(raw: str, anchor_a: str, anchor_b: str | None) -> str:
      """Slice raw HTML between two anchor IDs, aligned to opening '<' of
      the containing tag. Critical: starting mid-tag emits literal id="..."
      in html2text output (empirically verified in diagnose-stage2-simulation)."""
      pa_id = raw.find(f'id="{anchor_a}"')
      if pa_id < 0:
          return ""
      tag_start = raw.rfind("<", max(0, pa_id - 200), pa_id)
      slice_start = tag_start if tag_start >= 0 else pa_id
      if anchor_b is None:
          return raw[slice_start:]
      pb_id = raw.find(f'id="{anchor_b}"')
      if pb_id < 0 or pb_id <= pa_id:
          return raw[slice_start:]
      tag_end = raw.rfind("<", max(0, pb_id - 200), pb_id)
      slice_end = tag_end if tag_end >= 0 else pb_id
      return raw[slice_start:slice_end]


  def _extract_via_pattern_fallback(
      raw: str, form_type: str, items: list[str],
  ) -> ParsedFiling:
      """Today's logic, unchanged (byte-identical bodies). Each flag carries
      extraction='fallback_used'; found sections missing=False (+truncated if
      capped), not-found sections missing=True ('fallback_used+missing')."""
      # ... move existing parse_filing body here, wrap flags in SectionFlag ...
  ```

  Run: `uv run python -m pytest tests/deepdive/test_filing_parser_real.py::test_ko_10k_anchor_extraction -v`
  Expected: PASS

- [ ] **Step 2.3: Add real-filing tests for GOOGL, NOVO, ASML**

  ```python
  def test_googl_10k_anchor_extraction():
      raw = ...
      parsed = parse_filing(raw, "10-K")
      flags = parsed.section_flags
      for item in ("1", "1A", "7", "7A", "8"):
          assert flags[f"10-K_item{item}"].extraction == "ok"
          assert flags[f"10-K_item{item}"].missing is False
      # GOOGL §8 is ~152K chars — NOT truncated
      assert flags["10-K_item8"].truncated is False
      # ... pattern checks ...

  def test_novo_20f_anchor_extraction():
      raw = ...
      parsed = parse_filing(raw, "20-F")
      flags = parsed.section_flags
      for item in ("4", "5", "18"):
          assert flags[f"20-F_item{item}"].extraction == "ok"
          assert flags[f"20-F_item{item}"].missing is False
          assert flags[f"20-F_item{item}"].truncated is False
      # NOVO §18 in Stage 2 is ~12K chars (vs today's 184K F2-tail-absorbed)

  def test_asml_20f_fallback_regress_guard():
      raw = ...
      parsed_new = parse_filing(raw, "20-F")
      # Stage 2: ASML falls into fallback path (0 anchor coverage)
      for item in ("4", "5"):
          flag = parsed_new.section_flags[f"20-F_item{item}"]
          assert flag.extraction == "fallback_used"
          assert flag.missing is True               # → renders "fallback_used+missing"
          assert f"20-F_item{item}" not in parsed_new.sections
      f18 = parsed_new.section_flags["20-F_item18"]
      assert f18.extraction == "fallback_used"
      assert f18.missing is False
      assert f18.truncated is True                  # → renders "fallback_used+truncated"
      # Body content is byte-identical to today's parser output (Regress-Schutz:
      # Stage 2 must not change ASML's behavior in the fallback path).
      # _legacy_parse_filing = frozen copy of the pre-Stage-2 parse_filing body,
      # preserved in the test file as reference.
      assert parsed_new.sections["20-F_item18"] == _legacy_parse_filing(raw, "20-F").sections["20-F_item18"]
  ```

  Run + Expected: 4/4 PASS

- [ ] **Step 2.4: Update synthetic spec-tests in test_filing_parser.py**

  Existing tests assume `section_flags: dict[str, str]`. Update to `dict[str, SectionFlag]`:

  ```python
  # OLD:
  assert parsed.section_flags == {}

  # NEW (Befund B): synthetic fixtures haben keine <a href="#…">-Anker → Fallback-Pfad.
  assert all(f.extraction == "fallback_used" for f in parsed.section_flags.values())
  ```

  Run + Expected: existing tests PASS

- [ ] **Step 2.5: Update dossier_generator frontmatter rendering**

  ```python
  # app/deepdive/dossier_generator.py
  def _flag_str(flag: SectionFlag) -> str:
      parts = [flag.extraction]
      if flag.missing:
          parts.append("missing")
      if flag.truncated:
          parts.append("truncated")
      return "+".join(parts)

  # When rendering YAML frontmatter:
  yaml_data = {
      ...
      "section_flags": {
          key: _flag_str(flag) for key, flag in record.section_flags.items()
      },
      ...
  }
  ```

  Add test:
  ```python
  def test_dossier_frontmatter_renders_composite_flag_string():
      flag = SectionFlag(extraction="ok", missing=False, truncated=True, anchor_id="x")
      assert _flag_str(flag) == "ok+truncated"
      flag2 = SectionFlag(extraction="fallback_used", missing=False, truncated=False, anchor_id=None)
      assert _flag_str(flag2) == "fallback_used"
      flag3 = SectionFlag(extraction="fallback_used", missing=True, truncated=False, anchor_id=None)
      assert _flag_str(flag3) == "fallback_used+missing"
  ```

  Run + Expected: PASS

- [x] **Step 2.6: entfällt — kein Cache-Bump nötig**

  `filing_cache.py` cached raw filing text, nicht Parser-Output. Parser läuft bei
  jedem Deep-Dive frisch gegen den (ggf. gecachten) Rohtext. Kein Cache-Eintrag ist
  von der Schema-Änderung betroffen. (Befund C, Plan-Phase Stage 2 — bestätigt am
  realen `filing_cache.py`-Code.)

- [ ] **Step 2.7: Run full test suite**

  Run: `uv run python -m pytest -v`
  Expected: alle Tests PASS, Coverage ≥ 96%

- [ ] **Step 2.8: Diagnose-Script (supplementär)**

  ```cmd
  uv run python scripts/diagnose_filing_parser.py
  ```

  Das Script bleibt **unangetastet** und druckt Kandidaten-Zählungen pro Item
  (keine SectionFlags) — supplementär für Operator-Intuition (ASMLs leere
  Kandidaten vs. saubere KO/GOOGL/NOVO). **Autoritative Flag-Verifikation erfolgt
  via `tests/deepdive/test_filing_parser_real.py` gegen die Verifikations-Tabelle**
  (Befund D, Plan-Phase Stage 2).

- [ ] **Step 2.9: Commit**

  ```cmd
  git checkout -b feature/punkt5-stage2-anchor-integration
  git add app/deepdive/filing_parser.py app/deepdive/dossier_generator.py app/models/deep_dive_record.py tests/deepdive/
  git commit -m "Integrate anchor-tracing parser with pattern-matching fallback"
  ```

### Verification Criterion (Cache-Diagnose, gratis, deterministic)

| Filing | section_flags Erwartung |
|---|---|
| KO 10-K | items 1, 1A, 7, 7A: `ok`; item 8: `ok+truncated` |
| GOOGL 10-K | items 1, 1A, 7, 7A, 8: alle `ok` |
| NOVO 20-F | items 4, 5, 18: alle `ok` |
| ASML 20-F | items 4, 5: `fallback_used+missing`; item 18: `fallback_used+truncated` (byte-identisch zu heute) |

### Dependency

Stage 1 in main.

### PROJEKTSTAND-Meilenstein

Ja.

### Aufwand

4 Tage.

---

## Stage 3 — F4-Validator-Härtung

### Files

- **Modify:** `app/deepdive/synthesis.py` (`_validate_sources`-Funktion)
- **Modify:** `tests/deepdive/test_synthesis.py` (oder ähnlicher Test-File, je nach existierender Struktur)

### Tasks

- [ ] **Step 3.1: Write failing test for body-pattern rejection**

  ```python
  def test_validate_sources_rejects_cite_when_body_lacks_item_heading():
      sources = ["[10-K §1]"]
      sent_keys = {"10-K_item1"}
      sections = {"10-K_item1": "some random text without item heading"}
      result = _validate_sources(sources, "10-K", sent_keys, sections)
      assert result == ["Inferenz"]

  def test_validate_sources_accepts_cite_when_body_has_item_heading():
      sources = ["[10-K §1]"]
      sent_keys = {"10-K_item1"}
      sections = {"10-K_item1": "ITEM 1. BUSINESS\n\nWe build search engines..."}
      result = _validate_sources(sources, "10-K", sent_keys, sections)
      assert result == ["[10-K §1]"]

  def test_validate_sources_accepts_cite_with_page_header_prefix():
      sources = ["[10-K §1A]"]
      sent_keys = {"10-K_item1A"}
      sections = {"10-K_item1A": (
          "* * *\n\n| | | | |   \n---|---|---|---|---|---  \n"
          "Table of Contents| Alphabet Inc.  \n  \n"
          "ITEM 1A.RISK FACTORS\n\nOur operations..."
      )}
      result = _validate_sources(sources, "10-K", sent_keys, sections)
      assert result == ["[10-K §1A]"]

  def test_validate_sources_accepts_novo_bare_number_style():
      sources = ["[20-F §4]"]
      sent_keys = {"20-F_item4"}
      sections = {"20-F_item4": "ITEM 4 INFORMATION ON THE COMPANY\n\nA. History..."}
      result = _validate_sources(sources, "20-F", sent_keys, sections)
      assert result == ["[20-F §4]"]

  def test_validate_sources_letter_suffix_item_not_truncated():
      # Anti-regress for the cite-regex fix: §7A must be captured as "7A",
      # not truncated to "7" (which would key the wrong section). Guards the
      # _SECTION_CITE_RE (\d+[A-Z]?) change below. Same risk class for §1A.
      sources = ["[10-K §7A]"]
      sent_keys = {"10-K_item7A"}
      sections = {"10-K_item7A": (
          "ITEM 7A. QUANTITATIVE AND QUALITATIVE DISCLOSURES\n\nWe are exposed..."
      )}
      result = _validate_sources(sources, "10-K", sent_keys, sections)
      assert result == ["[10-K §7A]"]
  ```

  Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -v -k "validate_sources"`
  Expected (RED): 5/5 neue Tests FAIL (Body-Pattern-Check + Cite-Regex-Fix
  noch nicht implementiert, neue 4-Arg-Signatur fehlt).

  Nach GREEN müssen zusätzlich die committeten Stage-2-Sub-Item-Tests grün
  BLEIBEN (`test_no_space_subitem_cite_not_collapsed_red_driver` +
  `test_multiple_no_space_subitems_not_collapsed`) — kein Regress auf den
  1.5.2-Wurzelfix. Die 8 bestehenden 3-Arg-Call-Sites in `test_synthesis.py`
  werden in Step 3.2 auf die neue 4-Arg-Signatur (mit realistischen
  ITEM-Bodies) aktualisiert.

- [ ] **Step 3.2: Implement body-pattern check**

  **Erst den Cite-Regex fixen** (Befund Stage-2-Akzeptanz): `_SECTION_CITE_RE`
  erfasst heute nur `(\d+)` und kürzt `§1A`/`§7A` still auf `"1"`/`"7"` → der
  Body-Heading-Check unten würde Suffix-Items gegen die falsche Section prüfen
  und die F4-Härtung für `1A`/`7A` aushebeln. Stage 2 extrahiert `§1A`/`§7A`
  jetzt zuverlässig via Anchor, daher live-relevant.

  **Achtung 10-K/20-F-Asymmetrie:** 10-K-Sub-Items (`§1A`/`§7A`) sind
  eigenständige SEC-Items und müssen Suffix-tragend bleiben. 20-F-Sub-Absätze
  (`§4B`/`§5C`) sind dagegen Unter-Teile eines Number-Items; der Parser
  emittiert nur das Parent (`item4`/`item5`). Eine uniforme `(\d+[A-Z]?)`-Regex
  **ohne Fallback** würde `§4B` auf `item4B` keyen → nicht vorhanden →
  fälschlich `["Inferenz"]` und damit den committeten 1.5.2-Wurzelfix
  (`test_no_space_subitem_cite_not_collapsed_red_driver` + Counterpart)
  zurückdrehen. Lösung: **Numeric-Fallback** — bei Key-Miss einmal auf den
  numerischen Stamm zurückfallen, bevor `["Inferenz"]`. Der Body-Heading-Check
  prüft dann gegen das Item-Label des *gefundenen* Keys (`ITEM 4`, nicht
  `ITEM 4B`).

  ```python
  # app/deepdive/synthesis.py
  # Befund Stage-2-Akzeptanz: (\d+) -> (\d+[A-Z]?), sonst werden 10-K §1A/§7A
  # auf "1"/"7" gekürzt und gegen die falsche Section validiert. 20-F-Sub-
  # Absätze (§4B/§5C) fangen wir mit dem Numeric-Fallback unten ab.
  _SECTION_CITE_RE = re.compile(r"(10-K|20-F)\s*§\s*(\d+[A-Z]?)", re.IGNORECASE)

  _BODY_HEADING_PAT = r"^[\s\S]{{0,300}}?\bITEM\s+{item}\b"

  def _validate_sources(
      sources: list[str],
      form_type: str,
      sent_keys: set[str],
      sections: dict[str, str],
  ) -> list[str]:
      for s in sources:
          m = _SECTION_CITE_RE.search(s)
          if not m:
              if "10-K" in s or "20-F" in s:
                  logger.warning(
                      "source %r looks like a filing cite but is not in the "
                      "'<form> §<item>' format — not validatable", s,
                  )
              continue
          # .upper() so a lowercase "§1a" still keys "10-K_item1A".
          item_full = m.group(2).upper()              # "1A" oder "4B"
          numeric_part = re.match(r"\d+", item_full).group(0)
          key_full = f"{form_type}_item{item_full}"
          key_numeric = f"{form_type}_item{numeric_part}"
          if key_full in sent_keys:
              # 10-K §1A/§7A: eigenständiges Item, Suffix bleibt erhalten.
              key, item_for_body_check = key_full, item_full
          elif key_numeric in sent_keys:
              # 20-F §4B/§5C: Sub-Absatz -> Fallback auf das Parent-Item.
              key, item_for_body_check = key_numeric, numeric_part
          else:
              return ["Inferenz"]
          # Body-content check: body must START with the heading of the
          # *resolved* key (ITEM 4 for a §4B-fallback, not ITEM 4B).
          body = sections.get(key, "")
          pat = re.compile(
              _BODY_HEADING_PAT.format(item=re.escape(item_for_body_check)),
              re.IGNORECASE,
          )
          if not pat.match(body):
              logger.warning(
                  "cite %s: body does not start with expected ITEM %s heading "
                  "within 300-char tolerance — downgraded to Inferenz",
                  s, item_for_body_check,
              )
              return ["Inferenz"]
      return sources
  ```

  Update `run_synthesis` call site to pass `sections=sections` to `_validate_sources`.

  Run: `uv run python -m pytest tests/deepdive/test_synthesis.py -v -k "validate_sources"`
  Expected: 5/5 PASS

- [ ] **Step 3.3: Add real-filing test using Stage-2 parser output**

  ```python
  def test_validate_sources_real_filing_ko_10k():
      raw = (CACHE_DIR / "0000021344" / "0001628280-26-010047.txt").read_text(
          encoding="utf-8", errors="replace"
      )
      parsed = parse_filing(raw, "10-K")
      # All Stage-2 KO bodies should pass the validator
      for item in ("1", "1A", "7", "7A", "8"):
          source = f"[10-K §{item}]"
          result = _validate_sources(
              [source], "10-K",
              set(parsed.sections.keys()), parsed.sections,
          )
          assert result == [source], (
              f"item {item} body should pass body-heading check"
          )
  ```

  Run + Expected: PASS

- [ ] **Step 3.4: Run full test suite**

  Run: `uv run python -m pytest -v`
  Expected: alle Tests PASS

- [ ] **Step 3.5: Commit**

  ```cmd
  git checkout -b feature/punkt5-stage3-validator-body-check
  git add app/deepdive/synthesis.py tests/deepdive/test_synthesis.py
  git commit -m "Tighten validator: cite body must start with expected ITEM heading"
  ```

### Verification Criterion

`uv run python -m pytest tests/deepdive/test_synthesis.py -v -k "validate_sources"`
zeigt 5/5 neue Body-Pattern-Tests PASS **und** 2/2 committete Stage-2-Sub-Item-Tests
(`test_no_space_subitem_cite_not_collapsed_red_driver` +
`test_multiple_no_space_subitems_not_collapsed`) weiterhin PASS (kein Regress).
Volle Suite grün, Coverage ≥ 96%.

### Dependency

Stage 2 in main.

### Aufwand

1,5 Tage.

---

## Stage 4 — ASML-Investigation + Honest-Label

### 4a — Read-only Investigation (Hard-Cap 2 Tage)

**Files erstellt (nicht committed):**
- `scripts/diagnose_asml_structure.py` (Read-only-Diagnose, scripts/-Verzeichnis)

**Investigation-Plan:**

Suche in ASMLs Cache-File nach strukturellen Markern für SEC-Item-4/5/18-Headings:

1. CSS-Klassen auf `<div>`/`<span>`: greppe nach `class="..."` mit semantisch-passenden Namen (`hdg`, `section`, `item-header`, `chapter`, etc.)
2. XBRL-Tags: `<ix:nonNumeric>`, `<ix:fraction>` mit `name="..."`-Attributen, die SEC-Item-Konzepte indizieren (z.B. `name="dei:DocumentType"`)
3. Inline-Styling: `style="font-weight:..."` mit ITEM-Text in der Nähe
4. HTML5-Heading-Tags: `<h1>`, `<h2>`, `<h3>` (selten in iXBRL, aber möglich)
5. Spezielle Strukturen: `<table>`-Headers, `<thead>`, semantically-typed `<aside>`

**Outcome-Definition:**

- *Marker gefunden (verifizierbar):* eindeutiges Pattern, mit dem mind. ein SEC-Item (4, 5, oder 18) lokalisierbar ist → fortfahren mit 4b
- *Mehrere Marker-Hypothesen, keine eindeutig:* → 4b nicht machbar in dieser Plan-Phase, honest technische Schuld
- *Kein verifizierbarer Marker innerhalb 2 Tagen:* → 4b nicht machbar, honest technische Schuld

**Output:** `docs/superpowers/diagnostic-reports/2026-XX-XX-asml-structure-investigation.md` (Anhang-Report, kein Commit ohne Freigabe).

### 4b — Conditional Implementation (nur falls 4a erfolgreich)

Falls 4a einen Marker gefunden hat:

- **Modify:** `app/deepdive/anchor_resolver.py` — erweitere `resolve_anchors()` um eine zweite Erkennungsstufe für den ASML-Marker
- **Modify:** `tests/deepdive/test_anchor_resolver.py` — neuer Real-Filing-Test, dass ASML jetzt mind. ein Item findet
- **Modify:** `tests/deepdive/test_filing_parser_real.py` — `test_asml_20f_fallback_regress_guard` muss umbenannt + angepasst werden (Erwartung: Item X jetzt `ok`)

### Verification Criterion

- 4a: Investigation-Report dokumentiert Outcome (Marker / kein Marker)
- 4b (falls implementiert): ASML's `section_flags` ändern sich von `fallback_used` zu `ok` für mind. ein Item

### Dependency

Stages 1+2 in main (für `anchor_resolver`-Erweiterung in 4b).

### Aufwand

2 Tage Hard-Cap (inkl. 4b falls erfolgreich; sonst nur 4a in 1 Tag).

---

## Stage 5 — Re-Verifikation + PROJEKTSTAND

### Tasks

- [ ] **Step 5.1: Authorized Tool-B re-runs**

  ```cmd
  uv run python -m app.deepdive deepdive GOOGL
  uv run python -m app.deepdive deepdive KO
  uv run python -m app.deepdive deepdive NOVO-B.CO
  uv run python -m app.deepdive deepdive ASML
  ```

  Each call: ~$0.50-2.00 Gemini Pro cost. 4 calls total.

  Output: `output/Watchlist/<TICKER>_<today's-date>.md` — neue Dossiers, alte (vom 2026-05-19/20) bleiben mit Original-Datum erhalten.

- [ ] **Step 5.2: Cite-Grounding-Vergleich**

  ```cmd
  uv run python scripts/diagnose_cite_grounding.py
  ```

  (Skript existiert aus E3-Diagnose-Phase; evtl. Anpassung der Dossier-Pfade auf neue Dateinamen.)

  Expected output per dossier:
  - GOOGL: alle §-Cites GROUNDED in der zitierten Section
  - KO: alle §-Cites GROUNDED
  - NOVO: alle §-Cites GROUNDED
  - ASML: gleiches Niveau wie vorher (Honest-Label)

- [ ] **Step 5.3: Side-by-side Vergleichs-Doc**

  Erstelle `docs/superpowers/diagnostic-reports/2026-XX-XX-punkt5-acceptance.md` mit:
  - **Pro Filing Header — explizite Version-Referenz** (siehe Q4-Präzisierung):

    ```markdown
    ## Vergleich: GOOGL

    - **alt**: output/Watchlist/GOOGL_2026-05-20.md (vor Punkt 5)
    - **neu**: output/Watchlist/GOOGL_2026-XX-XX.md (nach Stages 1-5)
    - **Cite-Grounding-Diff**: N/M von M §-Cites grounded
    ```
  - Pro Filing: alte vs neue §-Cite-Listen
  - Pro Filing: alte vs neue Body-Längen pro Section
  - Pro Filing: alte vs neue Synthesis-Token-Verbrauch (Gemini-Log-Output)
  - Pro Filing: ein-zwei Sätze qualitative Bewertung des neuen Dossiers
  - **Fisher-Punkte-Drop-Wirkung-Probe mit Quellen-Unterscheidung (Input für N4-Folge-Ticket):** Methodisch zweistufig pro Filing.

    *Schritt 1 — Themen-Inventar:* Aus dem alt-Dossier alle Reasoning-Sätze identifizieren, deren Substanz aus einem Intermediate-Item stammen könnte. Themen-Beispiele für 10-K-Filings (GOOGL, KO): Legal Proceedings (§3), Cybersecurity (§1C), Executive Compensation (§11), Insider-/Related-Party-Transactions (§13). Für 20-F-Filings (NOVO, ASML) entsprechende Themen, deren Material heute über die Last-Item-Tail-Absorption (§18 absorbiert §19/Signatures) in den Prompt rutscht.

    *Schritt 2 — Quellen-Match gegen Last-Item-Tail des alt-Bodies:* Für jeden so identifizierten Reasoning-Satz Grep-Probe gegen den alt-Last-Item-Tail (10-K: alt-§8-Body bis EOD-Cap; 20-F: alt-§18-Body bis EOD-Cap). Zwei mögliche Befunde:
      - **Material textuell im Tail vorhanden** → echte Drop-Wirkung. Stage 2 entzieht das Material, neuer Reasoning-Satz fehlt oder ist schwächer. Eintrag im Folge-Ticket „Intermediate-Items-Diagnose".
      - **Material nicht im Tail** → Modell-Außenwissen (F8-Kandidat-Klasse, vgl. GOOGL-P6-„Nvidia"). Kein Drop-Effekt, gehört in den F8-Backlog, nicht ins Intermediate-Items-Folge-Ticket.

    *Empfohlene Darstellungsform — Mini-Tabelle pro Filing:*

    | alt-Reasoning-Thema | Tail-Match? | Drop-Wirkung im neu-Dossier | Folge-Ticket-Input |
    |---|---|---|---|
    | z.B. Legal Proceedings re X | ja (§8-Body Zeile N) | Satz fehlt / schwächer | Intermediate-Items |
    | z.B. Cybersecurity incident Y | nein | unverändert / Modell-Außenwissen | F8-Backlog |

    Format empfohlen, formal aber nicht zwingend — die Quellen-Unterscheidung muss aber explizit erfolgen, sonst speist die Probe das Folge-Ticket mit gemischten Daten und ist schwer interpretierbar.

    Sichtbare Drop-Wirkungs-Verluste sind Plan-Iterations-Trigger (nicht Akzeptanz-Blocker). Praktische Umsetzung: das E3-Skript `scripts/diagnose_cite_grounding.py` ist strukturell ähnlich (prüft Cite-Substanz gegen Section-Body) und vermutlich adaptierbar; Entscheidung (Adaption vs neues Skript `scripts/diagnose_drop_wirkung.py`) liegt in der Stage-5-Arbeit, nicht in der Plan-Phase.

- [ ] **Step 5.4: PROJEKTSTAND-Update (Hochzusammenfassung)**

  Eintrag unter `## Erledigt`:
  ```markdown
  - 2026-XX-XX: **Punkt 5 — Filing-Parser-Anchor-Tracing** ✅ — F1, F2, F3, F4, F6
    gelöst via Anchor-Resolver-Modul + Parser-Integration + Validator-Härtung
    (5 Stufen, je eigene Branch, einzeln gemergt). ASML-Fall: F5/F7 als
    technische Schuld dokumentiert (siehe
    `docs/superpowers/diagnostic-reports/2026-XX-XX-punkt5-acceptance.md`).
    Re-Verifikations-Dossiers GOOGL/KO/NOVO/ASML ersetzen die alten als
    authoritative Tool-B-Referenz. 2a.1b-Verifikations-Basis dadurch
    rehabilitiert.
  ```

- [ ] **Step 5.5: Commit**

  ```cmd
  git checkout -b feature/punkt5-stage5-reverification
  git add docs/superpowers/diagnostic-reports/ output/Watchlist/ PROJEKTSTAND.md
  git commit -m "Punkt 5 acceptance: re-verify GOOGL/KO/NOVO/ASML dossiers"
  ```

### Verification Criterion

- 100% §-Cites grounded in GOOGL/KO/NOVO neue Dossiers
- ASML neue Dossier zeigt keinen Quality-Regress gegenüber altem Dossier

### Dependency

Stages 1-4 in main.

### PROJEKTSTAND-Meilenstein

Ja, finaler.

### Aufwand

1 Tag.

---

## Test-Strategie

### Validierungs-Basis — Real-Filing-Tests

Neuer Test-File `tests/deepdive/test_filing_parser_real.py` (Stage 2) + `tests/deepdive/test_anchor_resolver.py` (Stage 1) + erweiterte `tests/deepdive/test_synthesis.py` (Stage 3) arbeiten gegen die vier Cache-Filings.

Deterministisch, gratis, in CI ausführbar.

### Spec-Tests — synthetisch, bleiben erhalten

Bestehende `tests/deepdive/test_filing_parser.py` mit synthetic Inline-HTML-Tests bleiben drin, aber:
- Schema-Anpassung: `section_flags: dict[str, SectionFlag]` statt `dict[str, str]`
- Edge-Cases bleiben Spec-Definition für den Fallback-Pfad

Diese Tests prüfen den Fallback-Pfad (`_extract_via_pattern_fallback`), der byte-identisch zu heute ist. Sie sind Regress-Schutz für Filings ohne Anchor-Coverage.

### Coverage-Threshold

≥ 96% (aktueller Stand 96,40%). Stage 1 hebt vermutlich um 1-2 Prozentpunkte.

---

## Re-Verifikations-Schritt — Akzeptanz-Probe

Siehe Stage 5. Vier Tool-B-Läufe + Cite-Grounding-Vergleich + Vergleichs-Doc + PROJEKTSTAND-Update.

Akzeptanz: 100% §-Cites grounded in 3/4 Dossiers, ASML kein Regress. Falls eines davon scheitert: Stop, Befund melden, Plan-Iteration.

---

## Offene Design-Punkte (Plan-Akzeptanz vorbedingt)

### N4 — Intermediate Items Handling — entschieden: (a) Drop

Stage-2-Default-Annahme bestätigt: Item-1A-Body läuft bis zum nächsten Anchor in Dokument-Reihenfolge (Item-1B-Anchor), nicht bis zum nächsten expected item (Item-7-Anchor). Items 1B-6, 9-16 sind nicht im Synthesis-Prompt.

Begründung: cleanste Cite-Provenance — jedes Cite zeigt nur auf seine tatsächliche Section, kein mis-labeling. Minimiert das Risiko, dass die Anchor-Tracing-Korrektheit durch zusätzliche Slicing-Komplexität kompromittiert wird. Option (b) würde F4-Pathologie in subtilerer Form restaurieren (echtes Material, falsches Cite-Mapping); (c)/(d) sind möglicherweise sinnvolle Folge-Initiativen, aber nicht Teil von Punkt 5.

Folge-Ticket („Intermediate-Items-Diagnose") siehe Abschnitt **Honest-Label / Technische Schuld nach Plan**.

### Q2 — Logging-Level bei Fallback — bestätigt: WARNING

Konsistent mit heutigen `missing`/`ambiguous`-WARNINGs. Format-Vorgabe für Stage 2:

```
WARNING filing parser: no SEC-item anchor-links found for <FORM> (CIK <cik>); falling back to pattern-matching for items <list>
```

So bleibt für den Operator sichtbar, welcher Pfad genommen wurde und für welche Items — ohne dass die Meldung wie ein Crash aussieht.

**Implementierungs-Notiz (Stage 2):** Realisiert **ohne `(CIK <cik>)`** — `parse_filing(raw_document, form_type)` hat auf Parser-Ebene keine CIK; der Deep-Dive-Kontext (Ticker) wird von `pipeline`/Gemini-Client ohnehin vorher geloggt. CIK-Threading wäre eine Signatur-Ausweitung ohne substantiellen Mehrwert; falls später gewünscht, sauberer Weg ist ein Logging-Adapter mit Pipeline-Context, nicht die Parser-Signatur.

### Q3 — Synthesis-System-Prompt unverändert — bestätigt

Unter Option (a) bleibt das Set stabil: 10-K {1, 1A, 7, 7A, 8}, 20-F {4, 5, 18}. System-Prompt-Anpassung nicht nötig.

**Präzisierung für Stage 5**: Section-Bodies werden nach Stufe 2 erheblich größer (KO §7 MD&A von 98 auf 50-80K Zchn). Der Charakter des Synthesis-Inputs verändert sich substantiell — nicht der Prompt, aber der Material-Reichtum. Modellverhalten kann sich qualitativ verschieben. Stage-5-Vergleichs-Doc dokumentiert das explizit (Tiefe/Spezifität der Reasoning-Sätze, ob das Modell die zusätzliche Substanz produktiv nutzt, Cite-Verteilung über §-Sections). Falls neue Dossiers qualitativ schlechter sind: Plan-Iterations-Trigger, nicht Akzeptanz-Blocker.

### Q4 — Dossier-Filename bei Re-Verifikation — bestätigt

Neue Dossiers mit aktuellem Datum (`output/Watchlist/<TICKER>_<today's-date>.md`), alte bleiben mit Original-Datum (2026-05-19/20). Audit-Trail-Disziplin.

**Präzisierung für Stage 5**: Vergleichs-Doc-Header pro Filing nennt explizit alt-Datum + neu-Datum — siehe Stage 5 Step 5.3.

---

## Aufwandszusammenfassung

| Stufe | Aufwand | Hard-Cap? |
|---|---|---|
| Stufe 1 — Anchor-Resolver | 2 Tage | nein |
| Stufe 2 — Parser-Integration | 4 Tage | nein |
| Stufe 3 — Validator-Härtung | 1,5 Tage | nein |
| Stufe 4 — ASML-Investigation | 2 Tage | **ja** (Hard-Cap; siehe 4a) |
| Stufe 5 — Re-Verifikation | 1 Tag | nein |
| **Summe** | **10,5 Tage = ~2 Arbeitswochen** | |

---

## Honest-Label / Technische Schuld nach Plan

- **F5+F7 konditional als technische Schuld:** falls Stage 4a keinen verifizierbaren ASML-Marker findet, bleiben ASMLs SEC-Items 4/5 als `fallback_used+missing`. Auswirkung auf ASML-Dossier: gleich wie heute (qualitativ nicht-überzeugend, aber kein Regress). Behebung erfordert eigene Initiative mit anderem Lösungsansatz (z.B. LLM-basierter Section-Locator, Bundesanzeiger-Source-Layer).
- **F8-Kandidat (Modell-Halluzination unter validem Cite-Label):** bewusst out-of-scope. Wäre eigene Initiative mit Cross-Reference-Validator (LLM-basiert oder Term-Frequency-basiert).
- **Intermediate-Items-Diagnose-Folge-Ticket:** Stage 2 implementiert N4-Option (a) Drop — items zwischen den expected items werden weder im Body extrahiert noch im Synthesis-Prompt mitgegeben. Beispiel-Verluste in 10-K-Filings: Item 3 (Legal Proceedings), Item 1C (Cybersecurity), Item 11 (Executive Compensation), Item 13 (Related Party Transactions) — alle für Fisher-relevante Reasoning-Pfade potenziell wichtig. Stage 5 Step 5.3 probiert die Wirkung empirisch. Wenn dort Qualitätsverlust sichtbar wird, eigene Plan-Phase mit Optionen (d) Gezielte Erweiterung oder (c) Expand. Nicht jetzt mit-detailliert, eigene Initiative wenn so weit.
- **Partial-Coverage-Wildnis-Annahme:** in den 4 Cache-Filings nicht beobachtet. Stage-2-Code-Pfad existiert, ist aber nur synthetic-getestet. Folge-Ticket falls in der Wildnis sichtbar.
