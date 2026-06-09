from app.screener.sector_buckets import resolve_bucket


def test_picks_finest_node_meeting_n_min():
    # chain finest->coarsest; counts per node; n_min=5
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 3, "Retailing": 9, "Consumer Discretionary": 40}
    assert resolve_bucket(chain, counts, n_min=5) == "Retailing"


def test_rolls_up_to_sector_when_all_thin_below():
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 1, "Retailing": 2, "Consumer Discretionary": 40}
    assert resolve_bucket(chain, counts, n_min=5) == "Consumer Discretionary"


def test_returns_none_when_even_sector_too_thin():
    # fail-safe: no bucket clears n_min -> None -> relative arm will not fire
    chain = ["Apparel Retail", "Retailing", "Consumer Discretionary"]
    counts = {"Apparel Retail": 1, "Retailing": 2, "Consumer Discretionary": 3}
    assert resolve_bucket(chain, counts, n_min=5) is None


def test_empty_chain_returns_none():
    assert resolve_bucket([], {}, n_min=5) is None
