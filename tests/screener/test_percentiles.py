import pytest
from app.screener.percentiles import percentile_rank, percentile_to_score


def test_percentile_rank_midrank_handles_ties():
    dist = [1.0, 2.0, 2.0, 4.0]
    # below=1 (the 1.0), equal=2 (the two 2.0s) -> (1 + 0.5*2)/4 = 50.0
    assert percentile_rank(2.0, dist) == 50.0


def test_percentile_rank_max_and_min():
    dist = [10.0, 20.0, 30.0, 40.0]
    assert percentile_rank(40.0, dist) == pytest.approx(87.5)  # (3 + 0.5)/4
    assert percentile_rank(10.0, dist) == pytest.approx(12.5)  # (0 + 0.5)/4


def test_percentile_to_score_anchor_bands():
    assert percentile_to_score(95.0) == 5
    assert percentile_to_score(88.0) == 5
    assert percentile_to_score(87.9) == 4
    assert percentile_to_score(70.0) == 4
    assert percentile_to_score(69.9) == 3
    assert percentile_to_score(40.0) == 3
    assert percentile_to_score(39.9) == 2
    assert percentile_to_score(15.0) == 2
    assert percentile_to_score(14.9) == 1
