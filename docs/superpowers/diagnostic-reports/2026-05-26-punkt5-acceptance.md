---
title: Punkt 5 — Stage 5 Re-Verifikation / Akzeptanz
status: abgeschlossen
created: 2026-05-26
plan: docs/superpowers/plans/punkt-5-filing-parser.md (Stage 5)
scope: Tool-B-Akzeptanz — keine Code-Änderung
---

# Punkt 5 — Stage-5-Akzeptanz: GOOGL / KO / NOVO / ASML Re-Verifikation

Vier Tool-B-Deep-Dives gegen die realen Cache-Filings, erzeugt mit dem
Stage-1/2/3-Stand in `main` (Anchor-Resolver + Parser-Integration +
Validator-Härtung). Vergleich gegen die F4-defekten Alt-Dossiers (2026-05-19/20).

**Läufe:** sequentiell, `uv run python -m app.deepdive deepdive <TICKER> --peers ...`.
Peer-Trios der Alt-Dossiers wiederverwendet (GOOGL META/MSFT/AMZN, NOVO LLY/PFE/MRK,
ASML AMAT/KLAC/LRCX); KO neu (PEP/KDP/MNST), da kein Alt-Dossier existiert.

> **Working-Tree-Voraussetzung:** KO besitzt keinen committeten ADR-Eintrag
> (US-Passthrough = Phase B.2). Für den Lauf wurde eine KO-Self-Reference
> (`cik 0000021344`, `10-K`) in `data/adr_table.json` ergänzt — gleiche
> dokumentierte Schuld-Klasse wie GOOGL/ASML, **nicht committet**.

---

## 1. Akzeptanz-Gate (hart)

Skript: `scripts/diagnose_cite_grounding_dossier.py` — extrahiert jeden
`[10-K §N]`/`[20-F §N]`-Cite (inkl. 20-F-Sub-Absatz-Form `§5 D`) aus dem Dossier
und füttert ihn durch den **echten Produktions-Validator** `_validate_sources`
gegen die frisch re-geparsten Sektionen (deterministisch = identisch zu dem, was
an Gemini ging).

| Dossier neu | §-Cites grounded | Verdikt |
|---|---|---|
| GOOGL | 22 / 22 (100%) | **PASS** |
| KO | 17 / 17 (100%) | **PASS** |
| NOVO | 18 / 18 (100%) | **PASS** |
| ASML | 1 / 1 (100%) | **NO REGRESS** (alt: 1/1) |

→ **Gate erfüllt.** Kein §-Cite zeigt auf eine fehlende oder falsch-betitelte
Section; kein Stage-3-Defekt durchgerutscht.

### Was dieser Check misst — und was nicht (Ehrlichkeits-Nuance)

Der Check ist **strukturelles Grounding (Interpretation A):** jeder §-Cite zeigt
auf eine vorhandene, korrekt mit `ITEM N` beginnende Section. Er prüft **nicht**
die Body-Substanz (ob die konkrete Aussage im Body steht — das ist F8, bewusst
out-of-scope). Da er den Produktions-Validator nutzt, ist „100%" bei den neuen
Dossiers teils konstruktionsbedingt — er fängt aber genau das ab, wofür das Gate
da ist (ein gerenderter Cite, der den Validator hätte passieren dürfen).

Wichtig: der Heading-basierte Check kann ein **fast leeres TOC-Fragment** nicht
von einem vollen Body unterscheiden (ein 20-Zeichen-`"ITEM 1. BUSINESS"` matcht
das Heading-Pattern). Der eigentliche F1/F2-Beweis steht daher in den
**Body-Längen-Tabellen** unten, nicht im Grounding-Prozent. Konsequenz: die
„100% grounded"-Zeile der **Alt**-Dossiers (gegen den heutigen Parser geprüft)
ist illustrativ, nicht aussagekräftig über den damaligen Zustand.

---

## 2. Vergleich: GOOGL

- **alt**: `output/Watchlist/GOOGL_2026-05-20.md` (vor Punkt 5)
- **neu**: `output/Watchlist/GOOGL_2026-05-26.md` (nach Stages 1–5)
- **Cite-Grounding (neu)**: 22/22 §-Cites grounded (100%)

### §-Cite-Listen

| | §-Cites | [Inferenz] |
|---|---|---|
| alt | §1×5, §1A×5, §7×4 (14) | 5 |
| neu | §1×8, §1A×8, §7×5, **§8×1** (22) | 3 |

### Body-Längen pro Section (Zeichen)

| Section | legacy-Parser | Anchor-Parser | Flag (neu) |
|---|--:|--:|---|
| §1 | 20 | 24.149 | ok |
| §1A | 367 | 86.296 | ok |
| §7 | 98 | 55.626 | ok |
| §7A | 72 | 8.487 | ok |
| §8 | 200.041 (capped) | 152.304 | ok |
| **Σ gesendet** | **200.598** | **326.862** | |
| ~Input-Tokens (chars/4) | ~50.149 | ~81.715 | |

### Qualitative Bewertung

Der Legacy-Parser lieferte für §1/§1A/§7/§7A faktisch **leere Fragmente**
(zusammen 557 Zeichen); das gesamte Substanz-Material steckte im
tail-absorbierten §8-Blob (200K, capped, absorbierte §9–§16). Die alten
`[§1]`/`[§7]`-Cites waren also Heading-grounded, aber substanziell mislabeled
(F4). Das neue Dossier zitiert dieselben Items gegen **echte** Bodies (§1A
86K, §7 56K) und zieht erstmals §8 sauber als eigenständige Quelle hinzu
(P10 Segment-/Kostenanalyse) — Inferenz-Anteil sinkt 5→3.

### Drop-Wirkung-Probe (Input für Folge-Tickets)

| alt-Reasoning-Thema | Quelle | Verdikt | Folge-Ticket |
|---|---|---|---|
| Antitrust/Legal (P11/P15) | im neu-Prompt (§1A/§7) | verfügbar — kein Drop | — |
| Dual-class governance (P8) | im neu-Prompt (`Class B`) | verfügbar — kein Drop | — |
| **Executive Compensation (§11)** | nur im legacy-§8-Tail | **echter DROP** | Intermediate-Items |
| Related-Party (§13) | in keinem Prompt | Modell-Außenwissen | F8-Backlog |

→ Ein konkreter Intermediate-Item-Verlust (§11 Exec-Comp): unter N4-Drop
liefert der saubere §8-Schnitt dem Modell kein Exec-Comp-Material mehr, das der
alte §8-Blob via Tail-Absorption noch enthielt. Kein Akzeptanz-Blocker — Input
fürs Folge-Ticket.

---

## 3. KO (kein Alt-Dossier)

- **neu**: `output/Watchlist/KO_2026-05-26.md` — KO wurde vor Punkt 5 nie
  deep-gedived, daher **kein alt** und kein Diff. Reine Neu-Verifikation.
- **Cite-Grounding (neu)**: 17/17 §-Cites grounded (100%)

### §-Cites / Body-Längen

| | §-Cites | [Inferenz] |
|---|---|---|
| neu | §1×7, §1A×5, §7×5 (17) | 5 |

| Section | legacy-Parser | Anchor-Parser | Flag (neu) |
|---|--:|--:|---|
| §1 | 20 | 55.482 | ok |
| §1A | 415 | 92.590 | ok |
| §7 | 98 | 112.225 | ok |
| §7A | 72 | 6.063 | ok |
| §8 | 200.041 (capped) | 200.041 | ok+truncated |
| **Σ gesendet** | **200.646** | **466.401** | |
| ~Input-Tokens (chars/4) | ~50.161 | ~116.600 | |

### Qualitative Bewertung

Dieselbe F1-Pathologie wie GOOGL, noch deutlicher: §7 (MD&A) wäre unter dem
Legacy-Parser 98 Zeichen gewesen, mit Anchor 112K. Das neue KO-Dossier ist die
erste substanzielle Tool-B-Referenz für Coca-Cola. ~116K Input-Tokens —
innerhalb des 200K-Caps (bestätigt die Token-Budget-Annahme des Plans).
Keine Drop-Wirkung-Probe (kein Alt-Dossier als Bezug).

---

## 4. Vergleich: NOVO

- **alt**: `output/Watchlist/NOVO-B.CO_2026-05-19.md` (vor Punkt 5)
- **neu**: `output/Watchlist/NOVO-B.CO_2026-05-26.md` (nach Stages 1–5)
- **Cite-Grounding (neu)**: 18/18 §-Cites grounded (100%)

### §-Cite-Listen

| | §-Cites | [Inferenz] |
|---|---|---|
| alt | §4×7, §5×4 (11) | 10 |
| neu | §4×6, §4B×3, §4D×3, §5B×1, §5C×2, §5D×2, §18×1 (18) | 5 |

### Body-Längen pro Section (Zeichen)

| Section | legacy-Parser | Anchor-Parser | Flag (neu) |
|---|--:|--:|---|
| §4 | 78 | 34.378 | ok |
| §5 | 1.279 | 23.442 | ok |
| §18 | **184.113** | **11.704** | ok |
| **Σ gesendet** | **185.470** | **69.524** | |
| ~Input-Tokens (chars/4) | ~46.367 | ~17.381 | |

### Qualitative Bewertung

Das klarste F2-Beispiel: legacy-§18 = **184K** (absorbierte §18 + §19 +
Signatures), Anchor-§18 = **11,7K** (sauber begrenzt — exakt die Plan-Vorhersage
„~12K"). Das alte Dossier zitierte §4 (78 Zeichen!) und §5 (1,3K) — fast leere
Bodies; das Material kam aus dem §18-Blob (F4). Das neue Dossier hat echte
§4/§5-Bodies (34K/23K) und zitiert erstmals auf **Sub-Absatz-Ebene**
(§4B/§4D/§5B/§5C/§5D — 11 der 18 Cites), plus §18 gezielt fürs „Critical Audit
Matter" (P10). Inferenz-Anteil sinkt 10→5. Der neue Prompt ist **kleiner**
(17K statt 46K Tokens), aber sauber attribuiert statt eines mislabeled
Riesen-Blobs — der substanzielle Punkt-5-Gewinn.

### Drop-Wirkung-Probe

| alt-Reasoning-Thema | Quelle | Verdikt | Folge-Ticket |
|---|---|---|---|
| Iran-Disclosure (P15) | im neu-Prompt | verfügbar — kein Drop | — |
| Critical Audit Matter (P10) | im neu-Prompt (§18) | verfügbar — kein Drop | — |
| Board/CEO-Turnover (P8/P9) | im neu-Prompt | verfügbar — kein Drop | — |
| Layoffs ~9.000 (P7) | im neu-Prompt | verfügbar — kein Drop | — |

→ Keine sichtbaren Intermediate-Item-Verluste für NOVO in den geprüften Themen
(alle Substanz liegt in §4/§5/§18, die alle gesendet werden).

---

## 5. Vergleich: ASML — *honester, nicht besser*

- **alt**: `output/Watchlist/ASML_2026-05-20.md` (vor Punkt 5)
- **neu**: `output/Watchlist/ASML_2026-05-26.md` (nach Stages 1–5)
- **Cite-Grounding (neu)**: 1/1 §-Cites grounded — **kein Regress** (alt: 1/1)

### §-Cite-Listen

| | §-Cites | [Inferenz] |
|---|---|---|
| alt | §18×1 (1) | 13 |
| neu | §18×1 (1) | **14** |

### Body-Längen pro Section (Zeichen)

| Section | legacy-Parser | Anchor-Parser | Flag (neu) |
|---|--:|--:|---|
| §4 | 0 | 0 | fallback_used+missing |
| §5 | 0 | 0 | fallback_used+missing |
| §18 | 200.041 | 200.041 | fallback_used+truncated |

### Einordnung (kritisch fürs Review)

ASML hat **0 SEC-Item-Anchor-Links** → Anchor-Resolver findet keine Sections →
Fallback-Pfad. §4/§5 sind `fallback_used+missing` (nicht im Prompt), §18 ist
der unveränderte 200K-Fallback-Blob — **byte-identisch alt/neu** (Regress-Schutz
greift). Die §4/§5-Cites von Gemini collapsen korrekt auf [Inferenz], weil das
Material nicht im Prompt ist; der Stage-3-Validator ist strenger → **14 statt 13**
[Inferenz].

Das neue ASML-Dossier ist also **nicht qualitativ besser** — es ist
**ehrlicher**: ein Inferenz-Downgrade mehr, weil ein Cite, den der alte
F4-blinde Validator durchließ, jetzt korrekt als nicht-grounded markiert wird.
Das **bestätigt das Stage-4-Honest-Label** (F5/F7 als technische Schuld), statt
es zu widerlegen. Wer ASML hier als „Stage-5-Versagen" liest, verkennt: genau
dieses Verhalten war vorhergesagt und ist die korrekte Behandlung.

### Drop-Wirkung-Probe

Nicht anwendbar im üblichen Sinn: §18 ist alt wie neu der gleiche 200K-Blob,
§4/§5 fehlen in beiden. Die geprüften Themen (Mistral, High-NA, 1.700-Stellen,
Zeiss, EUV) erscheinen zwar als Strings im §18-Blob, das alte Dossier labelte
die zugehörigen Aussagen aber überwiegend als [Inferenz] — d.h. Modell-Außenwissen
/ unstrukturierter Blob, kein sauber zitierbares Section-Material. Kein Drop
gegenüber alt. → EU-Native-Source-Layer (eigene Initiative) bleibt der einzige
echte Hebel für ASML-Typ-Filings.

---

## 6. Folge-Ticket-Input (Backlog, nicht Stage 5)

| Ticket | Input aus dieser Probe |
|---|---|
| **Intermediate-Items-Diagnose** | GOOGL §11 Executive Compensation = bestätigter Tail-Drop. NOVO: keine Verluste in geprüften Themen. Empfehlung: vor 2a.2/2a.3 evaluieren, Umfang gering. |
| **F8-Cross-Reference-Validator** | GOOGL §13 Related-Party = Modell-Außenwissen unter Reasoning. Eigene Initiative. |
| **EU-Native-Source-Layer** | ASML bleibt fallback-only; einziger struktureller Hebel für §4/§5-Substanz. |

---

## 7. Methodik / Caveats

- **Skripte (untracked):** `scripts/diagnose_cite_grounding_dossier.py`
  (Grounding-Gate, nutzt Produktions-`_validate_sources`),
  `scripts/diagnose_drop_wirkung.py` (Body-Längen via eingefrorenem
  `_legacy_parse_filing` + 3-stufige Themen-Klassifikation).
- **Token-Verbrauch:** Die Läufe loggten Token nicht auf stdout (nur
  WARNING-Level). Die `~Input-Tokens`-Spalten sind **Schätzungen** (chars/4 via
  `_CHARS_PER_TOKEN`), kein exakter Gemini-`usage_metadata`-Wert. Exakte
  Log-Tokens hätten einen bezahlten Re-Run mit INFO-Logging erfordert — für die
  Akzeptanz nicht gerechtfertigt. Alle vier Prompts lagen unter dem
  200K-deepdive-Token-Cap (sonst hätte `run_synthesis` mit GeminiError
  abgebrochen; alle vier schrieben Dossiers).
- **Grounding gegen heutigen Parser:** Alt-Dossier-Grounding-Prozente sind gegen
  den aktuellen Parser geprüft (nicht den damaligen) und daher illustrativ; der
  Substanz-Vergleich steht in den Body-Längen-Tabellen.
- **Audit-Trail:** Alte Dossiers (2026-05-19/20) bleiben mit Original-Datum
  erhalten; die neuen (2026-05-26) treten als autoritative Tool-B-Referenz daneben.
