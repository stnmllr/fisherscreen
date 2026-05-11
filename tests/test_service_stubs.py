def test_service_protocol_imports():
    from app.services.apify_client import ApifyClient
    from app.services.edgar_client import EdgarClient
    from app.services.firestore_client import FirestoreClient
    from app.services.gemini_client import GeminiClient
    from app.services.marketaux_client import MarketauxClient
    from app.services.yfinance_client import YFinanceClient

    assert all([
        ApifyClient, EdgarClient, FirestoreClient,
        GeminiClient, MarketauxClient, YFinanceClient,
    ])
