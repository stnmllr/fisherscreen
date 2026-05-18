from app.config import FisherScreenSettings


def test_reads_gcp_project_from_env(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GCP_PROJECT_ID", "test-project-123")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gcp_project_id == "test-project-123"


def test_gcp_project_defaults_to_empty():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gcp_project_id == ""


def test_reads_edgar_user_agent(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_EDGAR_USER_AGENT", "TestAgent/1.0 test@test.com")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_user_agent == "TestAgent/1.0 test@test.com"


def test_edgar_user_agent_defaults_to_empty():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_user_agent == ""


def test_reads_gemini_api_key(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_API_KEY", "api-key-xyz")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_api_key == "api-key-xyz"


def test_gemini_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("FISHERSCREEN_GEMINI_API_KEY", raising=False)
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_api_key == ""


def test_reads_apify_api_key(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_APIFY_API_KEY", "apify-key-abc")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.apify_api_key == "apify-key-abc"


def test_apify_api_key_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("FISHERSCREEN_APIFY_API_KEY", raising=False)
    settings = FisherScreenSettings(_env_file=None)
    assert settings.apify_api_key == ""


def test_reads_github_token(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GITHUB_TOKEN", "ghp_token123")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_token == "ghp_token123"


def test_github_token_defaults_to_empty(monkeypatch):
    monkeypatch.delenv("FISHERSCREEN_GITHUB_TOKEN", raising=False)
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_token == ""


def test_reads_gemini_token_cap(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_TOKEN_CAP", "250000")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_token_cap == 250000


def test_gemini_token_cap_default():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_token_cap == 500_000


def test_reads_ticker_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_TICKER_COLLECTION", "prod_ticker_cache")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.ticker_collection == "prod_ticker_cache"


def test_ticker_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.ticker_collection == "dev_ticker_cache"


def test_reads_edgar_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_EDGAR_COLLECTION", "prod_edgar_cache")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_collection == "prod_edgar_cache"


def test_edgar_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.edgar_collection == "dev_edgar_cache"


def test_reads_gemini_score_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_SCORE_COLLECTION", "prod_gemini_scores")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_score_collection == "prod_gemini_scores"


def test_gemini_score_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_score_collection == "dev_gemini_scores"


def test_reads_screener_runs_collection(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_SCREENER_RUNS_COLLECTION", "prod_screener_runs")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.screener_runs_collection == "prod_screener_runs"


def test_screener_runs_collection_defaults_to_dev():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.screener_runs_collection == "dev_screener_runs"


def test_crosshits_score_threshold_defaults_to_4():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_score_threshold == 4.0


def test_reads_crosshits_score_threshold(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_CROSSHITS_SCORE_THRESHOLD", "4.5")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_score_threshold == 4.5


def test_crosshits_min_dimensions_defaults_to_2():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_min_dimensions == 2


def test_crosshits_cap_defaults_to_50():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_cap == 50


def test_output_dir_defaults_to_output():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.output_dir == "output"


def test_reads_github_repo(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GITHUB_REPO", "stnmllr/fisherscreen")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_repo == "stnmllr/fisherscreen"


def test_github_branch_defaults_to_main():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_branch == "main"


def test_deepdive_settings_defaults():
    from app.config import FisherScreenSettings
    s = FisherScreenSettings()
    assert s.deepdive_gemini_model == "gemini-2.5-pro"
    assert s.deepdive_token_cap == 200_000
    assert s.filing_cache_ttl_days == 30
    assert s.historical_cache_ttl_days == 90
