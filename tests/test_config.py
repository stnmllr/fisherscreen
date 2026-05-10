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


def test_reads_gemini_token_cap(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GEMINI_TOKEN_CAP", "250000")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_token_cap == 250000


def test_gemini_token_cap_default():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.gemini_token_cap == 500_000


def test_reads_apify_api_key(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_APIFY_API_KEY", "apify-key-abc")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.apify_api_key == "apify-key-abc"
