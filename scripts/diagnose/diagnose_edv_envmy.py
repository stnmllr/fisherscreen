"""Diagnose (one-off): why is the ENVMY Depositary-Receipt line not preferred,
and would preferring it change the outcome?"""
from __future__ import annotations
from app.config import settings
from app.deepdive.eu_adr_resolution import _same_issuer, issuer_name, norm_issuer
from app.services.edgar_client import EdgarClientImpl

IDENT = "ENDEAVOUR MINING PLC"
ident_norm = norm_issuer(issuer_name(IDENT))
print("ident_norm            :", ident_norm)
for nm in ("ENDEAVOUR MINING PLC", "ENDEAVOUR MNG PLC-UNSPON ADR"):
    print(f"{nm!r}")
    print("   issuer_name ->", issuer_name(nm))
    print("   norm        ->", norm_issuer(issuer_name(nm)))
    print("   _same_issuer->", _same_issuer(nm, ident_norm))

edgar = EdgarClientImpl(user_agent=settings.edgar_user_agent)
for t in ("EDVMF", "ENVMY", "EDV"):
    print(f"edgar.get_cik({t!r}) -> {edgar.get_cik(t)!r}")
print("detect_annual_form('0002139860') ->", edgar.detect_annual_form("0002139860"))
