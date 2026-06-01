from app.deepdive.insider_parser import (
    parse_form4,
    classify_bucket,
    derive_role,
)

_XML_SELL = """<?xml version="1.0"?>
<ownershipDocument>
  <documentType>4</documentType>
  <aff10b5One>1</aff10b5One>
  <issuer><issuerTradingSymbol>NVDA</issuerTradingSymbol></issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Huang Jensen</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship>
      <isDirector>1</isDirector><isOfficer>1</isOfficer>
      <isTenPercentOwner>0</isTenPercentOwner>
      <officerTitle>President and Chief Executive Officer</officerTitle>
    </reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <securityTitle><value>Common Stock</value></securityTitle>
      <transactionDate><value>2026-05-29</value></transactionDate>
      <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>10000</value></transactionShares>
        <transactionPricePerShare><value>150.0</value></transactionPricePerShare>
        <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
      <postTransactionAmounts>
        <sharesOwnedFollowingTransaction><value>90000</value></sharesOwnedFollowingTransaction>
      </postTransactionAmounts>
      <ownershipNature><directOrIndirectOwnership><value>D</value></directOrIndirectOwnership></ownershipNature>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
  <derivativeTable>
    <derivativeTransaction>
      <securityTitle><value>RSU</value></securityTitle>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>5000</value></transactionShares>
        <transactionAcquiredDisposedCode><value>A</value></transactionAcquiredDisposedCode>
      </transactionAmounts>
    </derivativeTransaction>
  </derivativeTable>
</ownershipDocument>
"""


def test_parse_form4_extracts_nonderivative_and_derivative():
    txns = parse_form4(_XML_SELL)
    assert len(txns) == 2
    sell = txns[0]
    assert sell.owner_name == "Huang Jensen"
    assert sell.role == "CEO"  # title precedence over Director flag
    assert sell.code == "S" and sell.bucket == "sell"
    assert sell.shares == 10000 and sell.price == 150.0
    assert sell.value == 1_500_000.0
    assert sell.acquired_disposed == "D"
    assert sell.shares_after == 90000 and sell.direct_or_indirect == "D"
    assert sell.is_derivative is False
    assert sell.is_10b5_1 is True
    deriv = txns[1]
    assert deriv.is_derivative is True and deriv.bucket == "routine"
    assert deriv.value is None


def test_classify_bucket_unknown_code_warns_routine(caplog):
    import logging
    with caplog.at_level(logging.WARNING):
        assert classify_bucket("X", False) == "routine"
    assert any("unknown transactionCode" in r.message for r in caplog.records)
    assert classify_bucket("P", False) == "buy"
    assert classify_bucket("S", False) == "sell"
    assert classify_bucket("S", True) == "routine"


def test_derive_role_precedence():
    assert derive_role("EVP, Chief Financial Officer", True, True, False) == "CFO"
    assert derive_role("Principal Executive Officer", False, True, False) == "CEO"
    assert derive_role(None, True, True, False) == "Officer"
    assert derive_role(None, True, False, False) == "Director"
    assert derive_role(None, False, False, True) == "TenPercentOwner"
    assert derive_role(None, False, False, False) == "Other"
