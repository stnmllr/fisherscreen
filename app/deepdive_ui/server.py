"""FastAPI app of the deep-dive start UI.

Everything external is injected into ``create_app``: the preflight runner, the
stored-peers lookup and the RunManager. Tests pass fakes; only ``__main__``
wires the real things. All routes are async; blocking work (yfinance, EDGAR,
Firestore, subprocess start, file reads) runs via ``asyncio.to_thread``.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field

from app.deepdive.preflight import PreflightResult, is_valid_symbol, normalize_symbol
from app.deepdive_ui.runs import (
    RATIONALE_MAX,
    RunManager,
    RunRecord,
    RunRequest,
    exit_code_text,
    is_valid_run_id,
)
from app.errors import DataSourceError, DeepDiveError, FisherScreenError, RunBusyError

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).with_name("templates")
HISTORY_LIMIT = 20
PEER_COUNT = 3

PreflightRunner = Callable[[str, list[str]], PreflightResult]
PeersLookup = Callable[[str], dict[str, Any] | None]


class PreflightBody(BaseModel):
    # 0-3 peers: fewer than three is a hint (suggestions), not an error.
    # Starting still needs exactly three (RunBody).
    ticker: str = Field(min_length=1, max_length=40)
    peers: list[str] = Field(default_factory=list, max_length=PEER_COUNT)


class RunBody(BaseModel):
    ticker: str = Field(min_length=1, max_length=40)
    peers: list[str] = Field(min_length=PEER_COUNT, max_length=PEER_COUNT)
    rationale: str | None = Field(default=None, max_length=RATIONALE_MAX)
    no_cache: bool = False
    no_insider: bool = False
    site: bool = False
    quant_only_ack: bool = False
    preflight_token: str = ""


@dataclass(frozen=True)
class _Token:
    ticker: str
    peers: tuple[str, ...]
    needs_quant_only_ack: bool
    expires_at: float


class PreflightTokens:
    """In-memory, short-lived, single-use proof that a preflight passed.

    Bound to the normalized ticker + peer list; remembers whether the quant-only
    acknowledgement is required. Consumed only by a successful start.
    """

    def __init__(
        self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._tokens: dict[str, _Token] = {}
        self._lock = threading.Lock()

    def issue(self, ticker: str, peers: list[str], needs_ack: bool) -> str:
        token = secrets.token_urlsafe(24)
        now = self._clock()
        with self._lock:
            self._tokens = {k: v for k, v in self._tokens.items() if v.expires_at > now}
            self._tokens[token] = _Token(
                ticker, tuple(peers), needs_ack, now + self._ttl
            )
        return token

    def check(self, token: str, ticker: str, peers: list[str]) -> _Token | None:
        with self._lock:
            entry = self._tokens.get(token)
        if entry is None or entry.expires_at <= self._clock():
            return None
        if entry.ticker != ticker or entry.peers != tuple(peers):
            return None
        return entry

    def consume(self, token: str) -> None:
        with self._lock:
            self._tokens.pop(token, None)


def _record_view(record: RunRecord, viewer_url: str) -> dict[str, Any]:
    data = asdict(record)
    data["exit_text"] = record.exit_text or (
        exit_code_text(record.exit_code) if record.status != "running" else None
    )
    data["viewer_link"] = (
        f"{viewer_url.rstrip('/')}/ticker/{record.ticker}.html"
        if viewer_url and record.status == "ok"
        else None
    )
    return data


def create_app(
    *,
    preflight: PreflightRunner,
    peers_lookup: PeersLookup,
    run_manager: RunManager,
    root_path: str = "",
    viewer_url: str = "",
    preflight_ttl_minutes: float = 15,
    clock: Callable[[], float] = time.monotonic,
) -> FastAPI:
    app = FastAPI(title="FisherScreen Deep Dive", root_path=root_path)
    tokens = PreflightTokens(preflight_ttl_minutes * 60, clock)
    base = root_path.rstrip("/")
    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True, trim_blocks=True
    )
    app.state.run_manager = run_manager
    app.state.tokens = tokens

    def render(name: str, **ctx: Any) -> str:
        return env.get_template(name).render(base=base, **ctx)

    def find_record(run_id: str) -> RunRecord:
        record = run_manager.get(run_id) if is_valid_run_id(run_id) else None
        if record is None:
            raise HTTPException(status_code=404, detail="Lauf nicht gefunden")
        return record

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        history = await asyncio.to_thread(run_manager.list, HISTORY_LIMIT)
        current = next((r for r in history if r.status == "running"), None)
        tail = (
            await asyncio.to_thread(run_manager.tail, current.run_id) if current else ""
        )
        html = render(
            "index.html",
            history=[_record_view(r, viewer_url) for r in history],
            current=_record_view(current, viewer_url) if current else None,
            tail=tail,
            rationale_max=RATIONALE_MAX,
        )
        return HTMLResponse(html)

    @app.get("/api/peers/{ticker}")
    async def stored_peers(ticker: str) -> dict[str, Any]:
        symbol = normalize_symbol(ticker)
        if not is_valid_symbol(symbol):
            raise HTTPException(status_code=422, detail="ungültiges Symbol")
        try:
            stored = await asyncio.to_thread(peers_lookup, symbol)
        except DataSourceError as exc:
            logger.warning("stored peers for %s unavailable: %s", symbol, exc)
            raise HTTPException(
                status_code=503,
                detail=f"gespeicherte Peers nicht abrufbar: {exc}",
            ) from exc
        if not stored:
            return {}
        return {
            "peers": list(stored.get("peers") or []),
            "rationale": stored.get("rationale"),
            "last_updated": stored.get("last_updated"),
        }

    @app.post("/api/preflight")
    async def run_preflight(body: PreflightBody) -> dict[str, Any]:
        ticker = normalize_symbol(body.ticker)
        if not ticker:
            raise HTTPException(status_code=422, detail="Ticker fehlt")
        # Positional: an empty field stays "" in its slot, so the preflight's
        # missing_peer_slots names the right field number.
        peers = [normalize_symbol(raw) for raw in body.peers]
        try:
            result = await asyncio.to_thread(preflight, ticker, peers)
        except FisherScreenError as exc:
            logger.warning("preflight for %s failed: %s", ticker, exc)
            raise HTTPException(
                status_code=503, detail=f"Vorprüfung nicht möglich: {exc}"
            ) from exc
        data = asdict(result)
        data["preflight_token"] = (
            tokens.issue(ticker, peers, result.needs_quant_only_ack)
            if result.can_start
            else None
        )
        return data

    @app.post("/api/runs", status_code=201)
    async def start_run(body: RunBody) -> dict[str, Any]:
        ticker = normalize_symbol(body.ticker)
        peers = [normalize_symbol(p) for p in body.peers]
        entry = tokens.check(body.preflight_token, ticker, peers)
        if entry is None:
            raise HTTPException(
                status_code=422,
                detail="Vorprüfung fehlt, ist abgelaufen oder passt nicht zu "
                "Ticker/Peers — bitte erneut prüfen",
            )
        if entry.needs_quant_only_ack and not body.quant_only_ack:
            raise HTTPException(
                status_code=422,
                detail="Nur-Quant-Dossier muss ausdrücklich bestätigt werden",
            )
        rationale = (body.rationale or "").strip() or None
        request = RunRequest(
            ticker=ticker,
            peers=peers,
            rationale=rationale,
            no_cache=body.no_cache,
            no_insider=body.no_insider,
            site=body.site,
            quant_only_ack=body.quant_only_ack,
        )
        try:
            record = await asyncio.to_thread(run_manager.start, request)
        except RunBusyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except DeepDiveError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        tokens.consume(body.preflight_token)
        return _record_view(record, viewer_url)

    @app.get("/api/runs")
    async def list_runs() -> list[dict[str, Any]]:
        history = await asyncio.to_thread(run_manager.list, HISTORY_LIMIT)
        return [_record_view(r, viewer_url) for r in history]

    @app.get("/api/runs/{run_id}")
    async def run_status(run_id: str) -> dict[str, Any]:
        record = await asyncio.to_thread(find_record, run_id)
        data = _record_view(record, viewer_url)
        data["log_tail"] = await asyncio.to_thread(run_manager.tail, run_id)
        return data

    @app.get("/runs/{run_id}", response_class=HTMLResponse)
    async def run_partial(run_id: str) -> HTMLResponse:
        record = await asyncio.to_thread(find_record, run_id)
        tail = await asyncio.to_thread(run_manager.tail, run_id)
        return HTMLResponse(
            render("_run.html", run=_record_view(record, viewer_url), tail=tail)
        )

    return app
