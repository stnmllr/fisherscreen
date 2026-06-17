import app.deepdive.compose as deepdive_compose
import app.screener.compose as screener_compose


def test_build_adr_table_returns_seed():
    table = deepdive_compose.build_adr_table()
    assert "NOVO-B.CO" in table
    assert table["NOVO-B.CO"]["adr_ticker"] == "NVO"


def test_github_client_builder_is_reused_not_duplicated():
    # Tool B shares Tool A's GitHub push path — same builder, no copy.
    assert deepdive_compose.build_github_client is screener_compose.build_github_client


def test_build_adr_resolver_resolves_seed():
    from unittest.mock import patch

    from app.deepdive.compose import build_adr_resolver

    # NOVO-B.CO is a static-table (override) hit -> edgar/eu_resolver never invoked.
    # Patch the config-dependent construction (UA, OpenFIGI, yfinance), which is
    # absent in CI, so the table-override path stays the real thing under test
    # (mirrors the insider compose test).
    with patch("app.deepdive.compose.EdgarClientImpl"), \
         patch("app.deepdive.compose.OpenFIGIClientImpl"), \
         patch("app.deepdive.compose.YFinanceClientImpl"):
        assert build_adr_resolver().resolve("NOVO-B.CO").adr_ticker == "NVO"


def test_build_insider_fetcher_returns_cached_fetcher():
    from unittest.mock import patch

    from app.deepdive.compose import build_insider_fetcher
    from app.deepdive.insider_cache import CachedInsiderFetcher

    # Patch only the config-dependent construction: EdgarClientImpl requires a
    # non-empty SEC user agent (settings.edgar_user_agent), which is absent in CI.
    # The REAL CachedInsiderFetcher is still constructed, so the compose/cache
    # contract under test — returns a CachedInsiderFetcher that WRAPS the edgar
    # client — is preserved, not mocked into a tautology.
    with patch("app.deepdive.compose.EdgarClientImpl") as mock_edgar_cls:
        f = build_insider_fetcher()

    assert isinstance(f, CachedInsiderFetcher)
    assert f._edgar is mock_edgar_cls.return_value


def test_insider_lookback_setting_default():
    from app.config import settings
    assert settings.insider_lookback_days == 365
