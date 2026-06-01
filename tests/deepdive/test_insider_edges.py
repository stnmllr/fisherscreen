import json

from app.deepdive.insider_block import render_insider_block, insider_coverage_label
from app.deepdive.insider_cache import CachedInsiderFetcher
from app.deepdive.insider_parser import parse_form4
from app.models.deep_dive_record import InsiderSummary, InsiderTransaction
from app.services.edgar_client import Form4Ref

_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <reportingOwner>
    <reportingOwnerId><rptOwnerName>Doe Jane</rptOwnerName></reportingOwnerId>
    <reportingOwnerRelationship><isOfficer>1</isOfficer><officerTitle>EVP</officerTitle></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable><nonDerivativeTransaction>
    <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
    <transactionAmounts>
      <transactionShares><value>100</value></transactionShares>
      <transactionPricePerShare><value>10</value></transactionPricePerShare>
      <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
    </transactionAmounts>
  </nonDerivativeTransaction></nonDerivativeTable>
</ownershipDocument>
"""


# ---- insider_block: coverage label normal-case + render edges ----

def test_coverage_label_ok_partial_empty_failed():
    ok = insider_coverage_label(InsiderSummary(
        coverage_state="ok", n_filings_total=10, n_parsed=10,
        significant_buys=[InsiderTransaction(
            owner_name="A", role="CEO", code="P", bucket="buy")]))
    assert "10/10" in ok and "1 Käufe" in ok and "signifikant" in ok
    assert "0 Form-4" in insider_coverage_label(InsiderSummary(coverage_state="empty"))
    assert "fehlgeschlagen" in insider_coverage_label(
        InsiderSummary(coverage_state="fetch_failed", n_filings_total=5))
    assert insider_coverage_label(None).startswith("nicht anwendbar")


def test_render_missing_value_renders_na_and_omits_pct():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=1, n_parsed=1, n_transactions_total=1,
        significant_buys=[InsiderTransaction(
            owner_name="A", role="CEO", code="P", bucket="buy",
            shares=None, price=None, value=None, acquired_disposed="A",
            shares_after=None, direct_or_indirect="D", significant=True)])
    out = render_insider_block(s, "10-K")
    assert "= n/a" in out
    assert "%" not in out.split("Transaktionen")[1]


def test_render_acquisition_no_prior_holding_omits_pct_and_ungeplant_flag():
    s = InsiderSummary(
        coverage_state="ok", n_filings_total=1, n_parsed=1, n_transactions_total=1,
        significant_buys=[InsiderTransaction(
            owner_name="A", role="CEO", code="P", bucket="buy",
            shares=1000, price=10.0, value=10000, acquired_disposed="A",
            shares_after=1000, direct_or_indirect="D", is_10b5_1=False,
            significant=True)])  # pre = 1000 - 1000 = 0 -> omit pct
    out = render_insider_block(s, "10-K")
    assert "%" not in out.split("Transaktionen")[1]
    assert "(ungeplant)" in out


# ---- insider_parser: robustness ----

def test_parse_form4_empty_document_returns_empty_list():
    assert parse_form4("<?xml version='1.0'?><ownershipDocument></ownershipDocument>") == []


def test_parse_form4_nonnumeric_share_becomes_none():
    xml = """<?xml version="1.0"?><ownershipDocument>
      <reportingOwner><reportingOwnerId><rptOwnerName>X</rptOwnerName></reportingOwnerId></reportingOwner>
      <nonDerivativeTable><nonDerivativeTransaction>
        <transactionCoding><transactionCode>S</transactionCode></transactionCoding>
        <transactionAmounts>
          <transactionShares><value>abc</value></transactionShares>
          <transactionAcquiredDisposedCode><value>D</value></transactionAcquiredDisposedCode>
        </transactionAmounts>
      </nonDerivativeTransaction></nonDerivativeTable>
    </ownershipDocument>"""
    txns = parse_form4(xml)
    assert len(txns) == 1
    assert txns[0].shares is None and txns[0].value is None
    assert txns[0].owner_name == "X"


# ---- insider_cache: fail-soft fallbacks ----

class _Edgar:
    def __init__(self, refs, doc):
        self._refs = refs
        self._doc = doc
        self.calls = 0

    def get_form4_index(self, cik, since):
        return self._refs

    def get_form4_document(self, cik, accession_number, primary_document):
        self.calls += 1
        return self._doc


def test_corrupt_cache_file_falls_back_to_fetch(tmp_path):
    ref = Form4Ref("a1", "form4.xml", "2026-01-01")
    p = tmp_path / "1" / "a1.json"
    p.parent.mkdir(parents=True)
    p.write_text("{ not valid json", encoding="utf-8")
    edgar = _Edgar([ref], _XML)
    res = CachedInsiderFetcher(edgar=edgar, cache_dir=tmp_path).get_summary_input(
        "1", "2025-01-01")
    assert res.coverage_state == "ok" and edgar.calls == 1


def test_schema_version_mismatch_is_cache_miss(tmp_path):
    ref = Form4Ref("a1", "form4.xml", "2026-01-01")
    p = tmp_path / "1" / "a1.json"
    p.parent.mkdir(parents=True)
    p.write_text(json.dumps({"schema_version": 999, "transactions": []}),
                 encoding="utf-8")
    edgar = _Edgar([ref], _XML)
    res = CachedInsiderFetcher(edgar=edgar, cache_dir=tmp_path).get_summary_input(
        "1", "2025-01-01")
    assert edgar.calls == 1  # stale schema -> refetch
