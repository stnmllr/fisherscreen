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
    with (
        patch("app.deepdive.compose.EdgarClientImpl"),
        patch("app.deepdive.compose.OpenFIGIClientImpl"),
        patch("app.deepdive.compose.YFinanceClientImpl"),
    ):
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


def test_build_adr_resolver_uses_injected_edgar():
    from unittest.mock import MagicMock, patch

    from app.deepdive.compose import build_adr_resolver

    edgar = MagicMock()
    edgar.get_cik.return_value = "320193"
    edgar.detect_annual_form.return_value = "10-K"
    with (
        patch("app.deepdive.compose.EdgarClientImpl") as mock_edgar_cls,
        patch("app.deepdive.compose.OpenFIGIClientImpl"),
        patch("app.deepdive.compose.YFinanceClientImpl"),
    ):
        resolved = build_adr_resolver(edgar=edgar).resolve("AAPL")

    assert resolved.cik == "0000320193"
    edgar.get_cik.assert_called_once_with("AAPL")
    # only the EU delegate builds its own client; the US path uses ours
    assert mock_edgar_cls.call_count == 1


def test_build_preflight_runner_builds_fresh_shared_deps_per_call():
    from unittest.mock import MagicMock, patch

    from app.deepdive.compose import build_preflight_runner

    edgars = [MagicMock(name="edgar1"), MagicMock(name="edgar2")]
    seen: list[dict] = []

    def fake_run(ticker, peers, *, resolver, yfinance, edgar_map_available, suggest):
        seen.append(
            {
                "args": (ticker, peers),
                "resolver_edgar": resolver._edgar,
                "map_check": edgar_map_available,
                "yfinance": yfinance,
                "suggest": suggest,
            }
        )
        return "result"

    with (
        patch("app.deepdive.compose.EdgarClientImpl"),
        patch("app.deepdive.compose._build_resolver_edgar", side_effect=edgars),
        patch("app.deepdive.compose.OpenFIGIClientImpl"),
        patch("app.deepdive.compose.YFinanceClientImpl"),
        patch("app.deepdive.compose.run_preflight", side_effect=fake_run),
    ):
        runner = build_preflight_runner()
        assert seen == []  # nothing is built until a check runs
        assert runner("AAPL", ["MSFT", "GOOGL", "AMZN"]) == "result"
        assert runner("AAPL", ["MSFT", "GOOGL", "AMZN"]) == "result"

    assert seen[0]["args"] == ("AAPL", ["MSFT", "GOOGL", "AMZN"])
    for call, edgar in zip(seen, edgars):
        # resolver and map check share ONE client ...
        assert call["resolver_edgar"] is edgar
        assert call["map_check"] == edgar.ticker_map_available
    # ... and every check gets a fresh one
    assert seen[0]["resolver_edgar"] is not seen[1]["resolver_edgar"]
    assert all(callable(call["suggest"]) for call in seen)


def test_resolver_edgar_builder_passes_settings():
    from unittest.mock import patch

    from app.deepdive import compose

    with patch("app.deepdive.compose.EdgarClientImpl") as mock_edgar_cls:
        assert compose._build_resolver_edgar() is mock_edgar_cls.return_value
    kwargs = mock_edgar_cls.call_args.kwargs
    assert kwargs["user_agent"] == compose.settings.edgar_user_agent
    assert (
        kwargs["annual_form_max_age_days"] == compose.settings.annual_form_max_age_days
    )


def test_build_peer_suggester_builds_firestore_lazily_inside_call():
    from unittest.mock import patch

    from app.deepdive import compose
    from app.deepdive.preflight import SymbolCheck

    check = SymbolCheck("SAF.PA", True, "Safran", "EUR", 1e11, "ok", "A&D", "Ind")
    with (
        patch("app.deepdive.compose.FirestoreClientImpl") as mock_fs_cls,
        patch("app.deepdive.compose._load_universe", return_value=["SAF.PA", "AIR.PA"]),
        patch("app.deepdive.compose.suggest_peers", return_value=["s"]) as mock_sp,
        patch("app.deepdive.compose.YFinanceClientImpl") as mock_yf_cls,
    ):
        suggest = compose.build_peer_suggester()
        mock_fs_cls.assert_not_called()  # nothing touches Firestore at build time
        assert suggest(check, ["SAF.PA"]) == ["s"]

    mock_fs_cls.assert_called_once_with(project_id=compose.settings.gcp_project_id)
    mock_sp.assert_called_once_with(
        check,
        ["SAF.PA"],
        firestore=mock_fs_cls.return_value,
        collection=compose.settings.ticker_collection,
        universe=frozenset({"SAF.PA", "AIR.PA"}),
        fx_rate=mock_yf_cls.return_value.get_fx_rate,
    )


def test_build_peer_suggester_firestore_failure_raises_inside_call():
    from unittest.mock import patch

    import pytest

    from app.deepdive import compose
    from app.deepdive.preflight import SymbolCheck
    from app.errors import DataSourceError

    check = SymbolCheck("SAF.PA", True, "Safran", "EUR", 1e11, "ok", "A&D", "Ind")
    with patch(
        "app.deepdive.compose.FirestoreClientImpl",
        side_effect=DataSourceError("ADC not configured"),
    ):
        suggest = compose.build_peer_suggester()
        with pytest.raises(DataSourceError):
            suggest(check, [])
