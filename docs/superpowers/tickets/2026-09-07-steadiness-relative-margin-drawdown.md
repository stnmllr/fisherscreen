# Ticket: S2 als relativer Margenrückgang prüfen — Prozentpunkte geben Hochmargen-Geschäften mehr Fallhöhe

**Opened:** 2026-09-07
**Priority:** niedrig. Die Dimension funktioniert mit der pp-Kennzahl; das hier ist eine
Verbesserung der Messgröße, kein Defekt. **Nicht vor dem ersten Monatslauf mit der Dimension
anfassen** — sonst wird an einer Kennzahl geschraubt, deren Live-Verhalten noch niemand gesehen
hat.
**Status:** offen

## Beobachtung

S2 misst den größten Rückgang der operativen Marge vom bisherigen Hoch **in Prozentpunkten**.
Aufgefallen an TPL im Kalibrierungslauf 2026-09-07:

```
TPL op. Marge: 2018: 86,9%  2019: 81,5%  2020: 71,8%  2021: 80,4%
               2022: 84,3%  2023: 77,0%  2024: 76,4%  2025: 74,2%
```

Der Rückgang vom Hoch beträgt **15,1 pp** — viel in Prozentpunkten, aber nur **17 % des
Höchststands**. Ein Geschäft mit 87 % Marge hat strukturell mehr Fallhöhe in Prozentpunkten als
eines mit 20 %; FAST etwa schwankt zwischen 19,8 % und 20,8 % und kann gar nicht 15 pp fallen.
Die Kennzahl vergleicht damit nicht gleich.

## Warum das trotzdem nicht dringend ist

TPL fällt ohnehin, und zwar **zusätzlich über S1** (zwei Rückgangsjahre bei sieben Übergängen).
Es ist außerdem seit dem 2026-09-07 in der Preisnehmer-Spalte gekennzeichnet
(`data/price_takers.json`, `Oil & Gas E&P`). Der Fall, an dem die Schwäche auffiel, wird also
schon von zwei anderen Mechanismen erfasst.

Die Frage ist, ob es einen Titel gibt, der **nur** wegen dieser Skalenfrage falsch bewertet wird
— hoch- oder niedrigmargig, ohne Preisnehmer-Kennzeichnung, ohne S1-Auffälligkeit. Das ist
messbar, aber nicht geraten.

## Was zu tun ist

1. In `scripts/calibrate_steadiness_bands.py` eine dritte S2-Variante ergänzen: relativer
   Rückgang `max((peak − marge) / peak)` als Anteil, neben `std` und `drawdown`.
2. **Neuer Kalibrierungslauf mit demselben Skript** — die pp-Bänder (5/12/24/48) sind für die
   absolute Kennzahl festgezogen und gelten für eine relative Größe nicht. Neue Bänder aus der
   Verteilung, neue Nebenbedingungen prüfen (HL/NEM/MU unter 4,0; MEDP/FAST/FICO ab 4,0).
3. Die Regressionstabelle in §10.2 der Spec neu rechnen. Zu erwarten sind Verschiebungen bei den
   Hochmargen-Titeln (TPL, FICO 46,5 %, NVDA 60,4 %) und bei den Niedrigmargen-Titeln in beide
   Richtungen.
4. Entscheiden — nicht automatisch übernehmen. Die absolute Kennzahl hat ein eigenes Argument:
   ein Einbruch von 15 pp ist für die Ertragskraft dasselbe, egal von welchem Niveau er
   ausgeht.

## Bezug

- Spec: `docs/superpowers/specs/2026-09-07-dimension-steadiness-design.md` §5, §5.1
- Kalibrierung: `docs/superpowers/diagnostic-reports/2026-09-07-steadiness-band-calibration.md`,
  Abschnitt „Beobachtung zu TPL"
