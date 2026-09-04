r"""Verwirft die Negativ-Verdikte aus dem ADR-Cache und laesst die positiven stehen.

Warum selektiv: ein positives Verdikt (cik + form_type) entsteht nur, wenn eine
US-Linie tatsaechlich gefunden wurde -- es war vom Pagination-Defekt nie betroffen und
kostet ~4 OpenFIGI-Calls, es wegzuwerfen. Ein Negativ-Verdikt dagegen kann genau der
Fehlbefund sein, den die unpaginierte Suche erzeugt hat: 'keine US-Linie' konnte auch
'US-Linie lag auf Seite 2' heissen.

Wann noetig: nach einer Aenderung an der Aufloesungslogik, die Negativ-Verdikte
entwerten kann. Die 30-Tage-TTL heilt das zwar von selbst, aber zu langsam fuer eine
Messung, die unmittelbar danach laufen soll -- der Zaehllauf wuerde die alten Verdikte
zurueckelesen und die Aenderung nicht sehen.

Aufruf (cmd.exe):
  uv run python scripts\purge_adr_negative_verdicts.py --dry-run
  uv run python scripts\purge_adr_negative_verdicts.py
"""

from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

CACHE = Path(__file__).resolve().parents[1] / "cache" / "adr_resolved.json"


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
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

    negative = {k: v for k, v in data.items() if isinstance(v, dict)
                and v.get("no_sec_source_reason")}
    keep = {k: v for k, v in data.items() if k not in negative}

    reasons = collections.Counter(v["no_sec_source_reason"] for v in negative.values())
    print(f"{path}")
    print(f"  Eintraege gesamt : {len(data)}")
    print(f"  behalten (positiv): {len(keep)}")
    print(f"  verwerfen (negativ): {len(negative)}  {dict(reasons)}")

    if args.dry_run:
        print("\n--dry-run: nichts geschrieben")
        return 0

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    print(f"\ngeschrieben: {len(keep)} Eintraege bleiben, {len(negative)} verworfen")
    return 0


if __name__ == "__main__":
    sys.exit(main())
