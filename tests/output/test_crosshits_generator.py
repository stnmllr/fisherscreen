from pathlib import Path

import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.crosshits_generator import generate


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {
        "growth": 3,
        "profitability": 3,
        "management": 3,
        "innovation": 3,
        "resilience": 3,
    }
    dims.update(dim_scores)
    return ScreenerRecord(
        ticker=ticker,
        name=f"{ticker} Corp",
        gics_sector="Technology",
        gemini_dimensions=dims,
    )


def _run_record() -> RunRecord:
    return RunRecord(run_id="2026-05-13T08:00:00+00:00")


def test_generate_creates_file(tmp_path):
    path = generate(
        [_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path
    )
    assert path.exists()


def test_generate_filename(tmp_path):
    path = generate(
        [_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path
    )
    assert path.name == "2026-05-Crosshits.md"


def test_generate_writes_to_universum_subdir(tmp_path):
    path = generate(
        [_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path
    )
    assert path.parent == tmp_path / "Universum"


def test_ticker_with_two_qualifying_dims_is_a_crosshit(tmp_path):
    records = [_record("AAPL", growth=4, profitability=4)]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    assert "AAPL" in path.read_text(encoding="utf-8")


def test_ticker_with_one_qualifying_dim_is_not_a_crosshit(tmp_path):
    records = [_record("SOLO", growth=5, profitability=3)]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    content = path.read_text(encoding="utf-8")
    assert "SOLO" not in content or "Keine Crosshits" in content


def test_empty_crosshits_produces_informative_message(tmp_path):
    records = [_record("LOW", growth=2, profitability=2)]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    assert "Keine Crosshits" in path.read_text(encoding="utf-8")


def test_crosshits_sorted_by_dimension_count_desc(tmp_path):
    records = [
        _record("THREE", growth=4, profitability=4, management=4),
        _record("TWO", growth=4, profitability=4),
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    content = path.read_text(encoding="utf-8")
    assert content.index("THREE") < content.index("TWO")


def test_crosshits_ranked_by_number_of_fives(tmp_path):
    # All three records are crosshits at min_dimensions=3 (all three merit axes >=4).
    # Within equal qualifying-dim count, more 5s ranks higher: 5/5/5 > 5/5/4 > 4/4/4.
    records = [
        _record("MID", growth=5, profitability=5, resilience=4),
        _record("TOP", growth=5, profitability=5, resilience=5),
        _record("LOW", growth=4, profitability=4, resilience=4),
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=3
    )
    content = path.read_text(encoding="utf-8")
    assert content.index("TOP") < content.index("MID") < content.index("LOW")


def test_cap_limits_crosshits_output(tmp_path):
    records = [_record(f"T{i}", growth=5, profitability=5) for i in range(60)]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2, cap=10
    )
    content = path.read_text(encoding="utf-8")
    table_rows = [
        l
        for l in content.splitlines()
        if l.startswith("| ") and "---" not in l and "#" not in l
    ]
    assert len(table_rows) <= 10


def test_management_innovation_do_not_create_crosshit(tmp_path):
    # Only growth is a merit hit; management/innovation maxed must not form a crosshit.
    records = [
        _record(
            "NOPE", growth=4, profitability=3, management=5, innovation=5, resilience=3
        )
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    content = path.read_text(encoding="utf-8")
    assert "Keine Crosshits" in content
    assert "NOPE" not in content


def test_management_innovation_do_not_inflate_qualifying_count(tmp_path):
    # Two merit hits → crosshit, but management/innovation must not be listed/counted.
    records = [
        _record(
            "REAL", growth=4, profitability=4, management=5, innovation=5, resilience=3
        )
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    content = path.read_text(encoding="utf-8")
    assert "REAL" in content
    assert "management" not in content
    assert "innovation" not in content
    # Crosshit count column reflects only the two merit dims.
    assert "| 2 | growth, profitability |" in content


def test_records_without_gemini_dimensions_are_excluded(tmp_path):
    records = [
        _record("SCORED", growth=5, profitability=5),
        ScreenerRecord(ticker="UNSCORED"),
    ]
    path = generate(
        records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2
    )
    assert "UNSCORED" not in path.read_text(encoding="utf-8")


def test_header_injected_after_title(tmp_path):
    records = []
    path = generate(
        records,
        _run_record(),
        tmp_path,
        score_threshold=4.0,
        min_dimensions=2,
        header="## Lauf-Übersicht 2026-06\n\nHEADER_MARKER\n",
    )
    text = path.read_text("utf-8")
    assert "HEADER_MARKER" in text
    title_idx = text.index("# Universum")
    header_idx = text.index("HEADER_MARKER")
    schwelle_idx = text.index("*Schwelle")
    assert (
        title_idx < header_idx < schwelle_idx
    )  # header between title and threshold note


from app.output.crosshits_generator import _flags  # helper added in this task


def test_flags_global_fallback_and_low_confidence():
    from app.models.screener_record import ScreenerRecord

    r = ScreenerRecord(
        ticker="X",
        score_basis={
            "growth": "global",
            "profitability": "global_fallback",
            "resilience": "sector_relative",
        },
        data_confidence="low",
    )
    out = _flags(r)
    assert "⌖" in out  # global fallback on >=1 sector-relative axis
    assert "⚠" in out  # low data confidence


def test_flags_clean_record_empty():
    from app.models.screener_record import ScreenerRecord

    r = ScreenerRecord(
        ticker="Y",
        score_basis={
            "growth": "global",
            "profitability": "sector_relative",
            "resilience": "sector_relative",
        },
        data_confidence="ok",
    )
    assert _flags(r) == ""


def test_flags_partial_evidence_marker():
    from app.models.screener_record import ScreenerRecord

    r = ScreenerRecord(
        ticker="X",
        score_basis={
            "growth": "global",
            "profitability": "sector_relative",
            "resilience": "sector_relative",
        },
        data_confidence="ok",
        partial_evidence_axes=["profitability"],
    )
    assert "~" in _flags(r)


# --- price-taker exclusion -------------------------------------------------
#
# Since 2026-10 a price taker is no crosshit (the rule lives in `is_crosshit`,
# the flag is set by the scorer). The report keeps the judgement visible in a
# section of its own; the former "Preisnehmer" column would only ever read "nein".
#
# The September 2026 crosshits, with the yfinance `industry` each carried when
# the list was measured (2026-09-07). Captured rather than fetched so the test
# stays offline and deterministic; if yfinance relabels a title, the marking
# changes in production and this fixture goes stale — which is a reason to
# re-measure, not a reason to fetch at test time.
SEPTEMBER_INDUSTRIES = {
    "EDV.L": "Gold",
    "FICO": "Software - Application",
    "HL": "Other Precious Metals & Mining",
    "NEM": "Gold",
    "NVDA": "Semiconductors",
    "PLTR": "Software - Infrastructure",
    "RGLD": "Gold",
    "TDG": "Aerospace & Defense",
    "TPL": "Oil & Gas E&P",
    "ABNB": "Travel Services",
    "ARGX.BR": "Biotechnology",
    "META": "Internet Content & Information",
    "MU": "Semiconductors",
    "SNDK": "Computer Hardware",
    "ADYEN.AS": "Software - Infrastructure",
    "ANTO.L": "Copper",
    "FAST": "Industrial Distribution",
    "G24.DE": "Internet Content & Information",
    "GOOG": "Internet Content & Information",
    "GOOGL": "Internet Content & Information",
    "MEDP": "Diagnostics & Research",
    "MNST": "Beverages - Non-Alcoholic",
    "TER": "Semiconductor Equipment & Materials",
    "WISE.L": "Information Technology Services",
}

# Named by hand from the September list. The tests below assert these are all
# excluded; they deliberately do NOT assert how many there are, so the config
# can grow without a test needing to be touched.
SEPTEMBER_PRICE_TAKERS = (
    "EDV.L",
    "HL",
    "NEM",
    "RGLD",
    "ANTO.L",
    "TPL",
    "MU",
    "SNDK",
)


def _september_records():
    """The September crosshits, flagged against the committed table the way the
    scorer flags them in production."""
    from app.screener.price_takers import is_price_taker, load_price_takers

    table = load_price_takers()
    records = []
    for ticker, industry in SEPTEMBER_INDUSTRIES.items():
        record = _industry_record(ticker, industry)
        record.price_taker = is_price_taker(ticker, industry, table)
        records.append(record)
    return records


def _industry_record(ticker: str, industry: str) -> ScreenerRecord:
    return ScreenerRecord(
        ticker=ticker,
        name=f"{ticker} Corp",
        gics_sector="Technology",
        gics_industry=industry,
        gemini_dimensions={
            "growth": 4,
            "profitability": 4,
            "management": 3,
            "innovation": 3,
            "resilience": 4,
        },
    )


_TAKER_HEADING = "## Am Preisnehmer-Ausschluss gescheitert"


def _taker_section(text: str) -> str:
    return text.split(_TAKER_HEADING)[1] if _TAKER_HEADING in text else ""


def _crosshit_table(text: str) -> set[str]:
    """Tickers of the crosshit table only -- everything before the first
    failure section."""
    head = text.split("\n## ")[0]
    if "| Ticker |" not in head:
        return set()
    return set(_marks_col(head, "Stetigkeit"))


def test_the_crosshit_table_has_no_price_taker_column(tmp_path):
    """A price taker is no crosshit any more -- the column would always read
    'nein'."""
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    head = path.read_text(encoding="utf-8").split(_TAKER_HEADING)[0]
    assert "Preisnehmer |" not in head


def test_the_september_price_takers_are_all_excluded(tmp_path):
    """The acceptance case. A subset assertion, not an equality: naming a ninth
    price taker later must not turn this red."""
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    text = path.read_text(encoding="utf-8")
    assert set(SEPTEMBER_PRICE_TAKERS).isdisjoint(_crosshit_table(text))
    section = _marks_col(_taker_section(text), "Stetigkeit")
    assert set(SEPTEMBER_PRICE_TAKERS) <= set(section)


def test_the_section_lists_exactly_the_flagged_would_be_crosshits(tmp_path):
    """Derived from the committed table, not restated: extend
    data/price_takers.json and this test follows without an edit."""
    records = _september_records()
    path = generate(records, _run_record(), tmp_path, min_dimensions=3)
    text = path.read_text(encoding="utf-8")
    takers = {r.ticker for r in records if r.price_taker}
    assert set(_marks_col(_taker_section(text), "Stetigkeit")) == takers
    assert _crosshit_table(text) == set(SEPTEMBER_INDUSTRIES) - takers


def test_the_shared_semiconductor_industry_is_not_dragged_in(tmp_path):
    """MU is caught by ticker override; NVDA and TER share or neighbour its
    yfinance industry and must stay crosshits -- otherwise the override was
    written as an industry rule by mistake."""
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    text = path.read_text(encoding="utf-8")
    assert "| MU " in _taker_section(text)
    for ticker in ("NVDA", "TER", "FICO", "MEDP", "FAST"):
        assert ticker in _crosshit_table(text), ticker


def test_a_price_taker_failing_an_axis_is_not_in_the_section(tmp_path):
    """The section holds titles that would be crosshits but for the exclusion.
    A price taker that also misses an axis fails on merit, not on the rule."""
    weak = _industry_record("NEM", "Gold")
    weak.gemini_dimensions["resilience"] = 3
    weak.price_taker = True
    hit = _industry_record("RGLD", "Gold")
    hit.price_taker = True
    text = generate([weak, hit], _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert set(_marks_col(_taker_section(text), "Stetigkeit")) == {"RGLD"}


def test_a_price_taker_failing_on_steadiness_stays_in_the_steadiness_section(
    tmp_path,
):
    record = _steady_record("NEM", 1.33, industry="Gold")
    record.price_taker = True
    text = generate([record], _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert _TAKER_HEADING not in text
    assert "| NEM " in text.split(_FAILED_HEADING)[1]


def test_the_section_names_the_industry_or_the_override(tmp_path):
    from app.screener.price_takers import PriceTakerTable

    gold = _industry_record("NEM", "Gold")
    gold.price_taker = True
    mu = _industry_record("MU", "Semiconductors")
    mu.price_taker = True
    table = PriceTakerTable(industries=frozenset({"Gold"}), tickers=frozenset({"MU"}))
    text = generate(
        [gold, mu], _run_record(), tmp_path, min_dimensions=3, price_takers=table
    ).read_text("utf-8")
    cells = _marks_col(_taker_section(text), "Grund")
    assert cells == {"NEM": "Gold", "MU": "Override"}
    assert "**keine** Crosshits" in _taker_section(text)


def test_no_price_taker_section_when_nobody_is_excluded(tmp_path):
    path = generate(
        [_steady_record("FAST", 5.0)], _run_record(), tmp_path, min_dimensions=3
    )
    assert _TAKER_HEADING not in path.read_text(encoding="utf-8")


def test_price_taker_section_follows_the_leverage_section(tmp_path):
    taker = _industry_record("RGLD", "Gold")
    taker.price_taker = True
    records = [
        taker,
        _levered_record("TDG"),
        _steady_record("TER", 2.67),
        _steady_record("FAST", 5.0),
    ]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert (
        text.index(_FAILED_HEADING)
        < text.index(_LEVERAGE_HEADING)
        < text.index(_TAKER_HEADING)
    )
    assert "RGLD" not in text.split(_TAKER_HEADING)[0]


def test_a_flagged_price_taker_that_clears_the_bar_is_not_in_the_leverage_section(
    tmp_path,
):
    """min_dimensions=2: growth + profitability suffice, so the red flag is not
    what keeps it out -- the price-taker rule is."""
    record = _levered_record("XOM")
    record.price_taker = True
    text = generate([record], _run_record(), tmp_path, min_dimensions=2).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text
    assert "| XOM " in _taker_section(text)


def _marks_col(text: str, column: str) -> dict[str, str]:
    """ticker -> the value in the named column."""
    header = next(line for line in text.splitlines() if "| Ticker |" in line)
    columns = [c.strip() for c in header.strip("|").split("|")]
    ticker_at, mark_at = columns.index("Ticker"), columns.index(column)
    marks = {}
    for line in text.splitlines():
        if not line.startswith("| ") or "| Ticker |" in line or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(columns):
            continue
        marks[cells[ticker_at].split()[0]] = cells[mark_at]
    return marks


# --- steadiness column -----------------------------------------------------


def _steady_record(ticker, score, reason=None, industry="Software - Application"):
    record = _industry_record(ticker, industry)
    record.steadiness = score
    record.steadiness_reason = reason
    return record


def test_the_table_has_a_steadiness_column(tmp_path):
    path = generate(
        [_steady_record("FAST", 5.0)], _run_record(), tmp_path, min_dimensions=3
    )
    assert "| Stetigkeit |" in path.read_text(encoding="utf-8")


def test_an_assessed_title_shows_its_score(tmp_path):
    path = generate(
        [_steady_record("MEDP", 4.67)], _run_record(), tmp_path, min_dimensions=3
    )
    assert _marks_col(path.read_text(encoding="utf-8"), "Stetigkeit")["MEDP"] == "4.67"


def test_an_unassessed_title_shows_na_with_a_reason_marker_never_the_three(tmp_path):
    """Showing the sentinel 3 would be the visible half of the mistake the gate
    avoids: it looks like a measurement and is not one."""
    records = [
        _steady_record("EDV", 3.0, reason="no_sec_registrant"),
        _steady_record("RGLD", 3.0, reason="series_too_short"),
        _steady_record("XOM", 3.0, reason="no_concept"),
    ]
    cells = _marks_col(
        generate(records, _run_record(), tmp_path, min_dimensions=3).read_text("utf-8"),
        "Stetigkeit",
    )

    assert cells["EDV"] == "n/a ∅"
    assert cells["RGLD"] == "n/a ↧"
    assert cells["XOM"] == "n/a ⊘"
    assert "3.0" not in set(cells.values())


def test_a_measured_three_is_shown_as_a_number_not_as_na(tmp_path):
    path = generate(
        [_steady_record("CYC", 3.0)], _run_record(), tmp_path, min_dimensions=3
    )
    assert _marks_col(path.read_text(encoding="utf-8"), "Stetigkeit")["CYC"] == "3.0"


def test_the_legend_names_how_many_of_the_list_are_assessed(tmp_path):
    records = [
        _steady_record("FAST", 5.0),
        _steady_record("EDV", 3.0, reason="no_sec_registrant"),
    ]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )

    assert "**1 von 2** Titeln dieser Liste sind bewertet" in text
    assert "weder belohnt noch bestraft" in text


# --- the list obeys the same gate as the funnel ------------------------------
#
# October 2026: the table listed 25 titles, the funnel counted 17. The eight
# extra were exactly the titles whose MEASURED steadiness was below 4.0 -- the
# table applied only the three-axis rule. These tests pin the table to
# `is_crosshit`, the rule the funnel counts with.

_FAILED_HEADING = "## Am Stetigkeits-Gate gescheitert"


def _main_table(text: str) -> dict[str, str]:
    """ticker -> Stetigkeit cell, for the crosshit table only (not the
    steadiness-failure section below it)."""
    return _marks_col(text.split(_FAILED_HEADING)[0], "Stetigkeit")


def test_a_measured_steadiness_below_the_threshold_is_not_a_crosshit(tmp_path):
    records = [_steady_record("TER", 2.67), _steady_record("FAST", 5.0)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )

    assert set(_main_table(text)) == {"FAST"}


def test_a_title_failing_on_steadiness_is_shown_in_its_own_section(tmp_path):
    records = [_steady_record("TER", 2.67), _steady_record("FAST", 5.0)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )

    assert _FAILED_HEADING in text
    failed = _marks_col(text.split(_FAILED_HEADING)[1], "Stetigkeit")
    assert failed == {"TER": "2.67"}


def test_an_unassessed_steadiness_does_not_block_a_crosshit(tmp_path):
    """Neutral means neither reward nor penalty (spec 8): no SEC history keeps
    the title on the list."""
    records = [_steady_record("EDV", 3.0, reason="no_sec_registrant")]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )

    assert set(_main_table(text)) == {"EDV"}
    assert _FAILED_HEADING not in text


def test_no_failure_section_when_nobody_fails_on_steadiness(tmp_path):
    path = generate(
        [_steady_record("FAST", 5.0)], _run_record(), tmp_path, min_dimensions=3
    )
    assert _FAILED_HEADING not in path.read_text(encoding="utf-8")


def test_the_list_and_the_funnel_agree_on_the_september_titles(tmp_path):
    """The spec 10.2 regression set: the table must hold exactly the titles
    `is_crosshit` accepts -- the funnel's count -- and nothing else."""
    from app.screener.dimensions import is_crosshit

    measured = {
        "NEM": 1.33,
        "MU": 1.33,
        "ABNB": 2.0,
        "HL": 2.33,
        "TER": 2.67,
        "PLTR": 2.67,
        "TPL": 3.67,
        "META": 3.67,
        "NVDA": 4.0,
        "TDG": 4.0,
        "GOOG": 4.67,
        "GOOGL": 4.67,
        "MEDP": 4.67,
        "MNST": 4.67,
        "FAST": 5.0,
        "FICO": 5.0,
    }
    records = []
    for ticker, industry in SEPTEMBER_INDUSTRIES.items():
        if ticker in measured:
            records.append(_steady_record(ticker, measured[ticker], industry=industry))
        else:
            records.append(
                _steady_record(
                    ticker, 3.0, reason="no_sec_registrant", industry=industry
                )
            )

    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )

    funnel_hits = {r.ticker for r in records if is_crosshit(r, 4.0, 3)}
    assert set(_main_table(text)) == funnel_hits
    assert {"NEM", "MU", "ABNB", "HL", "TER", "PLTR", "TPL", "META"}.isdisjoint(
        _main_table(text)
    )


# --- leverage red-flag failures ----------------------------------------------
#
# A title that clears growth + profitability (and steadiness, where measured)
# but is held to resilience 0 by the net debt/EBITDA > 4.0x red flag is not a
# crosshit. It is listed in its own section so the decision stays visible.

_LEVERAGE_HEADING = "## Am Verschuldungs-Red-Flag gescheitert"


def _levered_record(
    ticker,
    *,
    growth=5,
    profitability=5,
    steadiness=3.0,
    reason="no_sec_registrant",
    flag="net_debt_to_ebitda_above_4",
    total_debt=6.0e9,
    ebitda=1.0e9,
):
    record = _industry_record(ticker, "Aerospace & Defense")
    record.gemini_dimensions = {
        "growth": growth,
        "profitability": profitability,
        "management": 3,
        "innovation": 3,
        "resilience": 0,
    }
    record.resilience_red_flag = flag
    record.total_debt = total_debt
    record.total_cash = 0.0
    record.ebitda = ebitda
    record.steadiness = steadiness
    record.steadiness_reason = reason
    return record


def _leverage_section(text: str) -> str:
    return text.split(_LEVERAGE_HEADING)[1] if _LEVERAGE_HEADING in text else ""


def test_a_leverage_red_flag_title_is_listed_in_its_own_section(tmp_path):
    records = [_levered_record("TDG", steadiness=4.0, reason=None)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    section = _leverage_section(text)
    assert "| TDG " in section
    assert "6.0x" in section
    assert "| Nettoverschuldung/EBITDA |" in section
    assert "4.0x" in section  # threshold named in the blockquote
    assert "**keine** Crosshits" in section


def test_leverage_section_with_nonpositive_ebitda(tmp_path):
    records = [
        _levered_record("NEG", flag="net_debt_with_nonpositive_ebitda", ebitda=-5.0)
    ]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert "| Nettoschuld, EBITDA ≤ 0 |" in _leverage_section(text)


def test_measured_failing_steadiness_excludes_from_leverage_section(tmp_path):
    records = [_levered_record("CYC", steadiness=2.0, reason=None)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text


def test_low_growth_excludes_from_leverage_section(tmp_path):
    records = [_levered_record("SLOW", growth=3)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text


def test_low_profitability_excludes_from_leverage_section(tmp_path):
    records = [_levered_record("THIN", profitability=3)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text


def test_unflagged_resilience_failure_is_not_in_leverage_section(tmp_path):
    records = [_levered_record("LOWGM", flag=None)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text


def test_leverage_failures_are_not_crosshits(tmp_path):
    records = [_levered_record("TDG"), _steady_record("FAST", 5.0)]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    main = _marks_col(text.split(_LEVERAGE_HEADING)[0], "Stetigkeit")
    assert set(main) == {"FAST"}
    assert "| TDG " in _leverage_section(text)


def test_leverage_section_follows_steadiness_section(tmp_path):
    records = [
        _levered_record("TDG"),
        _steady_record("TER", 2.67),
        _steady_record("FAST", 5.0),
    ]
    text = generate(records, _run_record(), tmp_path, min_dimensions=3).read_text(
        "utf-8"
    )
    assert text.index(_FAILED_HEADING) < text.index(_LEVERAGE_HEADING)
    assert "TDG" not in text.split(_FAILED_HEADING)[1].split(_LEVERAGE_HEADING)[0]


def test_a_flagged_title_that_is_a_crosshit_is_not_listed_as_failed(tmp_path):
    # local experiments run min_dimensions=2: growth + profitability suffice
    records = [_levered_record("TDG")]
    text = generate(records, _run_record(), tmp_path, min_dimensions=2).read_text(
        "utf-8"
    )
    assert _LEVERAGE_HEADING not in text


_PRIOR_RUN_WARNING = "> ⚠️ **Vorlauf unvollständig:** Lauf X endete mit `running`."


def test_prior_run_warning_is_first_line(tmp_path):
    path = generate(
        [_record("AAPL", growth=5, profitability=4)],
        _run_record(),
        tmp_path,
        header="## Lauf-Übersicht",
        prior_run_warning=_PRIOR_RUN_WARNING,
    )
    content = path.read_text(encoding="utf-8")
    assert content.startswith(_PRIOR_RUN_WARNING + "\n\n# Universum")


def test_no_prior_run_warning_by_default(tmp_path):
    path = generate([_record("AAPL", growth=5)], _run_record(), tmp_path)
    content = path.read_text(encoding="utf-8")
    assert content.startswith("# Universum")
    assert "Vorlauf" not in content
