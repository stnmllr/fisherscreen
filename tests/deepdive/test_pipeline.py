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
