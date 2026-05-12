from app.config import settings
from app.services.cached_yfinance_client import CachedYFinanceClient
from app.services.firestore_client import FirestoreClientImpl
from app.services.yfinance_client import YFinanceClient, YFinanceClientImpl


def build_screener_pipeline() -> YFinanceClient:
    yfinance = YFinanceClientImpl()
    firestore = FirestoreClientImpl(project_id=settings.gcp_project_id)
    return CachedYFinanceClient(
        yfinance=yfinance,
        firestore=firestore,
        collection=settings.ticker_collection,
    )
