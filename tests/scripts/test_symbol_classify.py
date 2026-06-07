from scripts.diagnose_symbol_contaminants import classify_info, isin_matches


def test_equity_info_is_equity():
    assert classify_info({"quoteType": "EQUITY", "marketCap": 1e9}) == "EQUITY"


def test_non_equity_is_contaminant():
    assert classify_info({"quoteType": "MUTUALFUND", "shortName": "3734810"}) == "CONTAMINANT"


def test_empty_or_missing_quotetype_is_inconclusive():
    assert classify_info({}) == "INCONCLUSIVE"
    assert classify_info({"marketCap": 1e9}) == "INCONCLUSIVE"   # no quoteType
    assert classify_info({"quoteType": None}) == "INCONCLUSIVE"


def test_isin_matches_normalizes_and_compares():
    assert isin_matches("fr0000131104", "FR0000131104 ") is True
    assert isin_matches("FR0000131104", "FR0000120271") is False


def test_isin_matches_false_when_either_missing():
    assert isin_matches(None, "FR0000131104") is False
    assert isin_matches("FR0000131104", None) is False
