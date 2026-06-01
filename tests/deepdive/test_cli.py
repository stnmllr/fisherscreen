import pytest

from app.deepdive.__main__ import build_parser, main


def test_build_parser_parses_ticker_and_flags():
    ns = build_parser().parse_args(["deepdive", "NOVO-B.CO", "--model", "x", "--no-cache"])
    assert ns.command == "deepdive"
    assert ns.ticker == "NOVO-B.CO"
    assert ns.model == "x"
    assert ns.no_cache is True


def test_deepdive_defaults():
    ns = build_parser().parse_args(["deepdive", "NOVO-B.CO"])
    assert ns.model is None
    assert ns.no_cache is False
    assert ns.peers is None
    assert ns.peer_rationale is None


def test_deepdive_parses_peer_args():
    ns = build_parser().parse_args([
        "deepdive", "NVO", "--peers", "LLY,PFE,MRK",
        "--peer-rationale", "Big Pharma"])
    assert ns.peers == "LLY,PFE,MRK"
    assert ns.peer_rationale == "Big Pharma"


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["deepdive", "--help"])
    assert exc.value.code == 0


def test_no_command_exits_two():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_deepdive_end_to_end_writes_dossier(tmp_path, monkeypatch):
    import frontmatter
    from unittest.mock import MagicMock
    from app.deepdive.adr_resolver import ResolvedTicker
    from app.models.deep_dive_record import (
        PointInTimeQuant, QuantSnapshot, SourceCoverage)
    from app.services.edgar_client import RawFiling
    import app.deepdive.__main__ as cli

    monkeypatch.setattr(cli.settings, "output_dir", str(tmp_path))
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F")
    fetcher = MagicMock()
    fetcher.get.return_value = RawFiling(
        "acc-1", "<html>Item 4. four Item 5. five Item 18. eighteen</html>")
    qb = MagicMock(return_value=(
        QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO")),
        SourceCoverage()))
    synth = MagicMock()
    synth.synthesize.return_value = {"points": [
        {"number": n, "title": f"P{n}", "rating": 4, "confidence": "🟢",
         "reasoning": "r.", "sources": ["20-F §5"]} for n in range(1, 16)]}
    from app.models.deep_dive_record import PeerComparison, PeerQuant
    peer_resolver = MagicMock(return_value=PeerComparison(
        peers=[PeerQuant(ticker="LLY"), PeerQuant(ticker="PFE"),
               PeerQuant(ticker="MRK")], rationale=None))
    monkeypatch.setattr(cli, "build_adr_resolver", lambda: resolver)
    monkeypatch.setattr(cli, "build_filing_fetcher", lambda: fetcher)
    monkeypatch.setattr(cli, "build_quant_builder", lambda: qb)
    monkeypatch.setattr(cli, "build_synthesizer", lambda m: synth)
    monkeypatch.setattr(cli, "build_peer_resolver", lambda: peer_resolver)

    rc = cli.main(["deepdive", "NOVO-B.CO", "--peers", "LLY,PFE,MRK"])
    assert rc == 0
    files = list((tmp_path / "Watchlist").glob("NOVO-B.CO_*.md"))
    assert len(files) == 1
    assert frontmatter.loads(files[0].read_text(encoding="utf-8"))["ticker"] == "NOVO-B.CO"


def test_deepdive_maps_deepdive_error_to_exit_1(monkeypatch):
    from unittest.mock import MagicMock
    import app.deepdive.__main__ as cli
    from app.errors import DeepDiveError
    bad = MagicMock()
    bad.resolve.side_effect = DeepDiveError("not in ADR table")
    monkeypatch.setattr(cli, "build_adr_resolver", lambda: bad)
    monkeypatch.setattr(cli, "build_filing_fetcher", lambda: MagicMock())
    monkeypatch.setattr(cli, "build_quant_builder", lambda: MagicMock())
    monkeypatch.setattr(cli, "build_synthesizer", lambda m: MagicMock())
    monkeypatch.setattr(cli, "build_peer_resolver", lambda: MagicMock())
    assert cli.main(["deepdive", "SAP.DE"]) == 1


def test_parser_accepts_no_insider_flag():
    args = build_parser().parse_args(["deepdive", "MSFT", "--no-insider"])
    assert args.no_insider is True


def test_parser_no_insider_defaults_false():
    args = build_parser().parse_args(["deepdive", "MSFT"])
    assert args.no_insider is False
