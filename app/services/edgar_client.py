import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RawFiling:
    accession_number: str
    document_text: str


class EdgarClient(Protocol):
    def get_cik(self, ticker: str) -> str | None: ...
    def has_restatement(self, cik: str, years: int = 3) -> bool: ...
    def has_going_concern(self, cik: str, months: int = 24) -> bool: ...
    def has_active_enforcement(self, cik: str) -> bool: ...
    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling: ...


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
        self._ticker_map: dict[str, str] | None = None

    def _get(self, url: str) -> dict[str, Any]:
        time.sleep(self._RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(url, headers=self._headers, timeout=30)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.json()

    def _load_ticker_map(self) -> dict[str, str]:
        """Fetch SEC company_tickers.json and return a TICKER -> CIK string map."""
        url = "https://www.sec.gov/files/company_tickers.json"
        data = self._get(url)
        return {entry["ticker"].upper(): str(entry["cik_str"]) for entry in data.values()}

    def get_cik(self, ticker: str) -> str | None:
        """Return the SEC CIK for ticker, or None if not found or on fetch failure.

        The ticker map is loaded lazily on first call and cached for the lifetime
        of this client instance to avoid repeated HTTP requests.
        """
        if self._ticker_map is None:
            try:
                self._ticker_map = self._load_ticker_map()
            except DataSourceError as exc:
                logger.warning("edgar: failed to load ticker map: %s — CIK lookup disabled", exc)
                self._ticker_map = {}  # empty dict prevents repeated retries
        return self._ticker_map.get(ticker.upper())

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

    def _get_text(self, url: str) -> str:
        time.sleep(self._RATE_LIMIT_SECONDS)
        try:
            resp = httpx.get(url, headers=self._headers, timeout=60)
        except Exception as exc:
            raise DataSourceError(f"EDGAR HTTP request failed: {exc}") from exc
        if resp.status_code != 200:
            raise DataSourceError(f"EDGAR returned {resp.status_code} for {url}")
        return resp.text

    def get_latest_annual_filing(self, cik: str, form_type: str) -> RawFiling:
        padded = cik.zfill(10)
        data = self._get(f"{self._SEC_BASE}/submissions/CIK{padded}.json")
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accessions = recent.get("accessionNumber", [])
        primary_docs = recent.get("primaryDocument", [])
        for form, accession, primary in zip(forms, accessions, primary_docs):
            if form == form_type:
                cik_int = str(int(cik))
                acc_nodash = accession.replace("-", "")
                url = (
                    f"https://www.sec.gov/Archives/edgar/data/"
                    f"{cik_int}/{acc_nodash}/{primary}"
                )
                text = self._get_text(url)
                return RawFiling(accession_number=accession, document_text=text)
        raise DataSourceError(
            f"no {form_type} filing found for CIK {padded} in recent submissions"
        )
