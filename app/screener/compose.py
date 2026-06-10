from app.config import settings
from app.screener.run_tracker import RunTracker
from app.screener.sector_buckets import SectorMedianTable
from app.screener.sector_median_table import load_sector_median_table
from app.services.cached_edgar_client import CachedEdgarClient
from app.services.cached_gemini_client import CachedGeminiClient
from app.services.cached_yfinance_client import CachedYFinanceClient
from app.services.edgar_client import EdgarClient, EdgarClientImpl
from app.services.firestore_client import FirestoreClientImpl
from app.services.gemini_client import GeminiClient, GeminiClientImpl
from app.services.github_client import GitHubClient, GitHubClientImpl
from app.services.yfinance_client import YFinanceClient, YFinanceClientImpl


def build_screener_pipeline() -> YFinanceClient:
    yfinance = YFinanceClientImpl()
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedYFinanceClient(
        yfinance=yfinance,
        firestore=firestore,
        collection=settings.ticker_collection,
    )


def build_edgar_pipeline() -> EdgarClient:
    edgar = EdgarClientImpl(
        user_agent=settings.edgar_user_agent,
        max_requests_per_second=settings.edgar_max_requests_per_second,
    )
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedEdgarClient(
        edgar=edgar,
        firestore=firestore,
        collection=settings.edgar_collection,
    )


def build_gemini_pipeline() -> GeminiClient:
    gemini = GeminiClientImpl(api_key=settings.gemini_api_key, model=settings.gemini_model)
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedGeminiClient(
        gemini=gemini,
        firestore=firestore,
        collection=settings.gemini_score_collection,
    )


def build_run_tracker() -> RunTracker:
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return RunTracker(
        firestore=firestore,
        collection=settings.screener_runs_collection,
    )


def build_github_client() -> GitHubClient:
    return GitHubClientImpl(
        token=settings.github_token,
        repo=settings.github_repo,
        branch=settings.github_branch,
    )


def build_sector_median_table() -> SectorMedianTable | None:
    """Load the pinned sector-median reference table from data/sector_median_table.json.

    Returns None when the file is absent (fail-safe: relative arm stays dormant
    until Phase E commits the calibrated table)."""
    return load_sector_median_table()
