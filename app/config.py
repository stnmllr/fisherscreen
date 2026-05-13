from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in EdgarClientImpl
    gemini_token_cap: int = 500_000
    gemini_api_key: str = ""
    apify_api_key: str = ""
    github_token: str = ""
    ticker_collection: str = "dev_ticker_cache"
    edgar_collection: str = "dev_edgar_cache"
    gemini_score_collection: str = "dev_gemini_scores"
    screener_runs_collection: str = "dev_screener_runs"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
