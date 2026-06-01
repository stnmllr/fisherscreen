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
    from app.deepdive.compose import build_adr_resolver
    assert build_adr_resolver().resolve("NOVO-B.CO").adr_ticker == "NVO"


def test_build_insider_fetcher_returns_cached_fetcher():
    from app.deepdive.compose import build_insider_fetcher
    from app.deepdive.insider_cache import CachedInsiderFetcher
    f = build_insider_fetcher()
    assert isinstance(f, CachedInsiderFetcher)


def test_insider_lookback_setting_default():
    from app.config import settings
    assert settings.insider_lookback_days == 365
