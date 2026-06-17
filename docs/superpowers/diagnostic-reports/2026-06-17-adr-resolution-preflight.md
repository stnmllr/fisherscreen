# ADR-Resolution Pre-Flight — Befund (B-Fast, ADR-BF-3)

**Zweck:** Prüfe, ob sich der Pfad EU-Yahoo-Ticker → OpenFIGI US-ADR-Linie → SEC-CIK zuverlässig für 20-F-ADR-Filer aufklären lässt. Go/No-Go-Gate für EU-ADR-Folge-Plan.

## Befund pro Filer

| Filer | Eindeutige US-ADR-Linie? | get_cik löst auf? | Mehrdeutigkeit? |
|---|---|---|---|
| NVO (NOVO-B.CO) | — | — | — |
| ASML (ASML.AS) | — | — | — |
| SAP (SAP.DE) | — | — | — |

## Funktionierende OpenFIGI-Methode

(Zu dokumentieren nach dem Netz-Lauf: welche Query hat funktioniert, welche Mehrdeutigkeiten oder Fehlschläge gab es.)

## Verdikt

Zwei mögliche Outcomes:

- **GO** → für ≥2 der 3 Filer eindeutige US-ADR-Linie mit auflösender CIK, kein Falsch-Match → EU-ADR-Folge-Plan terminieren.
- **NO-GO** → unzuverlässig/mehrdeutig → B-Fast bleibt US-Pfad allein; EU-ADR wird Phase 2 (Honest-Label im PROJEKTSTAND).

---

> Status: SKELETON — auszufüllen nach dem echten Netz-Lauf von `scripts/preflight_adr_resolution.py`
