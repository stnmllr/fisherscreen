# Phase 1.6 — Akzeptanz-Gate: Drei reale Watchlist-Deep-Dives

**Datum:** 2026-06-18
**Stand Repo:** `main` @ `332eadc` (B-Fast US-Pfad #42 + EU-ADR-Pfad #43 gemergt; 1065 Tests / 97,2 %)
**Erfolgskriterium (Plan §1.6.3):** Drei reale Deep-Dives, mind. 1 US-Filer + 1 20-F-Filer.
Pro Dossier Urteil: „substanzielle Entscheidungsgrundlage für Pass-oder-Vertiefen?" — für **≥2 von 3**
zustimmungsfähig → Phase 1 erfolgreich.

> **Verdikt-Status:** Dieses Memo dokumentiert die Lauf-Evidenz und die Mechanik-Verifikation.
> Das Pass-Urteil pro Dossier ist **Stephans** (Kriterium 3). Meine Einschätzung ist als
> *Empfehlung* markiert, nicht als Entscheidung.

---

## Slate & Peers (bezahlter Lauf, 3×)

| Slot | Ticker | Pfad | Peers | Peer-Rationale |
|---|---|---|---|---|
| US-Filer (voller Stack) | FICO | US dynamisch (`get_cik`) | VRSK, SPGI, MCO | Daten-/Analytics-Moat mit Pricing-Power |
| 20-F-Filer | ASML.AS | EU-ADR → OpenFIGI → 20-F | AMAT, LRCX, KLAC | Semicap-Equipment-Peers |
| 20-F-Filer | NOVO-B.CO | EU-ADR → OpenFIGI → 20-F | LLY, SNY, AZN | Pharma / GLP-1 & Metabolik |

Vorgehen: FICO als Kanari zuerst (neuer dynamischer US-Pfad = höchstes Risiko), nach sauberem
Durchlauf ASML.AS + NOVO-B.CO parallel. Alle drei `exit 0`.

---

## Mechanik-Verifikation (was B-Fast gebaut hat, einmal echt durchlaufen)

| Mechanismus | FICO | ASML.AS | NOVO-B.CO |
|---|---|---|---|
| CIK-Resolution | dyn. `get_cik` → `0000814547` ✓ | OpenFIGI ADR `ASML` → `0000937966` ✓ | OpenFIGI ADR `NVO` → `0000353278` ✓ |
| Annual-Form-Detektion | `10-K` ✓ | `20-F` ✓ | `20-F` ✓ |
| Insider (Form 4) | 48 Filings, 127 signifikant (0 Käufe) ✓ | `fpi_exempt` (Section-16-befreit) ✓ ehrlich gelabelt | `fpi_exempt` ✓ ehrlich gelabelt |
| Peer-Quant (Nutzer-Auswahl) | FICO 58,2 % vs VRSK 45,0 % / SPGI 44,3 % ✓ | 52,6 %/36,0 % vs AMAT/LRCX/KLA ✓ | 61,6 % vs LLY 49,4 % / SNY 20,0 % ✓ |
| Mehrjahres-Bewertung | `complete` (~3J, yfinance-bedingt) | `complete` | `complete` |
| Div-Yield-Guard | — | Prozent-Glitch auto-korrigiert 0,67 → 0,0067 ✓ | — |

**Beide neuen Pfade (US dynamisch + EU-ADR→20-F) sind end-to-end real verifiziert.**

---

## Pro-Dossier-Charakterisierung

### FICO (`output/Watchlist/FICO_2026-06-18.md`, 26,7 KB)
Voll filing-geerdet. Alle 15 Punkte mit konkreten Quellen-Markern (`[10-K §1/§1A/§7/§7A/§8]`,
`[yfinance, 5J]`, vereinzelt `[Inferenz]`). Substanz: FHFA/VantageScore-Regulierungsrisiko,
58,2 % op. Marge vs Peers, Bureau-Vertriebsabhängigkeit (Experian/TransUnion/Equifax), 226
Stellen-Restrukturierung, Umsatzrealisierung als „Critical Audit Matter", 127 Insider-Verkäufe.
**Empfehlung: PASS** — substanzielle Entscheidungsgrundlage.

### NOVO-B.CO (`output/Watchlist/NOVO-B.CO_2026-06-18.md`, 11,4 KB)
20-F parste sauber (Anchor-Links vorhanden). Punkte mit `[20-F §4/§5/§18]` + `[yfinance, 5J]`.
Substanz: Akero-Akquisition (MASH), 9.000 Entlassungen 2025, CEO-Wechsel + a.o. HV,
Marktanteilsverlust Ozempic/Wegovy an Lilly, US-Rabatt-Abgrenzung als „Critical Audit Matter",
FCF-Yield −1,0 % (Investitionszyklus), Patent bis 2032. Insider-Lücke korrekt als FPI-exempt
gelabelt. **Empfehlung: PASS** — substanzielle Entscheidungsgrundlage; dokumentierte FPI-Lücke
ehrlich ausgewiesen.

### ASML.AS (`output/Watchlist/ASML.AS_2026-06-18.md`, 12,3 KB) — nuanciert
Mechanik griff (CIK/Form/Peer/Quant alle ✓), **aber alle 15 Punkte tragen `[Inferenz]`**.
Ursache: ASMLs spezifisches 20-F hat keine SEC-Item-Anchor-Links → Parser-Fallback auf
Pattern-Matching → `item4/item5 missing, item18 truncated` → der Honest-Label-Guard konnte die
vom Modell emittierten Sektions-Zitate nicht gegen das geparste Filing verifizieren und hat sie
konservativ alle auf `[Inferenz]` heruntergestuft.

- **Inhalt ist trotzdem reich und ASML-spezifisch korrekt:** High-NA EUV, 1,3 Mrd. €
  Mistral-AI-Beteiligung, CEO-Eingeständnis Agilitätsverlust, 88 % Kundenzufriedenheit,
  78,9 % Engagement / 4,1 % Fluktuation, 1.700 Netto-Stellenabbau, EUV-De-facto-Monopol,
  Exportkontroll-Risiko, FCF-Yield 1,3 %.
- **Was fehlt:** Rückverfolgbarkeit jeder Aussage zur konkreten 20-F-Sektion. Ein Leser kann die
  Claims nicht im Filing nachschlagen — die Provenienz ist pauschal entwertet.

**Empfehlung: GRENZFALL.** Der Guard arbeitet korrekt (lieber `[Inferenz]` als erfundenes Zitat
— Mechanismus bestanden). Ob der reiche, aber provenienz-lose Inhalt für *dich* „substanzielle
Entscheidungsgrundlage" ist, ist genau die Gate-Frage. Für das ≥2/3-Kriterium tragen FICO + NOVO
ohnehin; ASML ist der lehrreiche „Vertiefen/Parser-Lücke"-Fall.

---

## Befund / Follow-up-Kandidat (nicht-blockierend für das Gate)

**20-F-Anchor-Link-Parser scheitert filing-spezifisch.** ASMLs 20-F → kein Anchor-Anker → alle
Punkte `[Inferenz]`. NOVOs 20-F parste sauber → kein 20-F-weiter Defekt, sondern Format-Varianz
einzelner Filer. Kandidat für ein eigenes Ticket: robusterer 20-F-Item-Segmentierer
(Pattern-Match-Fallback härten oder Anchor-frei strukturieren), damit 20-F-Filer mit dieser
Variante filing-geerdete Zitate statt Pauschal-`[Inferenz]` bekommen.

**Executive-Summary-Stub:** Alle drei Dossiers haben die Exec-Summary noch als Template-Platzhalter
(`[3 Sätze … von Gemini in B.1+ befüllt]`) — erwartungsgemäß, die 15 Punkt-Blöcke tragen die
Substanz; Exec-Summary-Befüllung ist Sub-Phase B.1+.

---

## Verdikt (Stephan, 2026-06-22)

**„Alle drei wie empfohlen."** FICO + NOVO-B.CO klar zustimmungsfähig (PASS), ASML.AS als
Grenzfall/„Vertiefen" anerkannt. Damit ist das ≥2/3-Kriterium erfüllt → **Phase 1 erfolgreich
abgenommen.** Der ASML-Befund (filing-spezifische 20-F-Anchor-Link-Lücke → Pauschal-`[Inferenz]`)
geht als nicht-blockierender Follow-up-Ticket-Kandidat weiter (robusterer 20-F-Item-Segmentierer).

| Dossier | Empfehlung | Stephans Urteil |
|---|---|---|
| FICO | PASS | **PASS** (wie empfohlen) |
| NOVO-B.CO | PASS | **PASS** (wie empfohlen) |
| ASML.AS | GRENZFALL | **GRENZFALL anerkannt** (wie empfohlen) |
