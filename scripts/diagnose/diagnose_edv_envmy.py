"""Diagnose (one-off): why is the ENVMY Depositary-Receipt line not preferred,
and would preferring it change the outcome?

The `_same_issuer` half of this trace is gone with the function: the US line is
now anchored on the home line's shareClassFIGI, so there is no issuer-name
comparison left on that path to diagnose. What remains — how the two spellings
normalise, and what EDGAR knows about the symbols — is the part that still
answers the question."""

from __future__ import annotations

from app.config import settings
from app.deepdive.eu_adr_resolution import issuer_name, norm_issuer, same_issuer_identity
from app.services.edgar_client import EdgarClientImpl

IDENT = "ENDEAVOUR MINING PLC"
print("ident norm            :", norm_issuer(IDENT))
for nm in ("ENDEAVOUR MINING PLC", "ENDEAVOUR MNG PLC-UNSPON ADR"):
    print(f"{nm!r}")
    print("   issuer_name        ->", issuer_name(nm))
    print("   norm               ->", norm_issuer(nm))
    print("   same_issuer_identity ->", same_issuer_identity(nm, IDENT))

edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
for t in ("EDVMF", "ENVMY", "EDV"):
    print(f"edgar.get_cik({t!r}) -> {edgar.get_cik(t)!r}")
print("detect_annual_form('0002139860') ->", edgar.detect_annual_form("0002139860"))
