import app.deepdive.compose as deepdive_compose
import app.screener.compose as screener_compose


def test_build_adr_table_returns_seed():
    table = deepdive_compose.build_adr_table()
    assert "NOVO-B.CO" in table
    assert table["NOVO-B.CO"]["adr_ticker"] == "NVO"


def test_github_client_builder_is_reused_not_duplicated():
    # Tool B shares Tool A's GitHub push path — same builder, no copy.
    assert deepdive_compose.build_github_client is screener_compose.build_github_client
