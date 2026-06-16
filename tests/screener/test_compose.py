from unittest.mock import patch

import app.screener.compose as compose_module


def test_build_screener_pipeline_wires_components():
    with (
        patch("app.screener.compose.YFinanceClientImpl") as mock_yf_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedYFinanceClient") as mock_cached_cls,
        patch("app.screener.compose.settings", spec=True) as mock_settings,
    ):
        mock_settings.gcp_project_id = "test-project"
        mock_settings.ticker_collection = "dev_ticker_cache"

        result = compose_module.build_screener_pipeline()

        mock_yf_cls.assert_called_once_with()
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            yfinance=mock_yf_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_ticker_cache",
        )
        assert result == mock_cached_cls.return_value


def test_build_edgar_pipeline_wires_components():
    with (
        patch("app.screener.compose.EdgarClientImpl") as mock_edgar_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedEdgarClient") as mock_cached_cls,
        patch("app.screener.compose.settings", spec=True) as mock_settings,
    ):
        mock_settings.edgar_user_agent = "Test Agent <test@example.com>"
        mock_settings.edgar_max_requests_per_second = 8.0
        mock_settings.gcp_project_id = "test-project"
        mock_settings.edgar_collection = "dev_edgar_cache"

        result = compose_module.build_edgar_pipeline()

        mock_edgar_cls.assert_called_once_with(
            user_agent="Test Agent <test@example.com>",
            max_requests_per_second=8.0,
        )
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            edgar=mock_edgar_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_edgar_cache",
        )
        assert result == mock_cached_cls.return_value


def test_build_gemini_pipeline_wires_components():
    with (
        patch("app.screener.compose.GeminiClientImpl") as mock_gemini_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedGeminiClient") as mock_cached_cls,
        patch("app.screener.compose.settings", spec=True) as mock_settings,
    ):
        mock_settings.gemini_api_key = "test-key"
        mock_settings.gcp_project_id = "test-project"
        mock_settings.gemini_score_collection = "dev_gemini_scores"
        mock_settings.gemini_model = "gemini-2.5-flash-lite"
        mock_settings.gemini_score_cache_ttl_days = 2

        result = compose_module.build_gemini_pipeline()

        mock_gemini_cls.assert_called_once_with(api_key="test-key", model="gemini-2.5-flash-lite")
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            gemini=mock_gemini_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_gemini_scores",
            ttl_days=2,
        )
        assert result == mock_cached_cls.return_value


def test_build_run_tracker_wires_components():
    with (
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.RunTracker") as mock_tracker_cls,
        patch("app.screener.compose.settings", spec=True) as mock_settings,
    ):
        mock_settings.gcp_project_id = "test-project"
        mock_settings.screener_runs_collection = "dev_screener_runs"

        result = compose_module.build_run_tracker()

        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_tracker_cls.assert_called_once_with(
            firestore=mock_fs_cls.return_value,
            collection="dev_screener_runs",
        )
        assert result == mock_tracker_cls.return_value


def test_build_github_client_wires_components():
    with (
        patch("app.screener.compose.GitHubClientImpl") as mock_cls,
        patch("app.screener.compose.settings") as mock_settings,
    ):
        mock_settings.github_token = "tok"
        mock_settings.github_repo = "org/repo"
        mock_settings.github_branch = "main"

        result = compose_module.build_github_client()

        mock_cls.assert_called_once_with(token="tok", repo="org/repo", branch="main")
        assert result == mock_cls.return_value


def test_build_revenue_series_cache_wires_components():
    with (
        patch("app.screener.compose.YFinanceClientImpl") as mock_yf_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedRevenueSeries") as mock_cached_cls,
        patch("app.screener.compose.settings", spec=True) as mock_settings,
    ):
        mock_settings.gcp_project_id = "test-project"
        mock_settings.revenue_series_collection = "dev_revenue_series"
        mock_settings.revenue_series_ttl_days = 400

        result = compose_module.build_revenue_series_cache()

        mock_yf_cls.assert_called_once_with()
        mock_fs_cls.assert_called_once_with(project_id="test-project")
        mock_cached_cls.assert_called_once_with(
            yfinance=mock_yf_cls.return_value,
            firestore=mock_fs_cls.return_value,
            collection="dev_revenue_series",
            ttl_days=400,
        )
        assert result == mock_cached_cls.return_value
