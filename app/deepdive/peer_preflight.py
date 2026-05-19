from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable

from app.deepdive.peer_quant import load_peer_quants
from app.errors import DataSourceError, DeepDiveError
from app.models.deep_dive_record import PeerComparison

logger = logging.getLogger(__name__)

_RATIONALE_MAX = 200
_MAX_ATTEMPTS = 5


def _clean_rationale(raw: str | None) -> str | None:
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    return trimmed[:_RATIONALE_MAX]


def _parse_triplet(raw: str) -> list[str]:
    """Split on comma, strip, require EXACTLY 3 non-empty tickers."""
    tokens = [t.strip() for t in raw.split(",")]
    tokens = [t for t in tokens if t]
    if len(tokens) != 3:
        raise DeepDiveError(
            "Peer-Auswahl benötigt genau 3 Ticker (kommagetrennt), "
            f"erhalten: {len(tokens)}"
        )
    return tokens


def _validate_resolvable(tokens: list[str], yfinance: Any) -> None:
    for tok in tokens:
        try:
            info = yfinance.get_ticker_info(tok)
        except DataSourceError as exc:
            raise DeepDiveError(
                f"✗ '{tok}' bei yfinance nicht auflösbar. Bitte genau 3 "
                f"gültige Ticker erneut eingeben."
            ) from exc
        if not info:
            raise DeepDiveError(
                f"✗ '{tok}' bei yfinance nicht auflösbar. Bitte genau 3 "
                f"gültige Ticker erneut eingeben."
            )


def _persist(
    firestore: Any, peers_collection: str, ticker: str,
    tokens: list[str], rationale: str | None,
) -> None:
    firestore.set(peers_collection, ticker, {
        "peers": tokens,
        "rationale": rationale,
        "last_updated": datetime.now(timezone.utc).isoformat(),
    })


def _build(
    tokens: list[str], rationale: str | None, yfinance: Any,
) -> PeerComparison:
    return PeerComparison(
        peers=load_peer_quants(tokens, yfinance), rationale=rationale)


def _interactive(
    *, ticker: str, firestore: Any, peers_collection: str, yfinance: Any,
    input_fn: Callable[..., str],
) -> tuple[list[str], str | None]:
    stored = firestore.get(peers_collection, ticker)
    default_peers: list[str] | None = None
    default_rationale: str | None = None
    if stored and stored.get("peers"):
        default_peers = list(stored["peers"])
        default_rationale = stored.get("rationale")

    print(
        f"Peer-Auswahl für {ticker} — genau 3 Ticker (kommagetrennt, "
        f"yfinance-Symbole)."
    )
    if default_peers:
        date = (stored.get("last_updated") or "")[:10]
        rtxt = default_rationale if default_rationale is not None else ""
        print(
            f"Letzte Peer-Eingabe ({date}): {', '.join(default_peers)}\n"
            f"Begründung: \"{rtxt}\"\n"
            f"[Enter] für unverändert, oder neue 3er-Liste:"
        )

    tokens: list[str] | None = None
    reused_default = False
    for _ in range(_MAX_ATTEMPTS):
        raw = input_fn("Peers: ")
        if not raw.strip() and default_peers:
            tokens = default_peers
            reused_default = True
            break
        try:
            cand = _parse_triplet(raw)
            _validate_resolvable(cand, yfinance)
        except DeepDiveError as exc:
            print(str(exc))
            continue
        tokens = cand
        break

    if tokens is None:
        raise DeepDiveError(
            "Peer-Auswahl nach mehreren Versuchen ungültig — abgebrochen."
        )

    # Reusing the stored default keeps its rationale verbatim — no second
    # prompt. (Re-prompting here previously clobbered the stored rationale.)
    if reused_default:
        return tokens, _clean_rationale(default_rationale)

    # New peers were entered — they deserve their own rationale.
    if default_rationale is not None:
        rat_raw = input_fn("Begründung (Enter behält alte Begründung): ")
        if not rat_raw.strip():
            return tokens, _clean_rationale(default_rationale)
        return tokens, _clean_rationale(rat_raw)

    rat_raw = input_fn("Begründung (Enter zum Überspringen): ")
    return tokens, _clean_rationale(rat_raw)


def resolve_peers(
    *,
    ticker: str,
    peers_arg: str | None,
    rationale_arg: str | None,
    is_tty: bool,
    firestore: Any,
    peers_collection: str,
    yfinance: Any,
    input_fn: Callable[..., str] = input,
) -> PeerComparison:
    """Resolve the user's 3-peer selection for a deep dive.

    --peers wins (non-interactive, no prompt). Else, on a TTY, prompt
    interactively (showing the last stored set as default). Else hard-fail
    with an actionable message.
    """
    if peers_arg is not None:
        tokens = _parse_triplet(peers_arg)
        _validate_resolvable(tokens, yfinance)
        rationale = _clean_rationale(rationale_arg)
        _persist(firestore, peers_collection, ticker, tokens, rationale)
        return _build(tokens, rationale, yfinance)

    if is_tty:
        tokens, rationale = _interactive(
            ticker=ticker, firestore=firestore,
            peers_collection=peers_collection, yfinance=yfinance,
            input_fn=input_fn)
        _persist(firestore, peers_collection, ticker, tokens, rationale)
        return _build(tokens, rationale, yfinance)

    raise DeepDiveError(
        "Peer-Trio im nicht-interaktiven Modus via "
        "--peers PEER1,PEER2,PEER3 erforderlich"
    )
