from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in EdgarClientImpl
    gemini_api_key: str = ""
    apify_api_key: str = ""
    github_token: str = ""
    gemini_token_cap: int = 500_000
    ticker_collection: str = "dev_ticker_cache"
    edgar_collection: str = "dev_edgar_cache"
    gemini_score_collection: str = "dev_gemini_scores"
    screener_runs_collection: str = "dev_screener_runs"
    crosshits_score_threshold: float = 4.0
    crosshits_min_dimensions: int = 2
    crosshits_cap: int = 50
    output_dir: str = "output"
    github_repo: str = ""
    github_branch: str = "main"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
