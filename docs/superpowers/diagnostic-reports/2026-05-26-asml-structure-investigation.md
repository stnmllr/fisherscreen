---
title: ASML 20-F — Structural-Marker-Investigation (Punkt 5, Stage 4a)
date: 2026-05-26
stage: Punkt 5 / Stage 4a (read-only Investigation)
status: abgeschlossen — Gate-Ergebnis NEGATIV (kein verifizierbarer Marker)
committed: nein (Anhang-Report; Commit nur nach Freigabe)
scripts:
  - scripts/diagnose_asml_structure.py (read-only, untracked)
  - scripts/diagnose_asml_xref.py (read-only, untracked)
  - scripts/diagnose_asml_xref2.py (read-only, untracked)
filing: cache/filings/0000937966/0001628280-26-011378.txt (ASML 20-F, FY2025, 24,9 MB iXBRL)
control: cache/filings/0000353278/0000353278-26-000012.txt (NOVO 20-F — funktionierende Kontrolle)
---

# ASML 20-F — Structural-Marker-Investigation (Stage 4a)

## Frage

Unter dem Stage-1-Anchor-Resolver (`app/deepdive/anchor_resolver.py`) haben ASMLs
SEC-Items 4/5/18 **0 Anchor-Coverage**. Stage-4a-Frage: Existiert **irgendein anderer
struktureller Marker**, mit dem sich der Beginn von SEC-Item 4, 5 oder 18 **eindeutig**
(verifizierbar, nicht mehrdeutig) lokalisieren lässt?

Outcome-Definition laut Plan: Marker eindeutig → 4b; mehrere Hypothesen ohne eindeutige
ODER kein Marker → 4b entfällt, honest technische Schuld.

## Methode

Drei read-only Probe-Scripts gegen das gecachte ASML-iXBRL (24,9 MB), `lxml-xml`-Parser
(identisch zur Produktion), NOVO 20-F als funktionierende Kontrolle. Anchor-Baseline über
den **Produktiv-Code** `resolve_anchors()` reproduziert. Kein Produktiv-Code geändert.

## Hypothesen-Ergebnisse

| # | Hypothese | Evidenz ASML | NOVO (Kontrolle) | Verdikt |
|---|---|---|---|---|
| H0 | TOC-Anchor-Link → Ziel-Text startet mit „ITEM N" | **0** Anchor-Matches gesamt (von `resolve_anchors`) | 33 Matches, Items 4/5/18 alle covered | ✗ |
| HX | Form-20-F-Cross-Reference-Tabelle mit Anchors | Tabelle **existiert** („4 Information on the Company", „5 …"), aber **0 `<a href>` in Zeile/Tabelle** | (n/a — NOVO nutzt anchored TOC) | ✗ |
| H1 | Heading-CSS-Klasse auf Carrier-Element | **0** distinct `class`-Werte (iXBRL nutzt Inline-Style) | ebenfalls 0 | ✗ |
| H2 | XBRL-Tag (`ix:nonNumeric`) markiert Section | 2518 ix-Tags, 748 Konzepte (220 `asml:`), **0** section/item-Konzepte | — | ✗ |
| H3 | Inline-Style (font-weight/size) als Marker | nur AGM-Agenda-Artefakte, nicht spezifisch | — | ✗ |
| H4 | HTML5-Heading `<h1>..<h6>` | **0** | 0 | ✗ |
| H5 | Tabellen-/`<thead>`-Struktur | einzige Multi-Item-Tabelle = AGM-Agenda (0 Anchors) | — | ✗ |
| C | SEC-Item-Titel als anchored Heading | „Information on the Company"/„Operating and Financial Review" je 1×, **0/1 anchored** | — | ✗ |

## Der entscheidende Befund: „Item 4/5/18" ist bei ASML etwas anderes

ASMLs Dokument enthält **keine** „ITEM 4/5/18"-Headings im SEC-Sinn. Die wenigen
Text-Knoten, die mit „Item 4"/„Item 5" beginnen, sind **AGM-Tagesordnungspunkte**
(„Item 1 Discussion of the Management Report… Item 2 Discussion of the dividend…") —
Hauptversammlung, nicht Form 20-F.

ASML hat reiche Anchor-Navigation (**3323** interne Links, **176** auflösbare Ziele) —
aber die Link-Texte sind durchweg ASMLs **eigene redaktionelle Kapitel** („STRATEGIC
REPORT", „CORPORATE GOVERNANCE", „Our business", „Risk", …) plus bloße **Seitenzahlen**.
Kein einziger Anchor zeigt auf einen SEC-Item.

Es **gibt** eine „Form 20-F cross reference table" (25× „form 20-f"; explizit „Reference
is made to the Form 20-F cross reference table above"). Sie listet die SEC-Items mit
führender Nummer + Titel (Zeile: `4 Information on the Company`, `5 Operating and
Financial Review and Prospects`). **Aber:** die Tabelle trägt **0 `<a href>`** — weder
auf den Zeilen noch auf Seitenzahlen. Sie ist eine reine Druckseiten-Referenz, im
DOM nicht verfolgbar.

## Gate-Entscheidung

**NEGATIV — kein verifizierbarer, eindeutiger struktureller Marker. → 4b entfällt.**

ASMLs SEC-Items sind nur durch **semantisches Urteil** lokalisierbar (Wissen, dass ASMLs
Kapitel „Our business" ≈ SEC-Item 4 ist usw.) — es existiert kein struktureller Anker,
keine Klasse, kein XBRL-Konzept, kein anchored Cross-Ref-Eintrag. Die Cross-Ref-Tabelle
— der einzige Kandidat, der SEC-Items überhaupt benennt — mappt auf **Seitenzahlen ohne
Hyperlink** und ist damit für DOM-Anchor-Tracing unbrauchbar.

Bewusst festgehalten (gegen den „Marker-erfinden"-Failure-Mode): Die Cross-Ref-Tabelle
wurde **gefunden und direkt geprüft** (`diagnose_asml_xref2.py`) — sie ist nicht
übersehen, sondern verifiziert unbrauchbar. „Nichts Verfolgbares gefunden, hier ist
warum" ist hier das vollständige, valide Investigation-Outcome.

## Honest-Label-Konsequenz

- ASMLs SEC-Items **4 und 5** bleiben `fallback_used + missing`, **18** bleibt
  `fallback_used + truncated` — **byte-identisch zu heute**, kein Regress.
- F5 (Section-Headings ohne ITEM-Präfix) + F7 (Cover-Page-Checkbox als Anker) bleiben
  als **dokumentierte technische Schuld** offen.
- ASML-Dossier-Qualität für §4/§5/§18 = wie bisher (qualitativ nicht-überzeugend, aber
  unverändert).

## Was eine echte Behebung erfordern würde (außerhalb 4b/dieser Plan-Phase)

Anchor-Tracing kann ASML strukturell nicht lösen. Ein künftiger eigener Ansatz müsste
**semantisch** arbeiten, z.B.:

1. **LLM-basierter Section-Locator** — Cross-Ref-Tabelle + ASML-Kapitel-Titel an ein
   LLM geben, das SEC-Item → Kapitel-Anchor mappt (Tool B darf Gemini Pro nutzen).
2. **Seitenzahl→DOM-Position-Mapping** — die Cross-Ref-Seitenzahlen über die iXBRL-
   `top:`/CSS-Position-Hinweise auf DOM-Offsets abbilden (fragil, Workiva-spezifisch).

Beides ist eine eigene Initiative mit anderem Lösungsansatz, kein „zweiter
Erkennungs-Layer in `resolve_anchors()`".
