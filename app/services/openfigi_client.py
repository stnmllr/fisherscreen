from __future__ import annotations

import logging
import time
from typing import Any, Callable, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


class OpenFIGIClient(Protocol):
    def map_ticker(self, local: str, exch_code: str) -> dict | None: ...
    def search_issuer(self, name: str) -> list[dict]: ...
    def lines_by_share_class(self, share_class_figi: str) -> list[dict]: ...


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
        res = self._post(
            "mapping",
            [
                {
                    "idType": "TICKER",
                    "idValue": local,
                    "exchCode": exch_code,
                    "securityType2": "Common Stock",
                }
            ],
        )
        first = res[0] if isinstance(res, list) and res else {}
        data = first.get("data") if isinstance(first, dict) else None
        return data[0] if data else None

    def search_issuer(self, name: str) -> list[dict]:
        res = self._post("search", {"query": name, "marketSecDes": "Equity"})
        return res.get("data", []) if isinstance(res, dict) else []

    def lines_by_share_class(self, share_class_figi: str) -> list[dict]:
        """All listing lines of one share class, from the home line's own
        `shareClassFIGI`. Unlike /search this is a canonical identifier, so a
        single mapping call is complete (no `next` cursor, no pagination) and
        the caller needs no issuer-name comparison.

        Deliberately NO `securityType2` filter, unlike `map_ticker`: the share
        class is already the anchor, and pre-filtering would discard exactly the
        lines we are looking for (the sponsored ADR is a Depositary Receipt, the
        OTC foreign-ordinary line is not always 'Common Stock')."""
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
