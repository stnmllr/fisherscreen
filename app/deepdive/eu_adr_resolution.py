from __future__ import annotations

from typing import TYPE_CHECKING

from app.errors import DeepDiveError

if TYPE_CHECKING:
    from app.services.openfigi_client import OpenFIGIClient

# Home-exchange codes per Yahoo suffix (lifted from the dual-line audit).
SUFFIX_HOME_EXCH: dict[str, list[str]] = {
    "SW": ["SW", "VX"], "DE": ["GY", "GR"], "PA": ["FP"], "MC": ["SM"],
    "L": ["LN"], "AS": ["NA"], "CO": ["DC"], "VI": ["AV"], "WA": ["PW"],
    "BR": ["BB"], "ST": ["SS"], "HE": ["FH"], "OL": ["NO"], "MI": ["IM"],
    "IR": ["ID"], "AT": ["GA"], "LS": ["PL"],
}
# US exchange codes for the ADR line (audit "(US)" bucket).
US_EXCH = {"US", "UN", "UW", "UQ", "UR", "UA", "UV", "PQ"}

_LEGAL_FORMS = (
    " AG", " SA", " S.A.", " N.V.", " NV", " PLC", " SE", " SPA", " S.P.A.",
    " ASA", " AB", " OYJ", " A/S", " HOLDING", " GROUP", " INC", " LTD",
    " LIMITED", " COMPANY", " HLDG", " HLDGS",
)


def norm_issuer(name: str) -> str:
    """Normalise an issuer name for equality matching: drop legal forms + spaces.
    'ROCHE HOLDING AG' -> 'ROCHEHOLDING'; 'ROCHE BOBOIS SA' -> 'ROCHEBOBOIS'
    (stays distinct -> Bobois noise excluded)."""
    n = (name or "").upper()
    for legal in _LEGAL_FORMS:
        n = n.replace(legal, " ")
    return "".join(n.split())


def issuer_name(figi_name: str) -> str:
    """Issuer identity from an OpenFIGI security name: strip a trailing
    '-CLASSTOKEN' whose token has no space ('ROCHE HOLDING AG-BR' -> 'ROCHE
    HOLDING AG'); the no-space guard keeps hyphenated real names ('COCA-COLA
    CO')."""
    n = (figi_name or "").upper().strip()
    if "-" in n:
        head, _, tail = n.rpartition("-")
        if head and tail and " " not in tail:
            return head.strip()
    return n


def home_exch_codes(ticker: str) -> list[str]:
    suffix = ticker.rsplit(".", 1)[1] if "." in ticker else ""
    return SUFFIX_HOME_EXCH.get(suffix.upper(), [])


def local_symbol_variants(ticker: str) -> list[str]:
    """Ordered candidate local symbols for OpenFIGI (the variant ladder against
    the documented NVO miss: 'NOVO B'/'NOVOB' instead of the dashed form)."""
    base = ticker.rsplit(".", 1)[0] if "." in ticker else ticker
    variants = [base, base.replace("-", " "), base.replace("-", "")]
    return list(dict.fromkeys(variants))  # order-preserving dedup


def find_home_identity(ticker: str, ref_norm: str, *, openfigi: "OpenFIGIClient") -> dict:
    """Variant ladder + NAME-SANITY-CHECK: accept the first candidate whose
    OpenFIGI issuer name matches the reference (ADR-EU-2). Never 'first answer
    wins' — guards the variant-ladder false hit (ROCHE -> ROCHE BOBOIS)."""
    for exch in home_exch_codes(ticker):
        for cand in local_symbol_variants(ticker):
            ident = openfigi.map_ticker(cand, exch)
            if ident and norm_issuer(issuer_name(ident.get("name", ""))) == ref_norm:
                return ident
    raise DeepDiveError(
        f"{ticker}: no verifiable OpenFIGI identity (no candidate local symbol "
        f"matched the reference issuer name) — fail-loud, no unverified match."
    )


def _same_issuer(line_name: str, ident_norm: str) -> bool:
    """Prefix-tolerant issuer match for US lines. ADR line names carry listing
    descriptors the home identity lacks ('ASML HOLDING NV-NY REG SHS',
    'SAP SE-SPONSORED ADR'), so strict norm-equality against the home identity
    ('ASML HOLDING NV') wrongly drops the ADR line. The home-issuer norm is a
    prefix of the ADR-line norm — accept when either is a prefix of the other."""
    ln = norm_issuer(issuer_name(line_name))
    return bool(ln) and (ln.startswith(ident_norm) or ident_norm.startswith(ln))


def pick_us_adr_line(lines: list[dict], ident_norm: str) -> dict | None:
    """Among the issuer's US-listed lines, prefer the Depositary-Receipt line;
    else the first US line. None if the issuer has no US listing (pure-EU,
    EU-Native gap). Operative output downstream is the CIK (consistent across
    lines per the pre-flight); the chosen ticker also serves as adr_ticker."""
    us = [
        ln for ln in lines
        if (ln.get("exchCode") or "").strip() in US_EXCH
        and _same_issuer(ln.get("name", ""), ident_norm)
    ]
    if not us:
        return None
    for ln in us:
        if (ln.get("securityType2") or "") == "Depositary Receipt":
            return ln
    return us[0]
