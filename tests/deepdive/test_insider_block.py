from app.deepdive.insider_block import render_insider_block, insider_coverage_label
from app.models.deep_dive_record import InsiderSummary, InsiderTransaction


def test_fpi_and_skipped_and_failed_and_empty_states():
    assert "nicht anwendbar" in render_insider_block(
        InsiderSummary(coverage_state="fpi_exempt"), "20-F")
    assert "--no-insider" in render_insider_block(
        InsiderSummary(coverage_state="skipped"), "10-K")
    failed = render_insider_block(
        InsiderSummary(coverage_state="fetch_failed", n_filings_total=122), "10-K")
    assert "fehlgeschlagen" in failed and "kein Urteil" in failed
    empty = render_insider_block(InsiderSummary(coverage_state="empty"), "10-K")
    assert "0 Form-4" in empty


def test_ok_denominator_line_uses_explicit_units():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=122, n_parsed=122,
        n_transactions_total=140, immaterial_sell_count=10, routine_count=127,
        significant_sells=[InsiderTransaction(
            owner_name="Doe Jane", role="CFO", code="S", bucket="sell",
            date="2026-05-14", shares=1000, price=400.0, value=400_000,
            acquired_disposed="D", shares_after=9000, direct_or_indirect="D",
            is_10b5_1=True, significant=True)],
        significant_buys=[InsiderTransaction(
            owner_name="Roe Sam", role="CEO", code="P", bucket="buy",
            shares=500, price=400.0, value=200_000, acquired_disposed="A",
            shares_after=1500, direct_or_indirect="D", significant=True)],
    )
    out = render_insider_block(s, "10-K")
    assert "122 Form-4-Filings" in out and "140 Transaktionen" in out
    assert "2 signifikant" in out
    assert "10 immateriell" in out and "127 Routine" in out
    assert "−10%" in out
    assert "+50%" in out
    assert "10b5-1-geplant" in out


def test_percent_suffix_failsoft_omits_on_indirect_or_missing():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=1, n_parsed=1, n_transactions_total=1,
        significant_sells=[InsiderTransaction(
            owner_name="X", role="CFO", code="S", bucket="sell",
            shares=1000, price=400.0, value=400_000, acquired_disposed="D",
            shares_after=9000, direct_or_indirect="I", significant=True)],
    )
    assert "%" not in render_insider_block(s, "10-K").split("Transaktionen")[1]


def test_coverage_label_states():
    assert "nicht anwendbar" in insider_coverage_label(
        InsiderSummary(coverage_state="fpi_exempt"))
    assert "übersprungen" in insider_coverage_label(
        InsiderSummary(coverage_state="skipped"))


def test_aggregate_owner_significant_entries_are_grouped():
    def _sell(v):
        return InsiderTransaction(
            owner_name="Smith B", role="Officer", code="S", bucket="sell",
            date="2025-05-01", shares=100, price=v / 100, value=v,
            acquired_disposed="D", direct_or_indirect="D", shares_after=900,
            significant=True)
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=2, n_parsed=2, n_transactions_total=2,
        significant_sells=[_sell(600_000), _sell(600_000)])
    out = render_insider_block(s, "10-K")
    assert out.count("Smith B (Officer)") == 1  # owner header once, not per line
    constituent_lines = [ln for ln in out.splitlines() if ln.startswith("  - ")]
    assert len(constituent_lines) == 2


def test_single_owner_significant_stays_flat():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=1, n_parsed=1, n_transactions_total=1,
        significant_sells=[InsiderTransaction(
            owner_name="Solo X", role="CFO", code="S", bucket="sell",
            date="2026-01-01", shares=100, price=10.0, value=1000,
            acquired_disposed="D", direct_or_indirect="D", shares_after=900,
            significant=True)])
    out = render_insider_block(s, "10-K")
    assert "- Solo X (CFO) 2026-01-01:" in out   # flat, owner inline
    assert "\n  - " not in out                    # no indented constituent lines
