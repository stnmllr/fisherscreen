from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from app.config import settings
from app.deepdive.adr_resolver import ADRResolver
from app.deepdive.adr_table import load_adr_table
from app.deepdive.eu_adr_resolution import resolve_eu_adr
from app.deepdive.filing_cache import CachedFilingFetcher
from app.deepdive.historical_cache import CachedHistoricalData
from app.deepdive.insider_cache import CachedInsiderFetcher
from app.deepdive.peer_preflight import resolve_peers
from app.deepdive.peer_suggest import PeerSuggestion, suggest_peers
from app.deepdive.preflight import PreflightResult, SymbolCheck, run_preflight
from app.deepdive.quant_join import build_quant_snapshot
from app.screener.compose import build_github_client
from app.screener.monthly import _load_universe
from app.services.edgar_client import EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
from app.services.github_client import GitHubClientImpl
from app.services.openfigi_client import OpenFIGIClientImpl
from app.services.gemini_deepdive_client import GeminiDeepDiveClient
from app.services.historical_data_service import HistoricalDataServiceImpl
from app.services.yfinance_client import YFinanceClientImpl

__all__ = [
    "build_adr_table",
    "build_github_client",
    "build_adr_resolver",
    "build_openfigi_client",
    "build_eu_resolver",
    "build_filing_fetcher",
    "build_insider_fetcher",
    "build_quant_builder",
    "build_peer_resolver",
    "build_peer_suggester",
    "build_preflight_runner",
    "build_synthesizer",
]

_FILING_CACHE_DIR = Path("cache/filings")
_HISTORICAL_CACHE_DIR = Path("cache/yfinance_historical")
_INSIDER_CACHE_DIR = Path("cache/insider")
_ADR_CACHE_PATH = Path("cache/adr_resolved.json")


def build_adr_table() -> dict[str, dict[str, str]]:
    return load_adr_table()


def build_openfigi_client() -> OpenFIGIClientImpl:
    return OpenFIGIClientImpl(api_key=settings.openfigi_api_key)


def build_eu_resolver() -> Callable[[str], Any]:
    openfigi = build_openfigi_client()
    edgar = EdgarClientImpl(
        user_agent=settings.edgar_user_agent,
        annual_form_max_age_days=settings.annual_form_max_age_days,
    )
    yfinance = YFinanceClientImpl()

    def _resolve(ticker: str):
        return resolve_eu_adr(
            ticker,
            openfigi=openfigi,
            edgar=edgar,
            yfinance=yfinance,
            cache_path=_ADR_CACHE_PATH,
            ttl_days=settings.adr_cache_ttl_days,
            negative_ttl_days=settings.adr_negative_cache_ttl_days,
        )

    return _resolve


def _build_resolver_edgar() -> EdgarClientImpl:
    return EdgarClientImpl(
        user_agent=settings.edgar_user_agent,
        annual_form_max_age_days=settings.annual_form_max_age_days,
    )


def build_adr_resolver(edgar: EdgarClientImpl | None = None) -> ADRResolver:
    """`edgar` lets a caller share the client with a later map check
    (build_preflight_runner) — otherwise a fresh client is built."""
    if edgar is None:
        edgar = _build_resolver_edgar()
    return ADRResolver(
        table=load_adr_table(), edgar=edgar, eu_resolver=build_eu_resolver()
    )


def build_preflight_runner() -> Callable[[str, list[str]], PreflightResult]:
    """Return a callable running the deep-dive pre-flight check.

    Every call builds FRESH dependencies: EdgarClientImpl remembers a failed
    SEC ticker-map load for its lifetime, so a long-lived UI process holding
    one instance would report every US ticker as unknown after a single SEC
    hiccup. Resolver and map check share ONE EdgarClientImpl, so the check
    asks about exactly the map the resolver used."""

    def _run(ticker: str, peers: list[str]) -> PreflightResult:
        edgar = _build_resolver_edgar()
        return run_preflight(
            ticker,
            peers,
            resolver=build_adr_resolver(edgar=edgar),
            yfinance=YFinanceClientImpl(),
            edgar_map_available=edgar.ticker_map_available,
            suggest=build_peer_suggester(),
        )

    return _run


def build_peer_suggester() -> Callable[[SymbolCheck, list[str]], list[PeerSuggestion]]:
    """Return the peer-suggestion callable for the pre-flight check.

    Firestore is constructed INSIDE the callable: it only runs when peer slots
    are empty, and an ADC/Firestore failure then surfaces as DataSourceError
    right there, where the pre-flight reports it as "nicht abrufbar" instead
    of failing the whole check."""

    def _suggest(ticker_check: SymbolCheck, exclude: list[str]) -> list[PeerSuggestion]:
        return suggest_peers(
            ticker_check,
            exclude,
            firestore=FirestoreClientImpl(project_id=settings.gcp_project_id),
            collection=settings.ticker_collection,
            universe=frozenset(_load_universe()),
            fx_rate=YFinanceClientImpl().get_fx_rate,
        )

    return _suggest


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

    def _resolve(
        *, ticker: str, peers_arg: str | None, rationale_arg: str | None, is_tty: bool
    ) -> Any:
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


def build_dossier_publisher() -> GitHubClientImpl | None:
    """GitHub client for the dossier repo, or None when publishing is not configured.

    Raises DataSourceError (from the client) when a repo is set but the token is empty.
    """
    if not settings.dossier_repo:
        return None
    return GitHubClientImpl(
        token=settings.dossier_token,
        repo=settings.dossier_repo,
        branch=settings.dossier_branch,
    )
