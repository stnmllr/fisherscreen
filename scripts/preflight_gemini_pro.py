"""Pre-Flight-Check (Tool B Master-Brainstorm §7a Pkt 1):
Ist `gemini-2.5-pro` aus dem FisherScreen-GCP-Projekt-API-Key nutzbar?

Liest `FISHERSCREEN_GEMINI_API_KEY` aus der Umgebung. Gibt den Key
NIEMALS aus (Lesson n — Token-Leak in Logs vermeiden).

Verdikt:
  OK     -> gemini-2.5-pro nutzbar -> B.1-Synthesis-Default = gemini-2.5-pro
  QUOTA  -> 429/403 -> B.1-Default = gemini-2.5-flash-lite via
            FISHERSCREEN_DEEPDIVE_GEMINI_MODEL
  ERROR  -> anderer Fehler, manuell prüfen

Aufruf (cmd.exe):
  set FISHERSCREEN_GEMINI_API_KEY=<key>
  uv run python scripts\\preflight_gemini_pro.py
"""

from __future__ import annotations

import os
import sys

from google import genai
from google.genai import types
from google.genai.errors import ClientError, ServerError

MODEL = "gemini-2.5-pro"
FALLBACK = "gemini-2.5-flash-lite"


def main() -> int:
    key = os.environ.get("FISHERSCREEN_GEMINI_API_KEY", "")
    if not key:
        print("FAIL: FISHERSCREEN_GEMINI_API_KEY not set in environment")
        return 2

    client = genai.Client(api_key=key)
    prompt = "Reply with the single word OK."

    try:
        ct = client.models.count_tokens(model=MODEL, contents=prompt)
        print(f"count_tokens OK: {ct.total_tokens} input tokens")

        resp = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(max_output_tokens=500),
        )
        reply = (resp.text or "").strip()
        usage = getattr(resp, "usage_metadata", None)
        tokens_in = getattr(usage, "prompt_token_count", 0) or 0
        tokens_out = getattr(usage, "candidates_token_count", 0) or 0
        print(
            f"generate_content OK: reply={reply!r} "
            f"tokens_in={tokens_in} tokens_out={tokens_out}"
        )
        print(f"VERDICT: OK — {MODEL} nutzbar; B.1-Synthesis-Default = {MODEL}")
        return 0
    except ClientError as exc:
        code = getattr(exc, "code", None)
        if code in (429, 403):
            print(
                f"VERDICT: QUOTA/PERMISSION (ClientError {code}) — "
                f"B.1-Default = {FALLBACK} via FISHERSCREEN_DEEPDIVE_GEMINI_MODEL"
            )
            return 0
        print(f"VERDICT: ERROR ClientError {code}: {exc}")
        return 1
    except ServerError as exc:
        print(f"VERDICT: ERROR ServerError {getattr(exc, 'code', None)}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
