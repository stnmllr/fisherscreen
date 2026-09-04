from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


class OpenFIGIClient(Protocol):
    def map_ticker(self, local: str, exch_code: str) -> dict | None: ...
    def lines_by_share_class(self, share_class_figi: str) -> list[dict]: ...


# What may be the HOME LISTING OF AN OPERATING COMPANY — the one thing
# `map_ticker` is asked to find. An allow-list, not the removal of the previous
# `securityType2: "Common Stock"` hard filter: that filter is what made
# `BYG.L` (Big Yellow Group) unfindable, but dropping it wholesale would let a
# warrant or an option on the same symbol answer instead, and the name check
# downstream cannot tell those apart — a warrant on Big Yellow carries Big
# Yellow's name.
#
# IN, with the reason each is in:
#   Common Stock       the base case, and what the old filter allowed.
#   REIT               a REIT is an operating company in a tax wrapper. It has
#                      one home listing, files annual reports, and is the
#                      measured miss this change exists for (BYG.L). Property
#                      and infrastructure names are a large EU block.
#   Preference         a preference share is a real listing of the issuer, not a
#                      derivative of one; on several German and Nordic names it
#                      IS the listed line (and the one the ADR sits on).
#   Depositary Receipt Dutch/Belgian STAK structures list depositary receipts as
#                      the ordinary home line. The exchange code already pins us
#                      to the home venue, so this cannot pull in a US ADR.
#
# OUT, deliberately: Option, Warrant, Right (derivatives ON the company, not the
# company), Future/Index (not an issuer at all), every bond type (debt has no
# share class to enumerate), Mutual/Open-End/Closed-End Fund and ETP (a fund is
# not an operating company), Ltd Part / MLP / Royalty Trust / Unit (pass-through
# vehicles; none is an EU home listing, and admitting them on speculation is how
# an allow-list stops being one).
#
# Fails CLOSED on a type nobody has seen: an unknown `securityType2` is rejected
# and the ticker degrades to `unverifiable_identity`, which is the honest
# outcome. The debug log below is what makes such a blind spot findable.
_HOME_LINE_SECURITY_TYPES = frozenset(
    {
        "Common Stock",
        "REIT",
        "Preference",
        "Depositary Receipt",
    }
)


class OpenFIGIClientImpl:
    """Thin OpenFIGI /v3 wrapper (Master ADR-BF-2). Keyless by default; an API key
    raises the rate limit. Fail-loud: 429/5xx after retries -> DataSourceError,
    never a swallowed empty result (failure != empty, ADR-BF-5)."""

    _BASE = "https://api.openfigi.com/v3/"
    _MAX_ATTEMPTS = 4

    def __init__(
        self,
        api_key: str = "",
        *,
        sleep: Callable[[float], None] | None = None,
    ) -> None:
        self._headers = {"Content-Type": "application/json"}
        if api_key:
            self._headers["X-OPENFIGI-APIKEY"] = api_key
        self._sleep = sleep if sleep is not None else time.sleep

    def _post(self, path: str, payload: Any) -> Any:
        for attempt in range(1, self._MAX_ATTEMPTS + 1):
            try:
                resp = httpx.post(
                    self._BASE + path, json=payload, headers=self._headers, timeout=25
                )
            except Exception as exc:
                raise DataSourceError(f"OpenFIGI request failed: {exc}") from exc
            if resp.status_code == 200:
                return resp.json()
            if (
                resp.status_code in (429, 500, 502, 503, 504)
                and attempt < self._MAX_ATTEMPTS
            ):
                retry_after = (resp.headers or {}).get("Retry-After")
                wait = int(retry_after) if (retry_after or "").isdigit() else 2**attempt
                logger.warning(
                    "OpenFIGI %s for %s — retry %d/%d",
                    resp.status_code,
                    path,
                    attempt,
                    self._MAX_ATTEMPTS,
                )
                self._sleep(wait)
                continue
            raise DataSourceError(f"OpenFIGI returned {resp.status_code} for {path}")
        raise DataSourceError(f"OpenFIGI exhausted retries for {path}")

    def map_ticker(self, local: str, exch_code: str) -> dict | None:
        """The home line for one local symbol on one exchange.

        The `securityType2` filter moved from the REQUEST to the response:
        OpenFIGI takes a single value per request, so a server-side filter can
        only ever be an allow-list of one. Filtering here costs the same single
        call and lets `_HOME_LINE_SECURITY_TYPES` decide."""
        res = self._post(
            "mapping",
            [{"idType": "TICKER", "idValue": local, "exchCode": exch_code}],
        )
        first = res[0] if isinstance(res, list) and res else {}
        data = first.get("data") if isinstance(first, dict) else None
        if not data:
            return None
        for line in data:
            if (line.get("securityType2") or "") in _HOME_LINE_SECURITY_TYPES:
                return line
        logger.debug(
            "OpenFIGI %s/%s: %d line(s), none an accepted home-listing type (%s)",
            local,
            exch_code,
            len(data),
            sorted({str(line.get("securityType2")) for line in data}),
        )
        return None

    def lines_by_share_class(self, share_class_figi: str) -> list[dict]:
        """All listing lines of one share class, from the home line's own
        `shareClassFIGI`. Unlike /search this is a canonical identifier, so a
        single mapping call is complete (no `next` cursor, no pagination) and
        the caller needs no issuer-name comparison.

        Deliberately NO `securityType2` filter at all, not even the response-side
        allow-list `map_ticker` applies: the share class is already the anchor,
        and filtering would discard exactly the lines we are looking for (the
        sponsored ADR is a Depositary Receipt, the OTC foreign-ordinary line is
        not always 'Common Stock')."""
        res = self._post(
            "mapping",
            [
                {
                    "idType": "ID_BB_GLOBAL_SHARE_CLASS_LEVEL",
                    "idValue": share_class_figi,
                }
            ],
        )
        first = res[0] if isinstance(res, list) and res else {}
        data = first.get("data") if isinstance(first, dict) else None
        return data if isinstance(data, list) else []
