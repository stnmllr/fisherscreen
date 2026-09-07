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


# --- price-taker column ----------------------------------------------------
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
# marked; they deliberately do NOT assert how many there are, so the config can
# grow without a test needing to be touched.
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
    return [
        _industry_record(ticker, industry)
        for ticker, industry in SEPTEMBER_INDUSTRIES.items()
    ]


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


def _marks(text: str) -> dict[str, str]:
    """ticker -> the value in the Preisnehmer column."""
    header = next(line for line in text.splitlines() if "| Ticker |" in line)
    columns = [c.strip() for c in header.strip("|").split("|")]
    ticker_at, mark_at = columns.index("Ticker"), columns.index("Preisnehmer")
    marks = {}
    for line in text.splitlines():
        if not line.startswith("| ") or "| Ticker |" in line or set(line) <= set("|- "):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != len(columns):
            continue
        marks[cells[ticker_at].split()[0]] = cells[mark_at]
    return marks


def test_the_table_has_a_price_taker_column(tmp_path):
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    assert "| Preisnehmer |" in path.read_text(encoding="utf-8")


def test_every_configured_price_taker_in_the_table_is_marked(tmp_path):
    """The expectation is derived from the committed config, not restated here:
    extend data/price_takers.json and this test follows without an edit."""
    from app.screener.price_takers import is_price_taker, load_price_takers

    table = load_price_takers()
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    marks = _marks(path.read_text(encoding="utf-8"))

    assert marks, "no rows rendered - the fixture stopped producing crosshits"
    for ticker, industry in SEPTEMBER_INDUSTRIES.items():
        expected = "ja" if is_price_taker(ticker, industry, table) else "nein"
        assert marks[ticker] == expected, ticker


def test_the_september_price_takers_are_all_caught(tmp_path):
    """The acceptance case from the brief. A subset assertion, not an equality:
    naming a ninth price taker later must not turn this red."""
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    marks = _marks(path.read_text(encoding="utf-8"))

    unmarked = [t for t in SEPTEMBER_PRICE_TAKERS if marks[t] != "ja"]
    assert not unmarked, f"price takers left unmarked: {unmarked}"


def test_the_shared_semiconductor_industry_is_not_dragged_in(tmp_path):
    """MU is marked by ticker override, NVDA and TER share or neighbour its
    yfinance industry and must stay unmarked -- otherwise the override was
    written as an industry rule by mistake."""
    path = generate(_september_records(), _run_record(), tmp_path, min_dimensions=3)
    marks = _marks(path.read_text(encoding="utf-8"))

    assert marks["MU"] == "ja"
    for ticker in ("NVDA", "TER", "FICO", "MEDP", "FAST"):
        assert marks[ticker] == "nein", ticker


def test_marking_changes_no_score_and_drops_no_title(tmp_path):
    """The column is a label. Same titles, same scores, with and without it."""
    from app.screener.price_takers import PriceTakerTable

    records = _september_records()
    marked = generate(records, _run_record(), tmp_path / "a", min_dimensions=3)
    unmarked = generate(
        records,
        _run_record(),
        tmp_path / "b",
        min_dimensions=3,
        price_takers=PriceTakerTable(industries=frozenset(), tickers=frozenset()),
    )

    def rows(text):
        return [
            line.rsplit("|", 2)[0]  # drop the Preisnehmer cell and the trailing pipe
            for line in text.splitlines()
            if line.startswith("| ") and "Ticker" not in line
        ]

    assert rows(marked.read_text("utf-8")) == rows(unmarked.read_text("utf-8"))
