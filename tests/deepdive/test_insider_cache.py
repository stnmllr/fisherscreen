from pathlib import Path

from app.deepdive.insider_cache import CachedInsiderFetcher
from app.errors import DataSourceError
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


class _FakeEdgar:
    def __init__(self, refs, docs=None, index_raises=False):
        self._refs = refs
        self._docs = docs or {}
        self._index_raises = index_raises
        self.doc_calls = 0

    def get_form4_index(self, cik, since):
        if self._index_raises:
            raise DataSourceError("index boom")
        return self._refs

    def get_form4_document(self, cik, accession_number, primary_document):
        self.doc_calls += 1
        if accession_number not in self._docs:
            raise DataSourceError("doc boom")
        return self._docs[accession_number]


def _fetcher(tmp_path, edgar):
    return CachedInsiderFetcher(edgar=edgar, cache_dir=tmp_path)


def test_empty_index_is_empty_not_fetch_failed(tmp_path):
    res = _fetcher(tmp_path, _FakeEdgar([])).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "empty"
    assert res.n_filings_total == 0 and res.n_parsed == 0


def test_all_xml_fail_is_fetch_failed_not_empty(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01")]
    res = _fetcher(tmp_path, _FakeEdgar(refs, docs={})).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "fetch_failed"
    assert res.n_filings_total == 1 and res.n_parsed == 0


def test_partial_when_some_xml_fail(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01"),
            Form4Ref("a2", "form4.xml", "2026-02-01")]
    edgar = _FakeEdgar(refs, docs={"a1": _XML})
    res = _fetcher(tmp_path, edgar).get_summary_input("1", "2025-01-01")
    assert res.coverage_state == "partial"
    assert res.n_filings_total == 2 and res.n_parsed == 1
    assert len(res.transactions) == 1


def test_ok_and_accession_cache_hit_skips_refetch(tmp_path):
    refs = [Form4Ref("a1", "form4.xml", "2026-01-01")]
    edgar = _FakeEdgar(refs, docs={"a1": _XML})
    f = _fetcher(tmp_path, edgar)
    r1 = f.get_summary_input("1", "2025-01-01")
    assert r1.coverage_state == "ok" and edgar.doc_calls == 1
    r2 = f.get_summary_input("1", "2025-01-01")
    assert r2.coverage_state == "ok" and edgar.doc_calls == 1


def test_index_error_propagates_for_pipeline_failsoft(tmp_path):
    import pytest
    edgar = _FakeEdgar([], index_raises=True)
    with pytest.raises(DataSourceError):
        _fetcher(tmp_path, edgar).get_summary_input("1", "2025-01-01")
