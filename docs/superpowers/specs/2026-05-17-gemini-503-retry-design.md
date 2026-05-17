# Design: Gemini 503-Retry mit tenacity

**Datum:** 2026-05-17
**TODO:** Phase-2 #11 (Quick Win vor 2026-06-01-Lauf)
**Branch:** `feature/gemini-503-retry`
**Aufwand:** ~1h

---

## Problem

Beim ersten Produktivlauf (2026-05-16) wurde ALV.DE aus dem Gemini-Scoring
geworfen, weil Gemini ein transientes `503 UNAVAILABLE — high demand`
zurückgab. Aktuell führt jede Exception aus einem Gemini-Netzwerk-Call zu
`GeminiError`, was den Ticker für den gesamten Monatslauf eliminiert. Ein
Top-Kandidat verschwindet so wegen einer Sekunden-langen Lastspitze.

Der Schaden ist asymmetrisch: Tool A läuft monatlich. Ein wegen 503
übersprungener Ticker ist 30 Tage lang unsichtbar — kein Re-Run dazwischen.

## Ziel

Transiente Gemini-Fehler (503 UNAVAILABLE, 429 RESOURCE_EXHAUSTED) werden
mit exponentiellem Backoff retried, statt den Ticker sofort zu verlieren.
Permanente Fehler verhalten sich unverändert (Ticker-Skip, Run läuft weiter).

## Nicht-Ziele

- Kein Retry auf andere 5xx (500/502/504) — bewusst eng an TODO #11.
- Keine Änderung an `CachedGeminiClient` oder `scorer.py`.
- Kein globales Retry-Budget über alle Ticker (YAGNI; per-Call reicht).
- Keine Jitter-Randomisierung (Spec gibt feste 1s/4s/16s vor).

## Architektur-Einordnung

Der Retry lebt **ausschließlich in `GeminiClientImpl`**
(`app/services/gemini_client.py`), hinter dem `GeminiClient`-Protocol.
`CachedGeminiClient` und `scorer.py` bleiben unverändert.

Bestehender Vertrag bleibt erhalten: Wenn alle Retries scheitern, fliegt
weiterhin `GeminiError` → `scorer.py`-Per-Ticker-Guard überspringt den
Ticker → Run läuft weiter. **Kein Verhaltenswechsel im Fehlerfall, nur ein
zusätzlicher Recovery-Pfad davor.**

## Komponenten

### 1. Retry-Prädikat (Modul-Level)

```python
from google.genai.errors import ServerError, ClientError

def _is_retryable(exc: BaseException) -> bool:
    return (
        (isinstance(exc, ServerError) and exc.code == 503)
        or (isinstance(exc, ClientError) and exc.code == 429)
    )
```

Exakt 503 UNAVAILABLE + 429 RESOURCE_EXHAUSTED. Andere Fehler fallen
sofort durch wie bisher.

### 2. Zwei dekorierte Private-Methoden

`count_tokens()` und `generate_content()` werden aus `score_ticker()` in
`_count_tokens()` / `_generate()` extrahiert. Beide sind Gemini-Netzwerk-
Calls, beide können 503 werfen, beide führen aktuell zum Ticker-Skip →
beide werden abgesichert.

```python
@retry(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),                       # 1 Initial + 3 Retries
    wait=wait_exponential(multiplier=1, exp_base=4),  # → 1s, 4s, 16s
    reraise=True,
)
```

`reraise=True` ist kritisch: nach erschöpften Retries fliegt die
**originale** genai-Exception, die dann von den bestehenden
`except Exception → GeminiError`-Blöcken in `score_ticker()` gewrappt wird.
Tenacity muss die rohe `ServerError` sehen, *bevor* sie zu `GeminiError`
wird — deshalb Decorator auf den Extrakt-Methoden, nicht auf
`score_ticker()`.

**Backoff-Verifikation** (tenacity-Formel
`multiplier * exp_base^(attempt_number - 1)`):

| Nach Attempt | Wait |
|---|---|
| 1 | 1·4⁰ = **1s** |
| 2 | 1·4¹ = **4s** |
| 3 | 1·4² = **16s** |
| 4 | `stop_after_attempt(4)` → kein weiterer Retry |

Worst-Case-Zusatzlatenz pro dauerhaft fehlschlagendem Ticker: ~21s.

### 3. Dependency

`uv add tenacity` — Promotion von transitiv (`tenacity 9.1.4` ist bereits
in `uv.lock` als Sub-Dependency) zu direkter Dependency in
`pyproject.toml`. Kein neuer Download. CLAUDE.md-konform als bewusster
Schritt dokumentiert.

## Datenfluss (unverändert bis auf Retry-Schicht)

```
scorer.run_gemini_scoring()
  → CachedGeminiClient.score_ticker()   [Cache-Miss]
    → GeminiClientImpl.score_ticker()
      → _count_tokens(prompt)        @retry(503/429)
      → _generate(prompt, ...)       @retry(503/429)
      → _parse_response(...)
```

## Fehlerbehandlung

| Szenario | Verhalten |
|---|---|
| 503 transient, löst sich in ≤3 Retries | Ticker wird normal gescort |
| 429 transient | wie 503 |
| 503/429 persistent (4 Calls scheitern) | `GeminiError` → Ticker-Skip (bisheriges Verhalten) |
| 400 / 500 / 502 / 504 | **kein** Retry, sofort `GeminiError` (bisheriges Verhalten) |
| Token-Limit überschritten | unverändert — `GeminiError` ohne Retry (kein Netzwerk-Fehler) |

## Test-Strategie (TDD — Tests zuerst)

`tests/services/test_gemini_client.py`, bestehendes
`@patch("app.services.gemini_client._genai")`-Pattern. Echte
`ServerError(503, {...})` / `ClientError(429, {...})` aus
`google.genai.errors` (im `.venv` vorhanden — kein Mock der Exception-
Typen nötig). Sleep neutralisiert via
`GeminiClientImpl._generate.retry.sleep = lambda *_: None` (bzw.
`_count_tokens`) → Tests laufen ohne reale Wartezeit.

| Test | Erwartung |
|---|---|
| `generate_content` 503 ×2, dann Erfolg | Ergebnis OK, 3 Calls |
| `count_tokens` 503 ×1, dann Erfolg | Ergebnis OK (beide Calls abgesichert) |
| 503 persistent (×4) | `GeminiError`, exakt 4 Calls |
| `ClientError(429)` transient | retried, Erfolg |
| `ClientError(400)` | **kein** Retry, sofort `GeminiError`, 1 Call |
| `ServerError(500)` | **kein** Retry, sofort `GeminiError`, 1 Call |
| Integration: `CachedGeminiClient` + echter `GeminiClientImpl`, Cache-Miss, 503→Erfolg | Ergebnis gecacht & zurückgegeben — Retry trägt durch Cache-Layer |

## Akzeptanzkriterien

- [ ] `uv run python -m pytest` grün (alle Tests)
- [ ] Coverage ≥ 95%
- [ ] `tenacity` als direkte Dependency in `pyproject.toml`
- [ ] Retry deckt `_count_tokens` UND `_generate` ab
- [ ] Nur 503 + 429 lösen Retry aus (500/502/504/4xx≠429 nicht)
- [ ] Persistenter Fehler → `GeminiError` (bisheriges Skip-Verhalten erhalten)
- [ ] Backoff-Schedule 1s/4s/16s, max 4 Calls (Lesart A)
- [ ] Integrationstest gegen `CachedGeminiClient` grün
