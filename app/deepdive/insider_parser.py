from __future__ import annotations

import logging
import xml.etree.ElementTree as ET

from app.models.deep_dive_record import (
    InsiderBucket,
    InsiderRole,
    InsiderTransaction,
)

logger = logging.getLogger(__name__)

_ROUTINE_CODES = {"A", "M", "F", "G"}
_CEO_TITLES = ("chief executive", "ceo", "principal executive officer")
_CFO_TITLES = ("chief financial", "cfo", "principal financial officer")


def classify_bucket(code: str, is_derivative: bool) -> InsiderBucket:
    if is_derivative:
        return "routine"  # derivatives are compensation by construction
    if code == "P":
        return "buy"
    if code == "S":
        return "sell"
    if code in _ROUTINE_CODES:
        return "routine"
    logger.warning("insider: unknown transactionCode %r -> routine bucket", code)
    return "routine"


def derive_role(
    officer_title: str | None,
    is_director: bool,
    is_officer: bool,
    is_ten_pct: bool,
) -> InsiderRole:
    """Display-only precedence (significance uses title+flags directly)."""
    t = (officer_title or "").lower()
    if any(k in t for k in _CEO_TITLES):
        return "CEO"
    if any(k in t for k in _CFO_TITLES):
        return "CFO"
    if is_officer:
        return "Officer"
    if is_director:
        return "Director"
    if is_ten_pct:
        return "TenPercentOwner"
    return "Other"


def _text(el: ET.Element | None, path: str) -> str | None:
    if el is None:
        return None
    found = el.find(path)
    return found.text.strip() if (found is not None and found.text) else None


def _float(el: ET.Element | None, path: str) -> float | None:
    raw = _text(el, path)
    if raw is None:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _flag(el: ET.Element | None, path: str) -> bool:
    return _text(el, path) == "1"


def _parse_10b5_1(root: ET.Element) -> bool | None:
    """aff10b5One/noAff10b5One pair (SEC schema). aff==1 -> True (planned);
    noAff==1 or aff==0 -> False; both absent -> None."""
    aff = _text(root, "aff10b5One")
    noaff = _text(root, "noAff10b5One")
    if aff == "1":
        return True
    if noaff == "1":
        return False
    if aff == "0":
        return False
    return None


def parse_form4(xml: str) -> list[InsiderTransaction]:
    """One reporting owner per Form-4; iterate non-derivative + derivative tables."""
    root = ET.fromstring(xml)
    owner = root.find("reportingOwner")
    owner_name = _text(owner, "reportingOwnerId/rptOwnerName") or "Unknown"
    rel = owner.find("reportingOwnerRelationship") if owner is not None else None
    is_director = _flag(rel, "isDirector")
    is_officer = _flag(rel, "isOfficer")
    is_ten_pct = _flag(rel, "isTenPercentOwner")
    officer_title = _text(rel, "officerTitle")
    role = derive_role(officer_title, is_director, is_officer, is_ten_pct)
    is_10b5_1 = _parse_10b5_1(root)

    txns: list[InsiderTransaction] = []
    for table, tag, is_deriv in (
        ("nonDerivativeTable", "nonDerivativeTransaction", False),
        ("derivativeTable", "derivativeTransaction", True),
    ):
        tbl = root.find(table)
        if tbl is None:
            continue
        for tx in tbl.findall(tag):
            code = _text(tx, "transactionCoding/transactionCode") or ""
            shares = _float(tx, "transactionAmounts/transactionShares/value")
            price = _float(tx, "transactionAmounts/transactionPricePerShare/value")
            value = (
                shares * price
                if (shares is not None and price is not None)
                else None
            )
            txns.append(
                InsiderTransaction(
                    owner_name=owner_name,
                    role=role,
                    officer_title=officer_title,
                    is_director=is_director,
                    is_officer=is_officer,
                    is_ten_pct=is_ten_pct,
                    date=_text(tx, "transactionDate/value"),
                    code=code,
                    bucket=classify_bucket(code, is_deriv),
                    shares=shares,
                    price=price,
                    value=value,
                    acquired_disposed=_text(
                        tx, "transactionAmounts/transactionAcquiredDisposedCode/value"
                    ),
                    security_title=_text(tx, "securityTitle/value"),
                    is_derivative=is_deriv,
                    shares_after=_float(
                        tx, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"
                    ),
                    direct_or_indirect=_text(
                        tx, "ownershipNature/directOrIndirectOwnership/value"
                    ),
                    is_10b5_1=is_10b5_1,
                )
            )
    return txns
