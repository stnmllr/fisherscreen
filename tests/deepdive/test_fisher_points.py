from app.deepdive.fisher_points import FISHER_POINTS


def test_fifteen_points_numbered_1_to_15():
    assert [n for n, _ in FISHER_POINTS] == list(range(1, 16))


def test_titles_are_nonempty_strings():
    assert all(isinstance(t, str) and t for _, t in FISHER_POINTS)


def test_point_14_15_are_openness_and_integrity():
    titles = dict(FISHER_POINTS)
    assert "Offenheit" in titles[14]
    assert "Integrität" in titles[15]
