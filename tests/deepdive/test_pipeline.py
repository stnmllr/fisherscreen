from unittest.mock import MagicMock

import frontmatter

from app.deepdive.adr_resolver import ResolvedTicker
from app.deepdive.pipeline import run_deep_dive
from app.models.deep_dive_record import (
    PointInTimeQuant, QuantSnapshot, SourceCoverage)
from app.services.edgar_client import RawFiling


def _good_points():
    return {"points": [
        {"number": n, "title": f"P{n}", "rating": 4, "confidence": "🟢",
         "reasoning": "Begründung.", "sources": ["20-F §5"]}
        for n in range(1, 16)]}


def _deps():
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F")
    filings = MagicMock()
    filings.get.return_value = RawFiling("acc-1",
        "<html>Item 4. four Item 5. five Item 18. eighteen</html>",
        filing_date="2025-02-05")
    quant = MagicMock()
    quant.return_value = (
        QuantSnapshot(point_in_time=PointInTimeQuant(
            ticker="NOVO-B.CO", name="Novo Nordisk")),
        SourceCoverage(edgar="20-F via ADR"))
    synthesizer = MagicMock()
    synthesizer.synthesize.return_value = _good_points()
    return resolver, filings, quant, synthesizer


def _peer_resolver():
    from app.models.deep_dive_record import PeerComparison, PeerQuant
    pr = MagicMock()
    pr.return_value = PeerComparison(
        peers=[PeerQuant(ticker="LLY"), PeerQuant(ticker="PFE"),
               PeerQuant(ticker="MRK")],
        rationale="peers")
    return pr


def _run(out_dir, resolver, filings, quant, synth, peer_resolver=None,
         peers=None, peer_rationale=None, is_tty=False):
    return run_deep_dive(
        "NOVO-B.CO", output_dir=out_dir, resolver=resolver,
        filing_fetcher=filings, build_quant=quant, synthesizer=synth,
        token_cap=200000, use_cache=True,
        peers=peers, peer_rationale=peer_rationale, is_tty=is_tty,
        peer_resolver=peer_resolver or _peer_resolver())


def test_pipeline_writes_dossier(tmp_path):
    resolver, filings, quant, synth = _deps()
    out = _run(tmp_path, resolver, filings, quant, synth)
    assert out.exists()
    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert "### Punkt 1 —" in post.content
    resolver.resolve.assert_called_once_with("NOVO-B.CO")
    filings.get.assert_called_once_with("0000353278", "20-F", use_cache=True)


def test_peer_resolver_invoked_between_quant_and_synthesis(tmp_path):
    from app.models.deep_dive_record import PeerComparison

    resolver, filings, quant, synth = _deps()
    pr = _peer_resolver()
    captured = {}

    def _synth_capture(**kwargs):
        captured["peer_comparison"] = kwargs["quant"].peer_comparison
        from app.deepdive.synthesis import run_synthesis
        return run_synthesis(**kwargs)

    out = _run(tmp_path, resolver, filings, quant, synth,
               peer_resolver=pr, peers="LLY,PFE,MRK")
    pr.assert_called_once()
    kw = pr.call_args.kwargs
    assert kw["ticker"] == "NOVO-B.CO"
    assert kw["peers_arg"] == "LLY,PFE,MRK"
    # attached to the quant snapshot -> flows into synthesis AND record
    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["peer_tickers"] == ["LLY", "PFE", "MRK"]
    assert post["peer_rationale"] == "peers"
    assert isinstance(pr.return_value, PeerComparison)


def test_pipeline_threads_filing_date_into_record(tmp_path, monkeypatch):
    resolver, filings, quant, synth = _deps()
    captured = {}

    import app.deepdive.pipeline as pipeline_mod
    real = pipeline_mod.generate_dossier

    def _capture(record, output_dir):
        captured["record"] = record
        return real(record, output_dir)

    monkeypatch.setattr(pipeline_mod, "generate_dossier", _capture)
    _run(tmp_path, resolver, filings, quant, synth)
    assert captured["record"].filing_date == "2025-02-05"


def test_pipeline_propagates_resolver_error(tmp_path):
    from app.errors import DeepDiveError
    resolver, filings, quant, synth = _deps()
    resolver.resolve.side_effect = DeepDiveError("not in ADR table")
    import pytest
    with pytest.raises(DeepDiveError, match="ADR table"):
        _run(tmp_path, resolver, filings, quant, synth)


def test_pipeline_raises_actionable_error_on_empty_cik(tmp_path):
    import pytest
    from app.errors import DeepDiveError
    resolver, filings, quant, synth = _deps()
    resolver.resolve.return_value = ResolvedTicker("AAPL", None, "", "10-K")
    with pytest.raises(DeepDiveError, match="US-passthrough CIK resolution is Phase B.2"):
        _run(tmp_path, resolver, filings, quant, synth)


from app.deepdive import pipeline as pipeline_mod


def test_build_insider_summary_fpi_skips_fetch():
    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise AssertionError("must not be called for 20-F")
    s = pipeline_mod._build_insider_summary(
        cik="123", form_type="20-F", no_insider=False,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365)
    assert s.coverage_state == "fpi_exempt"


def test_build_insider_summary_no_insider_flag_skips():
    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise AssertionError("must not be called when no_insider")
    s = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=True,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365)
    assert s.coverage_state == "skipped"


def test_build_insider_summary_none_fetcher_skips():
    s = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=False,
        insider_fetcher=None, use_cache=True, lookback_days=365)
    assert s.coverage_state == "skipped"


def test_build_insider_summary_failsoft_on_datasource_error():
    from app.errors import DataSourceError

    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise DataSourceError("index boom")
    s = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=False,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365)
    assert s.coverage_state == "fetch_failed"


def test_build_insider_summary_ok_path_computes_summary():
    from app.deepdive.insider_cache import InsiderFetchResult
    from app.models.deep_dive_record import InsiderTransaction

    class _Fetcher:
        def get_summary_input(self, cik, since, use_cache=True):
            return InsiderFetchResult(
                transactions=[InsiderTransaction(
                    owner_name="A", role="CEO", code="P", bucket="buy",
                    value=500_000, acquired_disposed="A")],
                coverage_state="ok", n_filings_total=1, n_parsed=1)
    s = pipeline_mod._build_insider_summary(
        cik="123", form_type="10-K", no_insider=False,
        insider_fetcher=_Fetcher(), use_cache=True, lookback_days=365)
    assert s.coverage_state == "ok"
    assert len(s.significant_buys) == 1
