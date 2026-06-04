"""Trigger an authenticated COLD dry-run against the deployed Cloud Run service.

WHY: The universe-completeness verification gate needs the free dry-run
(POST /run/monthly?dry_run=true -- filters only, $0, no Gemini, no GitHub push) and
its yfinance_unresolved list, which is returned directly in the JSON response body
(filter_report.to_dict()). The service is deployed --no-allow-unauthenticated, so the
POST needs a valid Google OIDC identity token whose audience is the service URL.

AUTH (Cloud Run --no-allow-unauthenticated is fiddly; this script supports 3 ways):
  1. PROXY (most robust for a user-gcloud login). In terminal A:
       gcloud run services proxy fisherscreen-service --region europe-west3 --port 8080
     then point this script at the local proxy (it injects auth, no token needed):
       uv run python scripts/trigger_cold_dry_run.py http://localhost:8080
  2. ENV TOKEN: set FISHERSCREEN_ID_TOKEN to a token whose audience is the service URL
     (e.g. from an impersonated service account), then pass the real service URL.
  3. ADC: if the above are unset and the URL is not localhost, the script tries
     google.oauth2.id_token.fetch_id_token (works with SA / impersonated ADC; usually
     NOT with a plain `gcloud auth application-default login` user credential).

PREREQUISITE: run the cold purge first, in this order, so the cache cannot mask attrition:
  uv run python scripts/purge_ticker_cache_all.py --apply
  uv run python scripts/purge_edgar_cache_all.py --apply

The dry-run fetches ~1332 tickers live and can take many minutes; the HTTP timeout is
set to 60 min to match the long-lived Cloud Run request.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import httpx

_DRY_RUN_PATH = "/run/monthly?dry_run=true"
_TIMEOUT_SECONDS = 60 * 60


def _resolve_token(audience: str) -> str | None:
    """Return a bearer token, or None when no auth header is needed (proxy/localhost)."""
    host = (urlparse(audience).hostname or "").lower()
    if host in {"localhost", "127.0.0.1"}:
        return None  # `gcloud run services proxy` injects auth for us.

    env_token = os.environ.get("FISHERSCREEN_ID_TOKEN")
    if env_token:
        return env_token

    import google.auth.transport.requests
    import google.oauth2.id_token

    auth_request = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_request, audience)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "service_url",
        help="Cloud Run base URL (or http://localhost:PORT when using the gcloud proxy)",
    )
    args = parser.parse_args()

    audience = args.service_url.rstrip("/")
    token = _resolve_token(audience)
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    url = f"{audience}{_DRY_RUN_PATH}"
    print(f"POST {url}  (timeout {_TIMEOUT_SECONDS}s, auth={'bearer' if token else 'proxy'}) ...", file=sys.stderr)
    response = httpx.post(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    print(f"HTTP {response.status_code}", file=sys.stderr)
    response.raise_for_status()

    payload = response.json()
    print(json.dumps(payload, indent=2, ensure_ascii=False))

    unresolved = payload.get("yfinance_unresolved", {})
    skipped = payload.get("edgar_skipped", {})
    gc_drops = payload.get("going_concern_drops", [])
    print("\n=== CONVERGENCE SUMMARY ===", file=sys.stderr)
    print(
        f"yfinance_unresolved : count={unresolved.get('count')} "
        f"tickers={unresolved.get('tickers')}",
        file=sys.stderr,
    )
    print(
        f"edgar_skipped       : no_cik={skipped.get('no_cik', {}).get('count')} "
        f"data_source_error={skipped.get('data_source_error', {}).get('count')}",
        file=sys.stderr,
    )
    print(f"going_concern_drops : {len(gc_drops)}", file=sys.stderr)
    print(
        "\nEXPECTED (post-fix, 1332-universe): unresolved ~5 "
        "(the UNCLEAR set: AMS.VI, RIGN.SW, ROL.L, SANO.HE, SCHA.OL), NOT 0; "
        "the 13 corrected tickers (ERIC-B.ST, ATCO-A.ST, HM-B.ST, ASM.AS, DSFIR.AS, "
        "FLTR.L, ICG.L, TEVA, INDV, BTRW.L, AKRBP.OL, EFGN.SW, INVP.L) must NOT appear.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
