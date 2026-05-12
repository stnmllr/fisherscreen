from unittest.mock import patch

import app.screener.compose as compose_module


def test_build_screener_pipeline_wires_components():
    with (
        patch("app.screener.compose.YFinanceClientImpl") as mock_yf_cls,
        patch("app.screener.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.screener.compose.CachedYFinanceClient") as mock_cached_cls,
        patch("app.screener.compose.settings") as mock_settings,
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
