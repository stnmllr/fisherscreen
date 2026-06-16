from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in EdgarClientImpl
    edgar_max_requests_per_second: float = 8.0  # SEC fair-access limit is 10 req/s; 8 is conservative
    gemini_api_key: str = ""
    apify_api_key: str = ""
    github_token: str = ""
    gemini_token_cap: int = 1_500_000
    ticker_collection: str = "dev_ticker_cache"
    edgar_collection: str = "dev_edgar_cache"
    gemini_score_collection: str = "dev_gemini_scores"
    screener_runs_collection: str = "dev_screener_runs"
    crosshits_score_threshold: float = 4.0
    crosshits_min_dimensions: int = 3
    crosshits_cap: int = 50
    output_dir: str = "output"
    github_repo: str = ""
    github_branch: str = "main"
    gemini_model: str = "gemini-2.5-flash-lite"
    deepdive_gemini_model: str = "gemini-2.5-pro"
    deepdive_token_cap: int = 200_000
    filing_cache_ttl_days: int = 30
    historical_cache_ttl_days: int = 90
    gemini_score_cache_ttl_days: int = 2  # < monthly cadence so each monthly run re-scores fresh
    revenue_series_collection: str = "dev_revenue_series"
    revenue_series_ttl_days: int = 400  # annual revenue changes yearly; long TTL is correct here
    insider_lookback_days: int = 365
    deepdive_peers_collection: str = "dev_deepdive_peers"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
