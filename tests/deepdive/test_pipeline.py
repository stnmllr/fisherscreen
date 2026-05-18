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
        "<html>Item 4. four Item 5. five Item 18. eighteen</html>")
    quant = MagicMock()
    quant.return_value = (
        QuantSnapshot(point_in_time=PointInTimeQuant(
            ticker="NOVO-B.CO", name="Novo Nordisk")),
        SourceCoverage(edgar="20-F via ADR"))
    synthesizer = MagicMock()
    synthesizer.synthesize.return_value = _good_points()
    return resolver, filings, quant, synthesizer


def test_pipeline_writes_dossier(tmp_path):
    resolver, filings, quant, synth = _deps()
    out = run_deep_dive(
        "NOVO-B.CO", output_dir=tmp_path, resolver=resolver,
        filing_fetcher=filings, build_quant=quant, synthesizer=synth,
        token_cap=200000, use_cache=True)
    assert out.exists()
    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert "### Punkt 1 —" in post.content
    resolver.resolve.assert_called_once_with("NOVO-B.CO")
    filings.get.assert_called_once_with("0000353278", "20-F", use_cache=True)


def test_pipeline_propagates_resolver_error(tmp_path):
    from app.errors import DeepDiveError
    resolver, filings, quant, synth = _deps()
    resolver.resolve.side_effect = DeepDiveError("not in ADR table")
    import pytest
    with pytest.raises(DeepDiveError, match="ADR table"):
        run_deep_dive("SAP.DE", output_dir=tmp_path, resolver=resolver,
                       filing_fetcher=filings, build_quant=quant,
                       synthesizer=synth, token_cap=200000, use_cache=True)


def test_pipeline_raises_actionable_error_on_empty_cik(tmp_path):
    import pytest
    from app.errors import DeepDiveError
    resolver, filings, quant, synth = _deps()
    resolver.resolve.return_value = ResolvedTicker("AAPL", None, "", "10-K")
    with pytest.raises(DeepDiveError, match="US-passthrough CIK resolution is Phase B.2"):
        run_deep_dive("AAPL", output_dir=tmp_path, resolver=resolver,
                       filing_fetcher=filings, build_quant=quant,
                       synthesizer=synth, token_cap=200000, use_cache=True)
