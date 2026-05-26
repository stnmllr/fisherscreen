---
title: Intermediate-Items — Tail-Drop-Diagnose (Punkt 5, Folge-Ticket aus Stage 5)
date: 2026-05-26
stage: Punkt 5 / Folge-Ticket (read-only Diagnose, kein Code-Touch)
status: abgeschlossen — Ergebnis: KEIN actionable Muster (kein Handlungsbedarf)
committed: ans Ende (Report); Diagnose-Scripts bewusst untracked
scripts:
  - scripts/diagnose_drop_wirkung.py (Stage-5, reproduziert als Baseline)
  - scripts/diagnose_intermediate_items.py (dieses Ticket, read-only, untracked)
filings:
  - cache/filings/0001652044/0001652044-26-000018.txt (GOOGL 10-K)
  - cache/filings/0000021344/0001628280-26-010047.txt (KO 10-K)
  - cache/filings/0000353278/0000353278-26-000012.txt (NOVO 20-F)
  - cache/filings/0000937966/0001628280-26-011378.txt (ASML 20-F)
---

# Intermediate-Items — Tail-Drop-Diagnose

## Frage

Die Punkt-5-Stage-2-Entscheidung **N4-Option (a) Drop** schneidet Sektionen sauber an
Anchor-Grenzen: Items, die nicht in `_FORM_ITEMS` stehen (10-K: §3, §1C, §9–§14;
20-F: §6, §7, §10, §16), landen nicht mehr im Synthesis-Prompt. Stage 5 fand per
String-Probe **einen** Tail-Drop — GOOGL §11 Executive Compensation — und stufte ihn als
„echten DROP" ein, mit der ausdrücklichen Caveat, dass die Probe nur String-Präsenz
misst, nicht Substanz.

**Zentrale Frage:** Ist GOOGL §11 ein **Einzelfall** oder ein **Muster**?
Falls Muster → eigene Plan-Phase. Falls Einzelfall / kein Substanz-Verlust → Ticket
schließt mit „kein Handlungsbedarf".

## Methode

Read-only, aus den vorhandenen Stage-5-Dossiers + Cache-Filings — **kein Tool-B-Re-Run,
kein Code-Touch.** Drei Evidenz-Ebenen, jede strenger als die vorige:

1. **String-Ebene** (Stage-5-Probe reproduziert): Erscheint ein Intermediate-Item-Thema
   im neu-Prompt, nur im legacy-Last-Item-Tail, oder nirgends?
2. **Substanz-Ebene** (neu): Ist der Tail-Treffer **echter Body-Text** oder bloß
   (a) eine **TOC-/Part-III-Listenzeile** (Pipe-Form „Item 11.| Executive Compensation| 91")
   oder (b) ein **Incorporation-by-Reference-Verweis** auf ein anderes Dokument?
3. **Reasoning-Ebene** (neu): Stützt ein **Reasoning-Satz** in irgendeinem Dossier (alt
   *oder* neu, alle vier Filings) seine Substanz auf gedropptes Intermediate-Item-Material?

Alle vier Filings systematisch geprüft; GOOGL §11 als Probe-Vorlage, dann auf die
übrigen drei + alle vom Plan-Doc hypothetisierten Items (§3/§1C/§11/§13 bzw. 20-F-Pendants)
ausgeweitet. Incorporation-by-Reference per Roh-Filing-Grep verifiziert.

## Schritt 1 — Inventar der Tail-Drop-Kandidaten

| Filing | Reasoning-Thema (Fisher-Punkt) | Vermutetes Quell-Item | Tail-Treffer | Substanz des Treffers | Reasoning-Drop? |
|---|---|---|---|---|---|
| **GOOGL** | Exec-Relations (P8) | §10/§11 | §11-String im legacy-§8-Tail | **TOC-Zeile + Incorp-by-Ref** (Proxy) | nein — in keinem Dossier gegroundet |
| GOOGL | Mgmt-Tiefe (P9) | §10 | „Directors/Governance" im neu-Prompt | §1/§1A (Schlüsselperson-Risiko) | nein |
| GOOGL | Integrität (P15) | §3 Legal | „legal proceedings" im neu-Prompt | §8-Notes + §1A-Antitrust-Risiko | nein |
| GOOGL | Robustheit (P14/P15) | §1C Cyber | „cybersecurity" im neu-Prompt | §1A-Risikofaktor | nein |
| GOOGL | (kein Reasoning) | §13 Related-Party | **F8-aussen** (nirgends) | komplett im Proxy | n/a |
| **KO** | Exec-Relations (P8) | §10/§11 | §11-String im legacy-§8-Tail | **TOC-Zeile + Incorp-by-Ref** (Proxy) | nein — Dossier sagt explizit „keine Informationen" |
| KO | Mgmt-Tiefe (P9) | §10 | §1 + [Inferenz] | „keine konkreten Details zu Schlüsselpersonen" | nein |
| KO | Integrität (P15) | §3 Legal | „legal proceedings" im neu-Prompt | §3/§1A | nein |
| **NOVO** | Exec-Relations/Tiefe (P8/P9) | §6 Directors | Foundation-Kontrolle **im neu-Prompt (§4)** | inline in §4 verfügbar | nein — beide Dossiers [Inferenz] |
| NOVO | Personal (P7) | §6D Employees | „9.000" / Layoffs im neu-Prompt | §4/§5 | nein |
| NOVO | Vergütung (P8) | §6B Remuneration | nur legacy-Tail | **Incorp-by-Ref** (Remuneration Report 2025) | nein |
| NOVO | Major-Shareholder/Related (P8/P15) | §7 | nur legacy-Tail | **Incorp-by-Ref** (Annual Report 2025); Kern-Substanz dupliziert in §4 | nein |
| **ASML** | §4/§5/§18 | — | Fallback-only (0 Anchor) | 200K-§18-Blob, byte-identisch alt/neu | n/a — F5/F7, **nicht** N4-Drop |

**Strukturell absorbierte Items im legacy-Tail** (rein navigatorisch, Pipe-/Seitenzahl-Form):
GOOGL & KO §8-Tail enthalten die komplette **Part-III-TOC** (Item 10 Directors · Item 11
Executive Compensation · Item 12 Security Ownership · Item 13 Related-Party · Item 14
Accountant Fees) — als Inhaltsverzeichnis-Zeilen mit Seitenzahl, gefolgt von den
Incorporation-by-Reference-Sätzen. **Kein** substanzieller Body dieser Items im Filing.

**Verifizierte Incorporation-by-Reference (Roh-Filing-Grep):**
- GOOGL: „Proxy Statement for the 2026 Annual Meeting of Stockholders are incorporated
  herein by reference in Part III" + pro Item „The information required by this item …
  is incorporated herein by reference."
- KO: „Proxy Statement … are incorporated by reference in Part III" + „Proxy Statement to
  be filed with the SEC within 120 days …"
- NOVO: „… incorporated by reference from the Company's … Remuneration Report 2025 / Annual
  Report 2025."

## Schritt 2 — Muster-Bewertung

**Auf String-Ebene sieht es nach Muster aus:** §11 (Exec-Comp) und §12 (Security Ownership)
erscheinen als „DROP-tail" in **2/2 US-10-Ks** (GOOGL + KO). Das überschreitet die
Ticket-Schwelle (>2–3 Fälle über 2+ Filings) — **wenn man nur Strings zählt.**

**Auf Substanz-Ebene löst sich das Muster auf:** Jeder dieser Treffer ist entweder eine
**TOC-Zeile** oder ein **Incorporation-by-Reference-Verweis**. Der eigentliche Inhalt von
10-K Part III (Items 10–14: Governance, Vergütung, Related-Party) steht **per Gesetz im
DEF-14A-Proxy**, nicht im 10-K-Body — unabhängig vom Parser, schon immer. Tool B holt den
Proxy nicht. Der N4-Drop entfernt also **Zeiger, keinen Inhalt**.

**Auf Reasoning-Ebene gibt es null Fälle:** In keinem der vier Filings, weder im alt- noch
im neu-Dossier, stützt ein Reasoning-Satz seine Substanz auf gedropptes
Intermediate-Item-Material. Bei GOOGL §11 zeigt der direkte alt/neu-Vergleich: **beide**
Dossiers behandeln P8/P9 als Gründer-Kontrolle/Schlüsselperson ([Inferenz]/[§1A]) —
**keine** Exec-Comp-Aussage ist je verschwunden, weil nie eine da war. KO formuliert die
Lücke sogar explizit aus („vorgelegte Unterlagen enthalten keine Informationen" zu
Führungsbeziehungen) — die korrekte Behandlung, wenn die Daten im Proxy liegen.

**20-F-Sonderfall (ehrlich festgehalten):** Anders als US-Part-III sind 20-F §6/§7 **nicht
voll** incorporated-by-reference — NOVOs Foundation-Kontroll-Substanz steht inline. **Aber:**
diese Substanz **erreicht den neu-Prompt über §4** (verifiziert: „Novo Holdings",
„Foundation", „controlling" alle im neu-Union). Gedropt wird nur Feindetail
(„supervisory board"-Zusammensetzung, Remuneration-Tabellen — letztere wieder
incorporated-by-reference). **Kein** beobachteter Reasoning-Drop.

**Verdikt:** **Kein actionable Muster.** GOOGL §11 war ein **substanz-blinder String-Artefakt**
(die Stage-5-Probe maß genau das, wovor sie selbst warnte). Der „echte DROP" ist beim
Hinsehen die Part-III-TOC-Zeile + ein Proxy-Verweis — **kein Substanz-Verlust.**

## Schritt 3 — Optionen-Skizze (knapp, da kein Muster)

| Option | Bewertung |
|---|---|
| **(a) `_FORM_ITEMS` erweitern** (§10–§14 / §6–§7) | **Net-negativ für 10-K.** Importiert nur TOC-Zeilen + Incorp-by-Ref-Boilerplate. GOOGL/KO §8 läuft bereits am/nahe 200K-Cap → zusätzliche Part-III-Items kosten Tokens für **null Substanz**, riskieren Cap-Überschreitung. 20-F marginal positiv (§6/§7 inline), aber NOVO-Kern-Substanz ist via §4 ohnehin da. → Nicht gerechtfertigt. |
| (b) Selektives Embed on-demand | Impraktikabel (Zwei-Call-Komplexität), und es gäbe nichts Substanzielles zu embedden. Verworfen. |
| (c) Sektions-übergreifender Summary-Block | Würde Boilerplate/TOC zusammenfassen → kein Wert für 10-K. Verworfen. |
| **(d) Status-Quo + Honest-Label** | **Korrekt.** Das Gedroppte ist Navigation/Zeiger; Substanz unberührt. P8/P9/P15 sind in den Dossiers bereits ehrlich niedrig/rot bewertet. |

**Reframte echte Lücke (eigene Initiative, nicht dieses Ticket):** Fishers P8/P9/P15
(Management-Qualität/Integrität) sind für **alle** Filer dünn, weil die tiefe Governance-/
Vergütungs-/Related-Party-Substanz in einem **separaten Dokument** liegt (DEF-14A-Proxy für
US; Remuneration-/Annual-Report für NOVO), das Tool B nie zieht. Das ist eine
**Missing-Data-Source-Lücke**, kein Parser-Problem — Geschwister-Initiative zum
ASML-EU-Native-Source-Layer („Proxy/Governance-Source-Layer").

## Empfehlung an Stephan

1. **Keine Plan-Phase** für die Intermediate-Items-Mechanik. Ticket schließt mit
   **„kein Handlungsbedarf"** (Option d). §3/§1C/§13 + 20-F-Pendants bleiben dokumentierte
   technische Schuld neben F5/F7 — aber als **„kein Substanz-Verlust"**, nicht als latenter
   Defekt.
2. **Stage-5-Eintrag präzisieren:** Die GOOGL-§11-Zeile im Akzeptanz-Report
   (`2026-05-26-punkt5-acceptance.md`, „echter DROP") wird durch diesen Report **verfeinert**
   zu *TOC-Zeile + Incorp-by-Ref-Artefakt, kein Substanz-Drop*. (Der Akzeptanz-Report bleibt
   als Audit-Trail unverändert; er hatte seine Substanz-Blindheit selbst ausgewiesen.)
3. **Neuer Backlog-Zeiger** (nicht dringend, kein Scoring-Regress): „Proxy/Governance-Source-
   Layer" als Geschwister zum EU-Native-Source-Layer — der einzige echte Hebel für
   P8/P9/P15-Grounding. Eigene Brainstorm-Phase, wenn überhaupt.
4. **Weiter mit Backlog wie vereinbart:** 2a.2 (Filing-Vintage-Anzeige) → 2a.3 (globaler
   Vintage-Confidence-Faktor) → 2a.1c → B.2-Vor-Brainstorm.

## Caveats / Methodik-Grenzen

- **Kein Tool-B-Re-Run:** Reasoning-Drop wurde über alt/neu-Dossier-Vergleich +
  Parser-Output-Klassifikation bestimmt, nicht über einen neuen Gemini-Lauf. Für die
  Einzelfall-vs-Muster-Frage ausreichend; ein Re-Run hätte Kosten ausgelöst (STOP-Bedingung).
- **F8-Scope ausgeklammert:** GOOGL §13 Related-Party (Modell-Außenwissen unter validem
  Cite) bleibt F8-Backlog, hier nicht analysiert.
- **ASML:** Fällt nicht unter N4-Drop, sondern unter F5/F7 (0 Anchor-Coverage) — separate
  Schuld, Stage-4-Report.
