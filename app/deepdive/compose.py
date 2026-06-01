from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.deepdive.adr_resolver import ADRResolver
from app.deepdive.adr_table import load_adr_table
from app.deepdive.filing_cache import CachedFilingFetcher
from app.deepdive.historical_cache import CachedHistoricalData
from app.deepdive.insider_cache import CachedInsiderFetcher
from app.deepdive.peer_preflight import resolve_peers
from app.deepdive.quant_join import build_quant_snapshot
from app.screener.compose import build_github_client
from app.services.edgar_client import EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
from app.services.gemini_deepdive_client import GeminiDeepDiveClient
from app.services.historical_data_service import HistoricalDataServiceImpl
from app.services.yfinance_client import YFinanceClientImpl

__all__ = [
    "build_adr_table",
    "build_github_client",
    "build_adr_resolver",
    "build_filing_fetcher",
    "build_insider_fetcher",
    "build_quant_builder",
    "build_peer_resolver",
    "build_synthesizer",
]

_FILING_CACHE_DIR = Path("cache/filings")
_HISTORICAL_CACHE_DIR = Path("cache/yfinance_historical")
_INSIDER_CACHE_DIR = Path("cache/insider")


def build_adr_table() -> dict[str, dict[str, str]]:
    return load_adr_table()


def build_adr_resolver() -> ADRResolver:
    return ADRResolver(table=load_adr_table())


def build_filing_fetcher() -> CachedFilingFetcher:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return CachedFilingFetcher(
        edgar=edgar,
        cache_dir=_FILING_CACHE_DIR,
        ttl_days=settings.filing_cache_ttl_days,
    )


def build_insider_fetcher() -> CachedInsiderFetcher:
    edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
    return CachedInsiderFetcher(edgar=edgar, cache_dir=_INSIDER_CACHE_DIR)


def build_quant_builder() -> Callable[..., tuple[Any, Any]]:
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    yfinance = YFinanceClientImpl()
    historical = CachedHistoricalData(
        service=HistoricalDataServiceImpl(yfinance=yfinance),
        cache_dir=_HISTORICAL_CACHE_DIR,
        ttl_days=settings.historical_cache_ttl_days,
    )
    pit_collection = settings.ticker_collection
    dims_collection = settings.gemini_score_collection

    def _build(ticker: str, *, use_cache: bool = True):
        return build_quant_snapshot(
            ticker,
            firestore=firestore,
            yfinance=yfinance,
            historical=historical,
            pit_collection=pit_collection,
            dims_collection=dims_collection,
            use_cache=use_cache,
        )

    return _build


def build_peer_resolver() -> Callable[..., Any]:
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    yfinance = YFinanceClientImpl()
    peers_collection = settings.deepdive_peers_collection

    def _resolve(*, ticker: str, peers_arg: str | None,
                 rationale_arg: str | None, is_tty: bool) -> Any:
        return resolve_peers(
            ticker=ticker,
            peers_arg=peers_arg,
            rationale_arg=rationale_arg,
            is_tty=is_tty,
            firestore=firestore,
            peers_collection=peers_collection,
            yfinance=yfinance,
        )

    return _resolve


def build_synthesizer(model_override: str | None = None) -> GeminiDeepDiveClient:
    return GeminiDeepDiveClient(
        api_key=settings.gemini_api_key,
        model=model_override or settings.deepdive_gemini_model,
    )
