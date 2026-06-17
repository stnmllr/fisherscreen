from unittest.mock import MagicMock

import pytest

from app.errors import DeepDiveError


def test_norm_issuer_folds_legal_forms_and_spaces():
    from app.deepdive.eu_adr_resolution import norm_issuer
    assert norm_issuer("ASML Holding N.V.") == norm_issuer("ASML HOLDING NV")
    assert norm_issuer("ROCHE HOLDING AG") != norm_issuer("ROCHE BOBOIS SA")


def test_issuer_name_strips_class_token():
    from app.deepdive.eu_adr_resolution import issuer_name
    assert issuer_name("ROCHE HOLDING AG-BR") == "ROCHE HOLDING AG"
    assert issuer_name("COCA-COLA CO") == "COCA-COLA CO"  # hyphen with space kept


def test_local_symbol_variants_for_dashed_ticker():
    from app.deepdive.eu_adr_resolution import local_symbol_variants
    assert local_symbol_variants("NOVO-B.CO") == ["NOVO-B", "NOVO B", "NOVOB"]


def test_home_exch_codes_from_suffix():
    from app.deepdive.eu_adr_resolution import home_exch_codes
    assert home_exch_codes("NOVO-B.CO") == ["DC"]
    assert home_exch_codes("SAP.DE") == ["GY", "GR"]


def test_find_home_identity_accepts_only_name_match():
    # Wrong candidate returns a foreign issuer -> rejected; right one accepted.
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer
    openfigi = MagicMock()
    openfigi.map_ticker.side_effect = [
        {"name": "ROCHE BOBOIS SA"},          # NOVO-B  -> foreign, rejected
        {"name": "NOVO NORDISK A/S-B"},       # NOVO B  -> matches, accepted
    ]
    ref = norm_issuer("Novo Nordisk A/S")
    ident = find_home_identity("NOVO-B.CO", ref, openfigi=openfigi)
    assert ident["name"] == "NOVO NORDISK A/S-B"


def test_find_home_identity_fail_loud_when_no_match():
    from app.deepdive.eu_adr_resolution import find_home_identity, norm_issuer
    openfigi = MagicMock()
    openfigi.map_ticker.return_value = None
    with pytest.raises(DeepDiveError, match="no verifiable OpenFIGI"):
        find_home_identity("XX-Y.CO", norm_issuer("Whatever Inc"), openfigi=openfigi)


def test_pick_us_adr_line_prefers_depositary_receipt():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line, norm_issuer, issuer_name
    ident_norm = norm_issuer(issuer_name("ASML HOLDING NV"))
    lines = [
        {"ticker": "ASMLF", "exchCode": "US", "securityType2": "Common Stock", "name": "ASML HOLDING NV"},
        {"ticker": "ASML", "exchCode": "US", "securityType2": "Depositary Receipt", "name": "ASML HOLDING NV-NY REG SHS"},
        {"ticker": "ASML", "exchCode": "GY", "securityType2": "Common Stock", "name": "ASML HOLDING NV"},
    ]
    assert pick_us_adr_line(lines, ident_norm)["ticker"] == "ASML"


def test_pick_us_adr_line_none_when_no_us_line():
    from app.deepdive.eu_adr_resolution import pick_us_adr_line, norm_issuer
    lines = [{"ticker": "RMV", "exchCode": "LN", "securityType2": "Common Stock", "name": "RIGHTMOVE PLC"}]
    assert pick_us_adr_line(lines, norm_issuer("RIGHTMOVE PLC")) is None
