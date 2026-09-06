r"""Verwirft gezielt eine Haelfte des ADR-Caches: die Negativ- oder die Positiv-Verdikte.

Wann noetig: nach einer Aenderung an der Aufloesungslogik, die vorhandene Verdikte
entwerten kann. Die TTL heilt das zwar von selbst (180 Tage positiv, 30 Tage negativ),
aber zu langsam fuer eine Messung, die unmittelbar danach laufen soll -- der Zaehllauf
oder die Live-Probe wuerde die alten Verdikte zurueckelesen und die Aenderung nicht
sehen. Genau diese Falle hat 2026-06 schon einmal eine Verifikation wertlos gemacht.

WELCHE Haelfte, haengt an der Aenderung -- und die Wahl ist nicht symmetrisch:

  --verdicts negative   Ein Negativ-Verdikt ist eine Aussage darueber, dass NICHTS
                        gefunden wurde, und damit anfaellig fuer jeden Such-Defekt.
                        Die unpaginierte OpenFIGI-Volltextsuche etwa liess 'US-Linie
                        lag auf Seite 2' wie 'keine US-Linie' aussehen. Ein positives
                        Verdikt (cik + form_type) entsteht nur, wenn eine US-Linie
                        tatsaechlich gefunden wurde, war davon nie betroffen und
                        kostet ~4 OpenFIGI-Calls, es wegzuwerfen -- deshalb ist dies
                        der Standard.

  --verdicts positive   Umgekehrt fuer jede Aenderung, die ein bisher POSITIVES
                        Verdikt entwerten kann. Der Aktualitaetsschnitt in
                        detect_annual_form (2026-09-05) ist der erste Fall dieser Art:
                        was als resolved_20f im Cache liegt, kann danach
                        no_annual_form sein, weil das Formular zu alt ist. Hier ist
                        die Standardauswahl exakt die falsche.

  --verdicts all        Beides. Nur wenn die Aenderung an beiden Enden wirkt.

Aufruf (cmd.exe):
  uv run python scripts\purge_adr_verdicts.py --dry-run
  uv run python scripts\purge_adr_verdicts.py --verdicts positive --dry-run
  uv run python scripts\purge_adr_verdicts.py --verdicts positive
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "cache" / "adr_resolved.json"


def is_negative(entry: object) -> bool:
    """Ein Negativ-Verdikt traegt `no_sec_source_reason`; die Tabelle und der Cache
    benutzen dieselbe Unterscheidung (siehe app/deepdive/adr_table.py). Alles andere
    -- auch ein kaputter Eintrag -- gilt als positiv und wird beim Standardlauf
    bewahrt, nicht still verworfen."""
    return isinstance(entry, dict) and bool(entry.get("no_sec_source_reason"))


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--verdicts",
        choices=("negative", "positive", "all"),
        default="negative",
        help="welche Haelfte verworfen wird (Standard: negative)",
    )
    p.add_argument("--dry-run", action="store_true", help="nur zeigen, nichts schreiben")
    p.add_argument("--path", default=str(CACHE), help="abweichender Cache-Pfad")
    args = p.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"{path} existiert nicht -- nichts zu tun")
        return 0

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print(f"{path}: unerwarteter Top-Level-Typ {type(data).__name__} -- Abbruch")
        return 1

    if args.verdicts == "negative":
        drop = {k: v for k, v in data.items() if is_negative(v)}
    elif args.verdicts == "positive":
        drop = {k: v for k, v in data.items() if not is_negative(v)}
    else:
        drop = dict(data)
    keep = {k: v for k, v in data.items() if k not in drop}

    # `or` statt eines get-Defaults: ein positiver Eintrag traegt den Schluessel
    # teils explizit mit Wert None, teils gar nicht -- beides ist dasselbe und
    # soll nicht als zwei Kategorien erscheinen.
    reasons = collections.Counter(
        v.get("no_sec_source_reason") or "(positiv)"
        for v in drop.values()
        if isinstance(v, dict)
    )
    print(f"{path}   --verdicts {args.verdicts}")
    print(f"  Eintraege gesamt : {len(data)}")
    print(f"  behalten         : {len(keep)}")
    print(f"  verwerfen        : {len(drop)}  {dict(reasons)}")

    if args.dry_run:
        print("\n--dry-run: nichts geschrieben")
        return 0

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    print(f"\ngeschrieben: {len(keep)} Eintraege bleiben, {len(drop)} verworfen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
