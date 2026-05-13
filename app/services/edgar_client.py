import logging
import time
from datetime import date, timedelta
from typing import Any, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


class EdgarClient(Protocol):
    def has_restatement(self, cik: str, years: int = 3) -> bool: ...
    def has_going_concern(self, cik: str, months: int = 24) -> bool: ...
    def has_active_enforcement(self, cik: str) -> bool: ...


class EdgarClientImpl:
    _SEC_BASE = "https://data.sec.gov"
    _EFTS_BASE = "https://efts.sec.gov"
    _RATE_LIMIT_SECONDS = 0.5

    def __init__(self, user_agent: str) -> None:
        if not user_agent:
            raise DataSourceError(
                "EDGAR user agent not set — configure FISHERSCREEN_EDGAR_USER_AGENT"
            )
        self._headers = {"User-Agent": user_agent}

    def _get(self, url: str) -> dict[str, Any]:
        time.sleep(self._RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(url, headers=self._headers, timeout=30)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.json()

    def has_restatement(self, cik: str, years: int = 3) -> bool:
        padded = cik.zfill(10)
        url = f"{self._SEC_BASE}/submissions/CIK{padded}.json"
        data = self._get(url)
        cutoff = (date.today() - timedelta(days=years * 365)).isoformat()
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        items_list = recent.get("items", [])
        for form, filing_date, items in zip(forms, dates, items_list):
            if form == "8-K" and filing_date >= cutoff and "4.02" in str(items):
                return True
        return False

    def has_going_concern(self, cik: str, months: int = 24) -> bool:
        padded = cik.zfill(10)
        startdt = (date.today() - timedelta(days=months * 30)).isoformat()  # ~30 days/month approximation
        url = (
            f"{self._EFTS_BASE}/LATEST/search-index"
            f"?q=%22raise+substantial+doubt%22"
            f"&forms=10-K,10-Q"
            f"&dateRange=custom&startdt={startdt}"
            f"&entity={padded}"
        )
        data = self._get(url)
        return data.get("hits", {}).get("total", {}).get("value", 0) > 0

    def has_active_enforcement(self, cik: str) -> bool:
        logger.warning(
            "has_active_enforcement not implemented — returning False for cik=%s", cik
        )
        return False
