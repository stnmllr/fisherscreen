from unittest.mock import MagicMock

import pytest

from app.deepdive.peer_preflight import resolve_peers
from app.errors import DataSourceError, DeepDiveError
from app.models.deep_dive_record import PeerComparison

_COLL = "dev_deepdive_peers"


def _yf(valid=("LLY", "PFE", "MRK", "JNJ", "ABBV")):
    yf = MagicMock()

    def _info(t):
        if t in valid:
            return {"shortName": f"name-{t}"}
        raise DataSourceError(f"{t} not resolvable")

    yf.get_ticker_info.side_effect = _info
    return yf


def _fs(stored=None):
    fs = MagicMock()
    fs.get.return_value = stored
    return fs


# ---- --peers (non-interactive) path -------------------------------------

def test_peers_arg_valid_persists_and_returns():
    fs, yf = _fs(), _yf()
    pc = resolve_peers(
        ticker="NVO", peers_arg="LLY,PFE,MRK", rationale_arg="Big Pharma",
        is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)
    assert isinstance(pc, PeerComparison)
    assert [p.ticker for p in pc.peers] == ["LLY", "PFE", "MRK"]
    assert pc.rationale == "Big Pharma"
    coll, doc, payload = fs.set.call_args[0]
    assert coll == _COLL and doc == "NVO"
    assert payload["peers"] == ["LLY", "PFE", "MRK"]
    assert payload["rationale"] == "Big Pharma"
    assert "last_updated" in payload


def test_peers_arg_strips_whitespace():
    fs, yf = _fs(), _yf()
    pc = resolve_peers(
        ticker="NVO", peers_arg=" LLY , PFE ,MRK ", rationale_arg=None,
        is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)
    assert [p.ticker for p in pc.peers] == ["LLY", "PFE", "MRK"]


def test_peers_arg_not_exactly_three_raises():
    fs, yf = _fs(), _yf()
    with pytest.raises(DeepDiveError):
        resolve_peers(
            ticker="NVO", peers_arg="LLY,PFE", rationale_arg=None,
            is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)


def test_peers_arg_invalid_ticker_raises_no_prompt():
    fs, yf = _fs(), _yf()
    called = []
    with pytest.raises(DeepDiveError):
        resolve_peers(
            ticker="NVO", peers_arg="LLY,NOPE,MRK", rationale_arg=None,
            is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf,
            input_fn=lambda *_: called.append(1) or "x")
    assert called == []  # never prompted in non-interactive mode


def test_no_peers_no_tty_raises():
    fs, yf = _fs(), _yf()
    with pytest.raises(DeepDiveError, match="nicht-interaktiven Modus"):
        resolve_peers(
            ticker="NVO", peers_arg=None, rationale_arg=None,
            is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)


def test_rationale_truncated_to_200():
    fs, yf = _fs(), _yf()
    long = "x" * 250
    pc = resolve_peers(
        ticker="NVO", peers_arg="LLY,PFE,MRK", rationale_arg=long,
        is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)
    assert len(pc.rationale) == 200


def test_rationale_empty_becomes_none():
    fs, yf = _fs(), _yf()
    pc = resolve_peers(
        ticker="NVO", peers_arg="LLY,PFE,MRK", rationale_arg="   ",
        is_tty=False, firestore=fs, peers_collection=_COLL, yfinance=yf)
    assert pc.rationale is None


# ---- interactive path ----------------------------------------------------

def test_interactive_valid_first_try():
    fs, yf = _fs(), _yf()
    inputs = iter(["LLY,PFE,MRK", "My rationale"])
    pc = resolve_peers(
        ticker="NVO", peers_arg=None, rationale_arg=None,
        is_tty=True, firestore=fs, peers_collection=_COLL, yfinance=yf,
        input_fn=lambda *_: next(inputs))
    assert [p.ticker for p in pc.peers] == ["LLY", "PFE", "MRK"]
    assert pc.rationale == "My rationale"
    fs.set.assert_called_once()


def test_interactive_invalid_then_reprompt():
    fs, yf = _fs(), _yf()
    inputs = iter(["LLY,NOPE,MRK", "LLY,PFE,MRK", ""])
    pc = resolve_peers(
        ticker="NVO", peers_arg=None, rationale_arg=None,
        is_tty=True, firestore=fs, peers_collection=_COLL, yfinance=yf,
        input_fn=lambda *_: next(inputs))
    assert [p.ticker for p in pc.peers] == ["LLY", "PFE", "MRK"]
    assert pc.rationale is None  # empty rationale skipped


def test_interactive_attempt_cap_raises():
    fs, yf = _fs(), _yf()
    with pytest.raises(DeepDiveError):
        resolve_peers(
            ticker="NVO", peers_arg=None, rationale_arg=None,
            is_tty=True, firestore=fs, peers_collection=_COLL, yfinance=yf,
            input_fn=lambda *_: "BAD,BAD,BAD")


def test_interactive_reuses_stored_default_on_empty():
    stored = {"peers": ["LLY", "PFE", "MRK"],
              "rationale": "stored reason",
              "last_updated": "2026-05-01T00:00:00+00:00"}
    fs, yf = _fs(stored), _yf()
    pc = resolve_peers(
        ticker="NVO", peers_arg=None, rationale_arg=None,
        is_tty=True, firestore=fs, peers_collection=_COLL, yfinance=yf,
        input_fn=lambda *_: "")  # Enter = unchanged for both prompts
    assert [p.ticker for p in pc.peers] == ["LLY", "PFE", "MRK"]
    assert pc.rationale == "stored reason"
    fs.get.assert_called_once_with(_COLL, "NVO")


def test_interactive_new_list_overrides_stored_default():
    stored = {"peers": ["LLY", "PFE", "MRK"], "rationale": "old",
              "last_updated": "2026-05-01T00:00:00+00:00"}
    fs, yf = _fs(stored), _yf()
    inputs = iter(["JNJ,ABBV,PFE", "new reason"])
    pc = resolve_peers(
        ticker="NVO", peers_arg=None, rationale_arg=None,
        is_tty=True, firestore=fs, peers_collection=_COLL, yfinance=yf,
        input_fn=lambda *_: next(inputs))
    assert [p.ticker for p in pc.peers] == ["JNJ", "ABBV", "PFE"]
    assert pc.rationale == "new reason"
