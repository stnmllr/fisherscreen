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


def test_help_exits_zero():
    with pytest.raises(SystemExit) as exc:
        main(["deepdive", "--help"])
    assert exc.value.code == 0


def test_no_command_exits_two():
    with pytest.raises(SystemExit) as exc:
        main([])
    assert exc.value.code == 2


def test_deepdive_skeleton_returns_zero_and_prints_notice(capsys):
    rc = main(["deepdive", "NOVO-B.CO"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "NOVO-B.CO" in out
    assert "Phase B.1" in out
