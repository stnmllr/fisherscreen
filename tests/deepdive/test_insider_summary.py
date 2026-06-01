from app.deepdive.insider_summary import compute_insider_summary
from app.models.deep_dive_record import InsiderTransaction


def _t(owner, role, code, bucket, value, ad, **kw):
    return InsiderTransaction(
        owner_name=owner, role=role, code=code, bucket=bucket,
        value=value, acquired_disposed=ad, **kw
    )


def test_three_bucket_netting_and_reconciliation():
    txns = [
        _t("A", "CEO", "P", "buy", 500_000, "A"),
        _t("B", "Officer", "S", "sell", 2_000_000, "D"),
        _t("C", "Officer", "S", "sell", 300_000, "D"),
        _t("D", "Officer", "F", "routine", None, "D"),
    ]
    s = compute_insider_summary(
        txns, coverage_state="ok", n_filings_total=4, n_parsed=4
    )
    assert len(s.significant_buys) == 1
    assert len(s.significant_sells) == 1
    assert s.immaterial_sell_count == 1
    assert s.routine_count == 1
    assert s.n_transactions_total == (
        len(s.significant_buys) + len(s.significant_sells)
        + s.immaterial_sell_count + s.routine_count
    )
    assert s.net_buy_value == 500_000
    assert s.net_sell_value == 2_000_000


def test_ceo_sell_significant_regardless_of_value():
    txns = [_t("X", "CFO", "S", "sell", 50_000, "D")]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=1, n_parsed=1)
    assert len(s.significant_sells) == 1 and s.immaterial_sell_count == 0


def test_per_owner_aggregate_marks_all_constituents():
    txns = [
        _t("Y", "Officer", "S", "sell", 400_000, "D"),
        _t("Y", "Officer", "S", "sell", 400_000, "D"),
        _t("Y", "Officer", "S", "sell", 400_000, "D"),
    ]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=3, n_parsed=3)
    assert len(s.significant_sells) == 3
    assert s.immaterial_sell_count == 0
    assert all(t.significant for t in s.significant_sells)


def test_by_role_aggregation():
    txns = [
        _t("A", "CEO", "P", "buy", 1_000_000, "A"),
        _t("B", "CFO", "S", "sell", 2_000_000, "D"),
    ]
    s = compute_insider_summary(txns, coverage_state="ok", n_filings_total=2, n_parsed=2)
    assert s.by_role["CEO"]["buy"] == 1_000_000
    assert s.by_role["CFO"]["sell"] == 2_000_000
