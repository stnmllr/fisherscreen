from unittest.mock import MagicMock

import frontmatter

from app.deepdive.adr_resolver import ResolvedTicker
from app.deepdive.pipeline import run_deep_dive
from app.models.deep_dive_record import PointInTimeQuant, QuantSnapshot, SourceCoverage
from app.services.edgar_client import RawFiling


def _good_points():
    return {
        "points": [
            {
                "number": n,
                "title": f"P{n}",
                "rating": 4,
                "confidence": "🟢",
                "reasoning": "Begründung.",
                "sources": ["20-F §5"],
            }
            for n in range(1, 16)
        ]
    }


def _deps():
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F"
    )
    filings = MagicMock()
    filings.get.return_value = RawFiling(
        "acc-1",
        "<html>Item 4. four Item 5. five Item 18. eighteen</html>",
        filing_date="2025-02-05",
    )
    quant = MagicMock()
    quant.return_value = (
        QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="NOVO-B.CO", name="Novo Nordisk")
        ),
        SourceCoverage(edgar="20-F via ADR"),
    )
    synthesizer = MagicMock()
    synthesizer.synthesize.return_value = _good_points()
    return resolver, filings, quant, synthesizer


def _peer_resolver():
    from app.models.deep_dive_record import PeerComparison, PeerQuant

    pr = MagicMock()
    pr.return_value = PeerComparison(
        peers=[
            PeerQuant(ticker="LLY"),
            PeerQuant(ticker="PFE"),
            PeerQuant(ticker="MRK"),
        ],
        rationale="peers",
    )
    return pr


def _run(
    out_dir,
    resolver,
    filings,
    quant,
    synth,
    peer_resolver=None,
    peers=None,
    peer_rationale=None,
    is_tty=False,
    ticker="NOVO-B.CO",
    insider_fetcher=None,
):
    return run_deep_dive(
        ticker,
        output_dir=out_dir,
        resolver=resolver,
        filing_fetcher=filings,
        build_quant=quant,
        synthesizer=synth,
        token_cap=200000,
        use_cache=True,
        peers=peers,
        peer_rationale=peer_rationale,
        is_tty=is_tty,
        peer_resolver=peer_resolver or _peer_resolver(),
        insider_fetcher=insider_fetcher,
    )


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

    out = _run(
        tmp_path, resolver, filings, quant, synth, peer_resolver=pr, peers="LLY,PFE,MRK"
    )
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


# --------------------------------------------------------------------------
# Quant-only path: ticker without any SEC filing source (EDV.L shape).
# --------------------------------------------------------------------------

_EDV_NOTE = (
    "Kein SEC-Hard-Scuttlebutt: ENDEAVOUR MINING PLC ist kein SEC-Registrant. "
    "Die einzige US-Linie (EDVMF) ist eine OTC-/unsponsored-Notierung, die ohne "
    "Zutun des Emittenten entstanden ist — sie begründet keine SEC-Registrierung "
    "(kein CIK in company_tickers.json) und damit keine Filing-Pflicht. Kein "
    "Symbol-Fehler. Dossier ist quant-only (Quant + Bewertung + Peers)."
)


class _ExplodingFilingFetcher:
    """Hand-written, not a MagicMock: a mock records the call and stays green,
    a raise makes the violation impossible to miss."""

    def get(self, *args, **kwargs):
        raise AssertionError("filing fetcher must not run without a filing source")


class _ExplodingInsiderFetcher:
    def get_summary_input(self, *args, **kwargs):
        raise AssertionError("insider fetcher must not run without a CIK")


class _ExplodingSynthesizer:
    def synthesize(self, *args, **kwargs):
        raise AssertionError("Gemini must never be called in the quant-only path")


def _quant_only_deps(reason="not_sec_registrant", note=_EDV_NOTE):
    from app.deepdive.adr_resolver import no_sec_source

    resolver = MagicMock()
    resolver.resolve.return_value = no_sec_source("EDV.L", reason=reason, note=note)
    quant = MagicMock()
    quant.return_value = (
        QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="EDV.L", name="Endeavour Mining")
        ),
        SourceCoverage(edgar="20-F via ADR"),
    )
    return resolver, quant


def _run_quant_only(out_dir, resolver, quant, peer_resolver=None, **over):
    return _run(
        out_dir,
        resolver,
        _ExplodingFilingFetcher(),
        quant,
        _ExplodingSynthesizer(),
        peer_resolver=peer_resolver,
        ticker="EDV.L",
        insider_fetcher=_ExplodingInsiderFetcher(),
        **over,
    )


def test_quant_only_path_touches_neither_filing_nor_insider_nor_gemini(tmp_path):
    """Rule 1 of the change, asserted structurally: the fetchers and the
    synthesizer are handed in and must still never be reached."""
    resolver, quant = _quant_only_deps()
    out = _run_quant_only(tmp_path, resolver, quant)

    assert out.exists()
    quant.assert_called_once_with("EDV.L", use_cache=True)


def test_quant_only_record_shape_has_no_filing_handles(tmp_path, monkeypatch):
    resolver, quant = _quant_only_deps()
    captured = {}

    real = pipeline_mod.generate_dossier

    def _capture(record, output_dir):
        captured["record"] = record
        return real(record, output_dir)

    monkeypatch.setattr(pipeline_mod, "generate_dossier", _capture)
    _run_quant_only(tmp_path, resolver, quant)

    rec = captured["record"]
    assert rec.cik is None
    assert rec.form_type is None
    assert rec.synthesis == []
    assert rec.filing_sections == {}
    assert rec.section_flags == {}
    assert rec.filing_date is None
    assert rec.no_sec_source_reason == "not_sec_registrant"
    assert rec.no_sec_source_note == _EDV_NOTE
    assert rec.insider_summary.coverage_state == "no_sec_source"
    # the resolver's note is the single source of truth for the EDGAR wording
    assert rec.source_coverage.edgar == _EDV_NOTE
    assert rec.source_coverage.insider == (
        "nicht verfügbar (kein SEC-Registrant, keine Form-4-Pflicht)"
    )


def test_quant_only_dossier_is_honestly_labelled(tmp_path):
    resolver, quant = _quant_only_deps()
    out = _run_quant_only(tmp_path, resolver, quant)

    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["ticker"] == "EDV.L"
    assert post["form_type"] == "kein SEC-Filing"
    assert post["cik"] is None
    assert post["no_sec_source_reason"] == "not_sec_registrant"
    assert post["no_sec_source_note"]
    assert "### Punkt" not in post.content  # no synthesis happened, none claimed


def test_quant_only_path_still_resolves_peers(tmp_path):
    """Peers are pure yfinance and stay valuable without a filing."""
    resolver, quant = _quant_only_deps()
    pr = _peer_resolver()
    out = _run_quant_only(tmp_path, resolver, quant, peer_resolver=pr, peers="AEM,GOLD")

    pr.assert_called_once()
    kw = pr.call_args.kwargs
    assert kw["ticker"] == "EDV.L"
    assert kw["peers_arg"] == "AEM,GOLD"
    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["peer_tickers"] == ["LLY", "PFE", "MRK"]


def test_quant_only_path_propagates_quant_datasource_error(tmp_path):
    """Degrade once, not twice: a quant-only dossier without quant would be
    worthless, so a transient yfinance failure still aborts (CLI exit 2)."""
    import pytest

    from app.errors import DataSourceError

    resolver, quant = _quant_only_deps()
    quant.side_effect = DataSourceError("yfinance down")

    with pytest.raises(DataSourceError, match="yfinance down"):
        _run_quant_only(tmp_path, resolver, quant)
    assert list(tmp_path.rglob("*.md")) == []


def test_quant_only_path_logs_a_warning(tmp_path, caplog):
    """A degraded run must be visible in the logs, not merely in the artefact."""
    import logging

    resolver, quant = _quant_only_deps()
    with caplog.at_level(logging.WARNING, logger="app.deepdive.pipeline"):
        _run_quant_only(tmp_path, resolver, quant)

    assert any(
        "no SEC filing source for EDV.L" in r.getMessage()
        and r.levelno == logging.WARNING
        for r in caplog.records
    )


def test_normal_filing_path_is_untouched_by_the_quant_only_branch(tmp_path):
    """Regression fence: has_filing_source True must still run the full path."""
    resolver, filings, quant, synth = _deps()
    out = _run(tmp_path, resolver, filings, quant, synth)

    post = frontmatter.loads(out.read_text(encoding="utf-8"))
    assert post["form_type"] == "20-F"
    assert post["cik"] == "0000353278"
    assert post["no_sec_source_reason"] is None
    assert post["no_sec_source_note"] is None
    assert "### Punkt 15 —" in post.content
    filings.get.assert_called_once_with("0000353278", "20-F", use_cache=True)
    synth.synthesize.assert_called()


# Removed: the pipeline-level empty-CIK guard test. The ADRResolver now
# guarantees a non-empty CIK or raises (see tests/deepdive/test_adr_resolver.py);
# a ResolvedTicker with cik="" can no longer occur, so the guard is gone (Task 4).


from app.deepdive import pipeline as pipeline_mod


def test_build_insider_summary_fpi_skips_fetch():
    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise AssertionError("must not be called for 20-F")

    s = pipeline_mod._build_insider_summary(
        cik="123",
        form_type="20-F",
        no_insider=False,
        insider_fetcher=_Fetcher(),
        use_cache=True,
        lookback_days=365,
    )
    assert s.coverage_state == "fpi_exempt"


def test_build_insider_summary_no_insider_flag_skips():
    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise AssertionError("must not be called when no_insider")

    s = pipeline_mod._build_insider_summary(
        cik="123",
        form_type="10-K",
        no_insider=True,
        insider_fetcher=_Fetcher(),
        use_cache=True,
        lookback_days=365,
    )
    assert s.coverage_state == "skipped"


def test_build_insider_summary_none_fetcher_skips():
    s = pipeline_mod._build_insider_summary(
        cik="123",
        form_type="10-K",
        no_insider=False,
        insider_fetcher=None,
        use_cache=True,
        lookback_days=365,
    )
    assert s.coverage_state == "skipped"


def test_build_insider_summary_failsoft_on_datasource_error():
    from app.errors import DataSourceError

    class _Fetcher:
        def get_summary_input(self, *a, **k):
            raise DataSourceError("index boom")

    s = pipeline_mod._build_insider_summary(
        cik="123",
        form_type="10-K",
        no_insider=False,
        insider_fetcher=_Fetcher(),
        use_cache=True,
        lookback_days=365,
    )
    assert s.coverage_state == "fetch_failed"


def test_build_insider_summary_ok_path_computes_summary():
    from app.deepdive.insider_cache import InsiderFetchResult
    from app.models.deep_dive_record import InsiderTransaction

    class _Fetcher:
        def get_summary_input(self, cik, since, use_cache=True):
            return InsiderFetchResult(
                transactions=[
                    InsiderTransaction(
                        owner_name="A",
                        role="CEO",
                        code="P",
                        bucket="buy",
                        value=500_000,
                        acquired_disposed="A",
                    )
                ],
                coverage_state="ok",
                n_filings_total=1,
                n_parsed=1,
            )

    s = pipeline_mod._build_insider_summary(
        cik="123",
        form_type="10-K",
        no_insider=False,
        insider_fetcher=_Fetcher(),
        use_cache=True,
        lookback_days=365,
    )
    assert s.coverage_state == "ok"
    assert len(s.significant_buys) == 1
