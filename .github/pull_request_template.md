<!--
Beschreibung frei formulieren: was geändert wurde, warum, und woran man es nachprüft.
Die Liste unten ist bewusst kurz — jeder Punkt steht dort, weil er schon einmal
vergessen wurde, nicht weil er sich gut liest. Was nicht zutrifft, wird abgehakt
mit „n/a" plus Grund, nicht stillschweigend gelöscht.
-->

---

## Vor dem Merge

- [ ] `uv run python -m black --check .` und `uv run python -m pytest -m "not integration"`
      grün — **Zahlen im PR-Text**, nicht nur die Behauptung
- [ ] **`Projektstand.md` fortgeschrieben** — oder bewusst nicht, dann kurz warum.
      Die Datei nennt sich Single Source of Truth; wenn sie es nicht ist, weiß es niemand
- [ ] Betroffene Tickets unter `docs/superpowers/tickets/` auf den neuen Stand gezogen
      (Status, oder Resolution-Abschnitt bei erledigten)
- [ ] Verhaltensänderungen, die **Caches oder gespeicherte Verdikte entwerten**, benannt —
      samt Weg, sie zu invalidieren (Purge-Skript, Schema-Version, Jahrgangs-Erkennung).
      Ein Fix, den ein warmer Cache verdeckt, ist kein Fix
