# Punkt 3 — Revenue-Growth-Viabilitäts-Floor — Calibration

> Vintage: 2026-06. Branch: `feature/revenue-growth-viability-floor`.
> Spec: `docs/superpowers/specs/2026-06-10-punkt-3-revenue-growth-viability-floor-design.md`.
> Plan: `docs/superpowers/plans/2026-06-10-punkt-3-revenue-growth-viability-floor.md`.
> Provenance-Blobs (eingefroren, dieses Verzeichnis): `revenue_growth_drops.csv` (189 Drops,
> angereichert), `full_sweep_slipthrough.csv` (Residuum-Korb).
> Verwandt: `[[adaptive-stat-swallows-judgment]]`, `[[punkt2-sector-gross-margin-floor-state]]`.

---

## 1. Was kalibriert wurde

Der flache `revenue_growth_yoy >= 0`-TTM-Snapshot-Knock-out wird durch einen **strukturellen
Mehrjahres-Viabilitäts-Floor** ersetzt (Hybrid Lazy-Fetch + γ-Drei-Signal-Konjunktion). Leitprinzip:
das Gate eliminiert nur echte Mehrjahres-Schrumpfer; der Wachstums-*Qualitätsgrad* gehört in den
Gemini-Scorer (Fisher Punkt 1 = „sizable increase for at least several years", nie ein Snapshot).

**γ-Kern (rein absolut/strukturell — kein Pinning, kein Vintage-Stempel auf den Schwellen):**
unter dem Hybrid-Lazy-Fetch (Mehrjahres-Blick nur bei TTM<0/None) ist DROP effektiv eine
Drei-Signal-Konjunktion:

```
DROP  ⟺  TTM < 0  ∧  multiyear_CAGR < 0  ∧  down_years >= 2
```

Drei unabhängige Messungen müssen alle „Niedergang" sagen. Kein `latest_down`-Kriterium: das
negative TTM ist das frischeste „aktuell-down"-Signal. `down_years >= 2` braucht ≥4 GJ; <4 GJ →
`UNASSESSABLE` → pass (Floor-Logik, bewusstes Routing, kein Silent-Pass).

## 2. Akzeptanz-Identität (Vintage 2026-06)

Quelle: `scripts/diagnose_revenue_growth_drops.py --with-trend --full-sweep` (γ-ausgerichtet,
warmer Cache, $0). Der γ-Kern, einheitlich über alle 189 heutigen Drops angewandt:

```
189 = 81 DROP + 107 RESCUE + 1 UNASSESSABLE          (geht voll auf — kein unbilanzierter Titel)
```

| Teilkorb | DROP | RESCUE | UNASSESSABLE |
|---|---|---|---|
| negativ-TTM (176) | 76 | 99 | 1 (TREL-B.ST, n_years=1, Kurzhistorie) |
| missing-TTM (13, `revenueGrowth=None`) | 5 | 8 | 0 |

**Die 13 Missing-TTM sind kein monolithischer Rescue-Bucket:** 5 sind echte γ-Schrumpfer und werden
floor-korrekt gedroppt — **Kering** (CAGR −10,3 %, dy=3), **Unilever** (−5,6 %, dy=2), **Vivendi**
(−68 %, dy=2), **Georg Fischer** (−9,1 %, dy=3), **Sonova** (−1,2 %, dy=3). Sie am Mehrjahres-Maß zu
beurteilen (nicht auto-pass) verhindert die Inversion des ursprünglichen Missing-Data-Bugs: ein
fehlendes `.info`-Feld darf ein *berechnetes* Urteil aus echten Statements nicht überstimmen.
Identifizierbar bleiben alle 13 via `revenue_growth_yoy=None` am Record.

**Hermetischer Lock:** `tests/screener/test_revenue_growth_acceptance.py` reproduziert 81/107/1/0
netzfrei aus den eingefrorenen CSV-Zahlen durch die Produktions-Gate-Funktion `revenue_growth_outcome`.

**Monotonie:** jeder heutige revenue_growth-Pass bleibt Pass; Änderungsmenge ⊆ den 189. Die 5
Missing-TTM-γ-Drops waren heute schon Drops (`None→False`), bleiben Drops mit jetzt legitimem statt
artefaktischem Grund. Kein Titel wird neu rausgeworfen.

## 3. Akzeptiertes Residuum X — die Hybrid-B-Asymmetrie

Hybrid B prüft TTM≥0-Titel nie nach. Der Voll-Sweep beziffert den Korb **direkt** als
`TTM≥0 ∧ CAGR<0 ∧ down_years≥2` über die Basis-Survivors. Survivor-Basis explizit aus
`revenue_growth_pass_reason` hergeleitet:

```
Survivor-Basis = 839 = 731 TTM_PASS + 107 TRAJECTORY_RESCUE + 1 UNASSESSABLE_PASS
   (die +108 ggü. 731 = die jetzt durchgelassenen Rescues; nur die 731 TTM_PASS sind Slip-Kandidaten)

X = 104 Survivors (TTM>=0 AND gamma CAGR<0 AND down_years>=2), davon 61 >10B Large-Caps
```

**Korrektur ggü. einer früheren Schätzung X=54:** die 54 war ein Undercount — sie filterte nur die
α-`MULTI_YEAR_DECLINE`-Teilmenge (76, verlangt `latest_down`) nach γ und übersah die ~50 γ-Titel mit
*letztem Jahr hoch* (cagr<0 ∧ dy≥2 ∧ latest_up; α stuft die als RECOVERED ein). |γ|=104, |α|=76,
|α∩γ|=54. Der α→γ-angeglichene Sweep zählt jetzt `is_gamma_decline` direkt; drei Invarianten sichern
Zahl-Regel-Blob-Deckung: jede Slip-Zeile erfüllt γ (In-Script-Assert + `test_residuum_blob_is_gamma_
consistent_and_pinned`), CSV-Zeilenzahl == X, Survivor-Basis aus pass_reason. `full_sweep_slipthrough.csv`
(104 Zeilen, jede γ) ist der eingefrorene Provenance-Blob.

Beispiele: XOM (TTM +2,6 % / CAGR −6,7 %), Intel (+7,2 % / −5,7 %), Chevron (+2,3 % / −7,9 %),
Shell (+0,7 % / −11,2 %), TotalEnergies (+3,4 % / −11,5 %), Pfizer (+5,4 % / −14,8 %), plus eine
große Klasse nahezu-flacher Erholer (Martin Marietta −0,1 % / +17 %, Corteva −0,1 % / +11 %, Altria
−0,9 % / +5 %).

**Bewusst akzeptiert — *wegen* der Richtung, nicht *trotz* der Größe:** alle 104 haben positives TTM —
ihr Niedergang liegt im Rückspiegel, das jüngste rollierende Fenster wächst wieder (Erholung/
Inflektion, kein schleichender Schrumpfer). Der größere Korb ist per-Titel *weniger* besorgniserregend:
die Zusatz-Titel sind nahezu-flach-CAGR bei starkem positivem TTM (doppelt erholend) — der schwächste
denkbare Slip-Through-Typ. „Erholt sich gerade — wie nachhaltig?" ist die Scorer-Frage, nicht die
Floor-Frage. Die Alternative (Voll-Universum-Maß) wäre **nicht „strenger"**, sondern würde eine
*rückwärtsgewandte* Fehlerklasse (erholende Titel auf historischem CAGR droppen) gegen eine
*vorwärtsgerichtete* eintauschen — und Fisher gewichtet „poised for increase", nicht „war mal größer".
Bei Konflikt zwischen jüngerem (TTM) und älterem (CAGR) Signal gewinnt die Gegenwart. Dass 61/104
Large-Caps sind (Öl, Pharma-Patentklippen), ist Bestätigung: Erholung-nach-Einbruch ist bei reifen
Zyklikern der Normalfall, den ein Fisher-Screen sehen *will*.

**Bekannte Eigenschaft — Corporate-Action-Artefakte:** extreme CAGR-Ausschläge können abgespaltenen
statt verlorenen Umsatz reflektieren (Vivendi −68 % = Aufspaltung Ende 2024). Der γ-Drop ist trotzdem
richtig (eine Holding, die den Großteil ihres Geschäfts abgegeben hat, ist kein Fisher-Kandidat); der
Floor unterscheidet organischen Schrumpf von Corporate-Action nicht und soll es nicht (Tool-B-Tiefe).

## 4. Stehende Monitoring-Posten

- **Jährlicher Re-Sweep** des Residuums (am Index-Drift-Sweep angedockt): der X-Korb verschiebt sich
  mit dem Konjunkturzyklus; `full_sweep_slipthrough.csv` ist der vintage-2026-06-Referenzstand.
- **Reach-Scorer (Spec §5.3):** die 104 X-Titel sind Basis-Survivors; zwischen Basis-Pass und
  Gemini-Scoring liegen nur die EDGAR-Inhaltsfilter (Restatement/Going-Concern/Enforcement), die
  orthogonal und legitim sind. Kein *struktureller* Artefakt-Block hält sie vom Scorer ab; ein
  legitimer EDGAR-Drop eines Einzelnamens widerlegt die Erholungs-Begründung nicht.
- **Fetch-Last ist zyklusabhängig:** ~189 heute; in einer Rezession kippen mehr Titel TTM-negativ und
  der Lazy-Fetch nähert sich dem Voll-Universum an — bekannte Eigenschaft, kein Defekt.

## 5. Reversibilität

**Kein dormant-Toggle** (anders als Punkt 2 `k=None`): die γ-Schwellen sind absolute Konstanten, es
gibt keine gepinnte Tabelle und kein `k`. Rollback = Code-Revert des Gates, nicht ein Config-Flip.
