from unittest.mock import MagicMock

import frontmatter
import pytest

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


def _unverifiable_identity_dossier(tmp_path):
    """Run the quant-only path on an `unverifiable_identity` verdict and return
    the dossier's full text, front matter included.

    Raw text rather than a parsed post: the decisive assertion on this dossier
    is a NEGATIVE over the whole document, and a false claim that landed in the
    front matter would be exactly as wrong as one in the body.

    The note comes from the real factory rather than being hand-copied, so a
    wording change in `eu_adr_resolution` cannot leave these tests asserting a
    string production no longer emits."""
    from app.deepdive.eu_adr_resolution import unverifiable_identity

    verdict = unverifiable_identity(
        "EDV.L",
        cause="keine OpenFIGI-Heimatlinie stimmte mit dem Referenznamen überein",
    )
    resolver, quant = _quant_only_deps(
        reason=verdict.no_sec_source_reason, note=verdict.no_sec_source_note
    )
    out = _run_quant_only(tmp_path, resolver, quant)
    return out.read_text(encoding="utf-8")


def _section(content, heading):
    """The text of one '## ' section of a dossier, heading excluded."""
    return content.split(heading, 1)[1].split("\n## ", 1)[0]


def test_unverifiable_identity_reaches_the_dossier_as_an_unchecked_label(tmp_path):
    """The end of the chain, and the reason the degrade is defensible at all:
    the honest label has to arrive on the PRODUCT SURFACE, not merely inside a
    verdict object. A reader of this dossier must be able to tell that we did
    not identify the company — as opposed to that the company files nothing.

    Scoped to the WHOLE document, not to the Executive Summary alone. Until the
    reason -> coverage-state mapping existed, the insider block further down
    asserted the exact opposite ("kein SEC-Registrant") and the same dossier
    made two contradicting claims — the false one being the confident one. The
    characterisation test that pinned that defect has been folded in here."""
    text = _unverifiable_identity_dossier(tmp_path)
    post = frontmatter.loads(text)

    assert post["no_sec_source_reason"] == "unverifiable_identity"
    assert "ungeprüft, nicht widerlegt" in post["no_sec_source_note"]

    summary = _section(post.content, "## Executive Summary")
    assert "ungeprüft, nicht widerlegt" in summary
    assert "Dossier ist quant-only" in summary

    # Both surfaces that render the coverage state: the insider block itself and
    # the one-line SourceCoverage entry. Substrings, not the full sentences —
    # the wording may be improved, the claim it makes may not.
    insider = _section(post.content, "## Insider-Transaktionen")
    assert "der Emittent konnte nicht identifiziert werden" in insider
    assert "Emittent nicht identifiziert" in post.content

    # THE regression fence. A positive-only assertion above would go green again
    # the moment someone reintroduces the contradiction elsewhere in the
    # document, so the claim this path is not entitled to make is asserted
    # absent from the entire file — body and front matter. Case-insensitive:
    # a sentence-initial "Kein SEC-Registrant" is the same false claim.
    assert "kein sec-registrant" not in text.lower(), (
        "an unverifiable_identity dossier claims a CHECKED non-registration "
        "somewhere in the document — we never identified the issuer, so that "
        "claim was never established"
    )

    # Same structural downgrade as the three issuer verdicts: no filing handles,
    # no synthesis, and none claimed.
    assert post["cik"] is None
    assert post["form_type"] == "kein SEC-Filing"
    assert "### Punkt" not in post.content


def test_insider_state_mapping_is_total_over_the_no_sec_source_reasons():
    """`_INSIDER_STATE_BY_REASON` is checked for totality by an `assert` at
    import time — which disappears under `python -O`. Restated here so the
    invariant is enforced by the suite too, and so a fifth reason surfaces as a
    set difference instead of a bare import-time AssertionError."""
    from typing import get_args

    from app.deepdive.adr_resolver import NO_SEC_SOURCE_REASONS
    from app.models.deep_dive_record import InsiderCoverage

    assert set(pipeline_mod._INSIDER_STATE_BY_REASON) == NO_SEC_SOURCE_REASONS
    # Every mapped value must be a real coverage state, not a typo that only
    # shows up as an unrendered branch in a finished dossier.
    assert set(pipeline_mod._INSIDER_STATE_BY_REASON.values()) <= set(
        get_args(InsiderCoverage)
    )


def test_the_three_issuer_reasons_still_mean_no_sec_source():
    """The fix's boundary, pinned from the other side: only
    `unverifiable_identity` moved. The three verdicts ABOUT THE ISSUER are
    checked statements that no Form-4 duty exists, and the dossier stays
    entitled to say so — a fix that dragged them along would have traded one
    dishonest label for another."""
    mapping = pipeline_mod._INSIDER_STATE_BY_REASON

    assert mapping["no_us_line"] == "no_sec_source"
    assert mapping["not_sec_registrant"] == "no_sec_source"
    assert mapping["no_annual_form"] == "no_sec_source"
    assert mapping["unverifiable_identity"] == "issuer_unidentified"


@pytest.mark.parametrize(
    "reason", ["no_us_line", "not_sec_registrant", "no_annual_form"]
)
def test_issuer_reasons_still_produce_the_registrant_wording(reason, tmp_path):
    """The counterpart of the negative assertion above, and the reason it is
    scoped to `unverifiable_identity` only: for the three issuer verdicts the
    sentence "kein SEC-Registrant" is TRUE and must keep being printed. The
    fence must fence, not blanket-ban a phrase."""
    resolver, quant = _quant_only_deps(reason=reason)
    out = _run_quant_only(tmp_path, resolver, quant)
    post = frontmatter.loads(out.read_text(encoding="utf-8"))

    insider = _section(post.content, "## Insider-Transaktionen")
    assert "kein SEC-Registrant" in insider
    assert "Emittent konnte nicht identifiziert werden" not in insider


@pytest.mark.parametrize(
    "reason",
    ["no_us_line", "not_sec_registrant", "no_annual_form", "unverifiable_identity"],
)
def test_every_no_sec_source_reason_routes_through_the_mapping(
    reason, tmp_path, monkeypatch
):
    """The mapping is CONSULTED, not merely declared. Without driving the
    pipeline once per reason, the two constant tests above would only prove that
    a dict equals itself — a hard-coded "no_sec_source" back in `run_deep_dive`
    would leave them green while the dossier lied again."""
    resolver, quant = _quant_only_deps(
        reason=reason, note="Testnote. Dossier ist quant-only."
    )
    captured = {}
    real = pipeline_mod.generate_dossier

    def _capture(record, output_dir):
        captured["record"] = record
        return real(record, output_dir)

    monkeypatch.setattr(pipeline_mod, "generate_dossier", _capture)
    _run_quant_only(tmp_path, resolver, quant)

    assert (
        captured["record"].insider_summary.coverage_state
        == pipeline_mod._INSIDER_STATE_BY_REASON[reason]
    )


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
