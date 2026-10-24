import logging

import pytest

from app.deepdive.__main__ import build_parser, main


@pytest.fixture(autouse=True)
def _no_dossier_repo(monkeypatch):
    """Keep a developer's local .env from enabling real publishing."""
    from app.config import settings

    monkeypatch.setattr(settings, "dossier_repo", "")


def test_build_parser_parses_ticker_and_flags():
    ns = build_parser().parse_args(
        ["deepdive", "NOVO-B.CO", "--model", "x", "--no-cache"]
    )
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
    ns = build_parser().parse_args(
        ["deepdive", "NVO", "--peers", "LLY,PFE,MRK", "--peer-rationale", "Big Pharma"]
    )
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
        PointInTimeQuant,
        QuantSnapshot,
        SourceCoverage,
    )
    from app.services.edgar_client import RawFiling
    import app.deepdive.__main__ as cli

    monkeypatch.setattr(cli.settings, "output_dir", str(tmp_path))
    resolver = MagicMock()
    resolver.resolve.return_value = ResolvedTicker(
        "NOVO-B.CO", "NVO", "0000353278", "20-F"
    )
    fetcher = MagicMock()
    fetcher.get.return_value = RawFiling(
        "acc-1", "<html>Item 4. four Item 5. five Item 18. eighteen</html>"
    )
    qb = MagicMock(
        return_value=(
            QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO")),
            SourceCoverage(),
        )
    )
    synth = MagicMock()
    synth.synthesize.return_value = {
        "points": [
            {
                "number": n,
                "title": f"P{n}",
                "rating": 4,
                "confidence": "🟢",
                "reasoning": "r.",
                "sources": ["20-F §5"],
            }
            for n in range(1, 16)
        ]
    }
    from app.models.deep_dive_record import PeerComparison, PeerQuant

    peer_resolver = MagicMock(
        return_value=PeerComparison(
            peers=[
                PeerQuant(ticker="LLY"),
                PeerQuant(ticker="PFE"),
                PeerQuant(ticker="MRK"),
            ],
            rationale=None,
        )
    )
    monkeypatch.setattr(cli, "build_adr_resolver", lambda: resolver)
    monkeypatch.setattr(cli, "build_filing_fetcher", lambda: fetcher)
    monkeypatch.setattr(cli, "build_quant_builder", lambda: qb)
    monkeypatch.setattr(cli, "build_synthesizer", lambda m: synth)
    monkeypatch.setattr(cli, "build_peer_resolver", lambda: peer_resolver)
    # Stub the 6th builder too — it was missed when Phase 1.4 wired insider fetching
    # into the CLI. Building the real one constructs an EdgarClientImpl (needs a SEC
    # user agent), which has no place in a CLI-orchestration test. NOVO-B.CO is a
    # 20-F/FPI, so the insider stage is skipped and the fetcher is never exercised.
    monkeypatch.setattr(cli, "build_insider_fetcher", lambda: MagicMock())

    rc = cli.main(["deepdive", "NOVO-B.CO", "--peers", "LLY,PFE,MRK"])
    assert rc == 0
    files = list((tmp_path / "Watchlist").glob("NOVO-B.CO_*.md"))
    assert len(files) == 1
    assert (
        frontmatter.loads(files[0].read_text(encoding="utf-8"))["ticker"] == "NOVO-B.CO"
    )


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
    monkeypatch.setattr(cli, "build_insider_fetcher", lambda: MagicMock())
    assert cli.main(["deepdive", "SAP.DE"]) == 1


def test_parser_accepts_no_insider_flag():
    args = build_parser().parse_args(["deepdive", "MSFT", "--no-insider"])
    assert args.no_insider is True


def test_parser_no_insider_defaults_false():
    args = build_parser().parse_args(["deepdive", "MSFT"])
    assert args.no_insider is False


# --- --site: re-render the viewer after a successful deep dive -------------
#
# The flag is opt-in on purpose. Everything below exists to pin one property:
# the renderer may not influence the outcome of a 20-minute paid Gemini run.


def _stub_builders(monkeypatch, cli) -> None:
    """Stub the six composition roots so no real client is constructed."""
    from unittest.mock import MagicMock

    for name in (
        "build_adr_resolver",
        "build_filing_fetcher",
        "build_quant_builder",
        "build_peer_resolver",
        "build_insider_fetcher",
    ):
        monkeypatch.setattr(cli, name, lambda: MagicMock())
    monkeypatch.setattr(cli, "build_synthesizer", lambda model: MagicMock())


@pytest.fixture
def site_cli(tmp_path, monkeypatch):
    """The CLI with a successful deep dive and a recording renderer."""
    from unittest.mock import MagicMock
    import app.deepdive.__main__ as cli

    monkeypatch.setattr(cli.settings, "output_dir", str(tmp_path))
    _stub_builders(monkeypatch, cli)
    dossier = tmp_path / "Watchlist" / "MSFT_2026-09-06.md"
    monkeypatch.setattr(cli, "run_deep_dive", MagicMock(return_value=dossier))
    render = MagicMock(return_value=0)
    monkeypatch.setattr(cli, "render_site", render)
    return cli, render, dossier, tmp_path


def test_parser_site_defaults_false():
    args = build_parser().parse_args(["deepdive", "MSFT"])
    assert args.site is False


def test_parser_accepts_site_flag():
    args = build_parser().parse_args(["deepdive", "MSFT", "--site"])
    assert args.site is True


def test_without_site_flag_the_renderer_is_not_called(site_cli):
    cli, render, _, _ = site_cli

    assert cli.main(["deepdive", "MSFT"]) == 0
    render.assert_not_called()


def test_site_flag_renders_once_with_paths_from_settings(site_cli):
    cli, render, _, tmp_path = site_cli

    cli.main(["deepdive", "MSFT", "--site"])

    render.assert_called_once_with(
        [
            "--in",
            str(tmp_path / "Watchlist"),
            "--out",
            str(tmp_path / "site"),
        ]
    )


def test_site_flag_keeps_exit_code_zero_when_render_succeeds(site_cli):
    cli, _, _, _ = site_cli

    assert cli.main(["deepdive", "MSFT", "--site"]) == 0


def test_dossier_path_is_printed_before_the_render_starts(site_cli, capsys):
    """A hanging or noisy renderer must not obscure the paid-for result."""
    cli, render, dossier, _ = site_cli
    seen: list[str] = []
    render.side_effect = lambda argv: seen.append(capsys.readouterr().out) or 0

    cli.main(["deepdive", "MSFT", "--site"])

    assert str(dossier) in seen[0]


def test_render_crash_keeps_the_exit_code_of_the_run_without_site(site_cli):
    cli, render, _, _ = site_cli
    without_site = cli.main(["deepdive", "MSFT"])
    render.side_effect = RuntimeError("renderer exploded")

    assert cli.main(["deepdive", "MSFT", "--site"]) == without_site


def test_render_crash_is_logged_with_the_traceback(site_cli, caplog):
    cli, render, _, _ = site_cli
    render.side_effect = RuntimeError("renderer exploded")

    with caplog.at_level(logging.ERROR, logger="app.deepdive.__main__"):
        cli.main(["deepdive", "MSFT", "--site"])

    record = caplog.records[-1]
    assert record.exc_info is not None
    assert "renderer exploded" in caplog.text


def test_render_crash_still_names_the_dossier_and_says_the_site_is_stale(
    site_cli, capsys
):
    cli, render, dossier, _ = site_cli
    render.side_effect = RuntimeError("renderer exploded")

    cli.main(["deepdive", "MSFT", "--site"])
    printed = capsys.readouterr().out

    assert str(dossier) in printed
    assert "NOT refreshed" in printed


def test_render_systemexit_keeps_the_deep_dive_exit_code(site_cli, capsys):
    """The seam is a CLI entry point, so argparse can raise SystemExit —
    which `except Exception` would let through."""
    cli, render, dossier, _ = site_cli
    render.side_effect = SystemExit(2)

    exit_code = cli.main(["deepdive", "MSFT", "--site"])

    assert exit_code == 0
    assert "NOT refreshed" in capsys.readouterr().out


def test_render_nonzero_exit_keeps_the_deep_dive_exit_code(site_cli, capsys):
    """The viewer reports its own failures by returning 1, not by raising."""
    cli, render, dossier, _ = site_cli
    render.return_value = 1

    exit_code = cli.main(["deepdive", "MSFT", "--site"])
    printed = capsys.readouterr().out

    assert exit_code == 0
    assert str(dossier) in printed
    assert "NOT refreshed" in printed


# --- preflight subcommand ----------------------------------------------------


def _preflight_result(can_start: bool, kind: str = "full"):
    from app.deepdive.preflight import PreflightResult, SymbolCheck

    def ok(sym):
        return SymbolCheck(sym, True, sym.title(), "USD", 1e9, f"gefunden: {sym}")

    return PreflightResult(
        ticker=ok("NOVO-B.CO"),
        peers=[ok("LLY"), ok("PFE"), ok("MRK")],
        dossier_kind=kind,
        dossier_note="20-F via ADR NVO (CIK 0000353278)",
        no_sec_source_reason=None,
        can_start=can_start,
        needs_quant_only_ack=False,
    )


def test_preflight_parser():
    ns = build_parser().parse_args(["preflight", "NOVO-B.CO", "--peers", "LLY,PFE,MRK"])
    assert ns.command == "preflight"
    assert ns.ticker == "NOVO-B.CO"
    assert ns.peers == "LLY,PFE,MRK"


def test_preflight_requires_peers():
    with pytest.raises(SystemExit) as exc:
        main(["preflight", "NOVO-B.CO"])
    assert exc.value.code == 2


@pytest.mark.parametrize("can_start, code", [(True, 0), (False, 1)])
def test_preflight_exit_code_follows_can_start(monkeypatch, capsys, can_start, code):
    import app.deepdive.__main__ as cli

    calls = []

    def runner(ticker, peers):
        calls.append((ticker, peers))
        return _preflight_result(can_start)

    monkeypatch.setattr(cli, "build_preflight_runner", lambda: runner)
    # the deep-dive path must not be touched by the preflight command
    monkeypatch.setattr(cli, "run_deep_dive", None)

    assert main(["preflight", "NOVO-B.CO", "--peers", "LLY, PFE ,MRK"]) == code
    assert calls == [("NOVO-B.CO", ["LLY", "PFE", "MRK"])]
    out = capsys.readouterr().out
    assert "Vorprüfung NOVO-B.CO" in out
    assert f"Start möglich: {'ja' if can_start else 'nein'}" in out


def test_preflight_bad_peer_string_exits_one_without_check(monkeypatch, capsys):
    import app.deepdive.__main__ as cli

    def boom():
        raise AssertionError("runner must not be built")

    monkeypatch.setattr(cli, "build_preflight_runner", boom)
    assert main(["preflight", "NOVO-B.CO", "--peers", "A,B,C,D"]) == 1
    assert "1 bis 3" in capsys.readouterr().out


def test_preflight_data_source_setup_failure_exits_two(monkeypatch, capsys):
    import app.deepdive.__main__ as cli
    from app.errors import DataSourceError

    def broken():
        def _run(ticker, peers):
            raise DataSourceError("EDGAR user agent not set")

        return _run

    monkeypatch.setattr(cli, "build_preflight_runner", broken)
    assert main(["preflight", "NOVO-B.CO", "--peers", "LLY,PFE,MRK"]) == 2
    assert "EDGAR user agent not set" in capsys.readouterr().out


def test_preflight_two_peers_prints_suggestions_and_exits_one(monkeypatch, capsys):
    import dataclasses

    import app.deepdive.__main__ as cli
    from app.deepdive.peer_suggest import PeerSuggestion

    calls = []
    suggestion = PeerSuggestion("HO.PA", "Thales", 4e10, "industry", "A&D", None)

    def runner(ticker, peers):
        calls.append((ticker, peers))
        base = _preflight_result(False)
        return dataclasses.replace(
            base,
            peers=base.peers[:2],
            missing_peer_slots=[3],
            peer_suggestions=[suggestion],
        )

    monkeypatch.setattr(cli, "build_preflight_runner", lambda: runner)
    assert main(["preflight", "SAF.PA", "--peers", "air.pa,RHM.DE"]) == 1
    assert calls == [("SAF.PA", ["AIR.PA", "RHM.DE"])]
    out = capsys.readouterr().out
    assert "Peer 3  fehlt" in out
    assert "HO.PA" in out


# --- publishing the dossier to the data repo -------------------------------

STATUS_PREFIXES = (
    "Published to: ",
    "WARNING: dossier NOT published: ",
    "Dossier not published (--no-publish)",
    "Dossier not published (no dossier repo configured)",
)


def _status_lines(out: str) -> list[str]:
    return [ln for ln in out.splitlines() if ln.startswith(STATUS_PREFIXES)]


@pytest.fixture
def publish_cli(tmp_path, monkeypatch):
    """Successful deep dive, publishing configured, recording fakes."""
    from unittest.mock import MagicMock
    import app.deepdive.__main__ as cli

    monkeypatch.setattr(cli.settings, "output_dir", str(tmp_path))
    monkeypatch.setattr(cli.settings, "dossier_repo", "stnmllr/fisherscreen-dossiers")
    _stub_builders(monkeypatch, cli)
    dossier = tmp_path / "Watchlist" / "X_2026-10-25.md"
    run = MagicMock(return_value=dossier)
    monkeypatch.setattr(cli, "run_deep_dive", run)
    monkeypatch.setattr(cli, "render_site", MagicMock(return_value=0))
    builder = MagicMock(return_value=MagicMock())
    monkeypatch.setattr(cli, "build_dossier_publisher", builder)
    publish = MagicMock(
        return_value="stnmllr/fisherscreen-dossiers/Watchlist/X_2026-10-25.md"
    )
    monkeypatch.setattr(cli, "publish_dossier", publish)
    return cli, run, builder, publish, dossier


def test_deepdive_publishes_after_writing(publish_cli, capsys):
    cli, _, builder, publish, dossier = publish_cli
    assert cli.main(["deepdive", "X"]) == 0
    out = capsys.readouterr().out
    assert (
        "Published to: stnmllr/fisherscreen-dossiers/Watchlist/X_2026-10-25.md" in out
    )
    assert out.index("Dossier written to:") < out.index("Published to:")
    assert publish.call_args.args[0] == dossier
    assert len(_status_lines(out)) == 1


def test_deepdive_no_publish_flag(publish_cli, capsys):
    cli, _, builder, publish, _ = publish_cli
    assert cli.main(["deepdive", "X", "--no-publish"]) == 0
    out = capsys.readouterr().out
    assert "Dossier not published (--no-publish)" in out
    builder.assert_not_called()
    publish.assert_not_called()
    assert len(_status_lines(out)) == 1


def test_deepdive_publish_unconfigured(publish_cli, monkeypatch, capsys):
    cli, _, builder, publish, _ = publish_cli
    monkeypatch.setattr(cli.settings, "dossier_repo", "")
    monkeypatch.setattr(cli, "build_dossier_publisher", lambda: None)
    assert cli.main(["deepdive", "X"]) == 0
    out = capsys.readouterr().out
    assert "Dossier not published (no dossier repo configured)" in out
    publish.assert_not_called()
    assert len(_status_lines(out)) == 1


def test_deepdive_publish_failure_keeps_exit_zero(publish_cli, capsys, caplog):
    from app.errors import DataSourceError

    cli, _, _, publish, _ = publish_cli
    publish.side_effect = DataSourceError("boom")
    with caplog.at_level(logging.ERROR):
        assert cli.main(["deepdive", "X"]) == 0
    out = capsys.readouterr().out
    assert "WARNING: dossier NOT published: " in out
    assert "boom" in out
    assert any(r.levelno >= logging.ERROR for r in caplog.records)
    assert len(_status_lines(out)) == 1


def test_deepdive_publish_half_configured_runs_then_warns(
    publish_cli, monkeypatch, capsys
):
    from app.deepdive.compose import build_dossier_publisher

    cli, run, _, _, _ = publish_cli
    # Real builder: repo set, token empty -> raises before any client/network call.
    monkeypatch.setattr(cli, "build_dossier_publisher", build_dossier_publisher)
    monkeypatch.setattr(cli.settings, "dossier_repo", "o/dossiers")
    monkeypatch.setattr(cli.settings, "dossier_token", "")
    assert cli.main(["deepdive", "X"]) == 0
    run.assert_called_once()
    out = capsys.readouterr().out
    warning = [ln for ln in out.splitlines() if "dossier NOT published" in ln]
    assert len(warning) == 1 and "DOSSIER_TOKEN" in warning[0]
    assert len(_status_lines(out)) == 1


@pytest.mark.parametrize(
    ("exc", "expected"),
    [
        (OSError(), "OSError"),
        (RuntimeError("  \n "), "RuntimeError"),
        (RuntimeError("first\nsecond"), "first"),
        (RuntimeError("\nlead blank\nmore"), "lead blank"),
    ],
)
def test_deepdive_publish_warning_is_one_line_with_reason(
    publish_cli, capsys, exc, expected
):
    cli, _, _, publish, _ = publish_cli
    publish.side_effect = exc
    assert cli.main(["deepdive", "X"]) == 0
    out = capsys.readouterr().out
    assert f"WARNING: dossier NOT published: {expected}\n" in out
    assert len(_status_lines(out)) == 1


def test_deepdive_publish_unexpected_error_keeps_exit_zero(publish_cli, capsys, caplog):
    cli, _, _, publish, _ = publish_cli
    publish.side_effect = OSError("disk")
    with caplog.at_level(logging.ERROR):
        assert cli.main(["deepdive", "X"]) == 0
    out = capsys.readouterr().out
    assert "WARNING: dossier NOT published: " in out
    assert any(r.exc_info for r in caplog.records)
    assert len(_status_lines(out)) == 1


def test_deepdive_publish_systemexit_keeps_exit_zero(publish_cli, capsys):
    cli, _, _, publish, _ = publish_cli
    publish.side_effect = SystemExit(2)
    assert cli.main(["deepdive", "X"]) == 0
    assert "WARNING: dossier NOT published: " in capsys.readouterr().out


def test_deepdive_publishes_before_site_refresh(publish_cli, monkeypatch, capsys):
    cli, _, _, publish, _ = publish_cli
    order: list[str] = []

    def fake_publish(*a, **k):
        order.append("publish")
        return "r/Watchlist/X_2026-10-25.md"

    def fake_render(argv):
        order.append("render")
        return 0

    monkeypatch.setattr(cli, "publish_dossier", fake_publish)
    monkeypatch.setattr(cli, "render_site", fake_render)
    assert cli.main(["deepdive", "X", "--site"]) == 0
    assert order == ["publish", "render"]
    assert "Published to:" in capsys.readouterr().out
