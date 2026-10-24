from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.deepdive.peer_suggest import PeerSuggestion
from app.deepdive.preflight import PreflightResult, SymbolCheck
from app.deepdive_ui.runs import RunManager
from app.deepdive_ui.server import PreflightTokens, create_app
from app.errors import DataSourceError

FAKE = Path(__file__).with_name("fake_deepdive.py")
PEERS = ["LLY", "PFE", "MRK"]


def _check(symbol: str, ok: bool = True) -> SymbolCheck:
    return SymbolCheck(
        symbol=symbol,
        ok=ok,
        name=f"{symbol} Inc" if ok else None,
        currency="USD" if ok else None,
        market_cap=1.5e11 if ok else None,
        message="gefunden" if ok else "nicht gefunden",
    )


def _result(
    ticker: str = "NVO",
    kind: str = "full",
    peers_ok: bool = True,
) -> PreflightResult:
    can_start = peers_ok and kind in ("full", "quant_only")
    return PreflightResult(
        ticker=_check(ticker),
        peers=[_check(p, peers_ok) for p in PEERS],
        dossier_kind=kind,  # type: ignore[arg-type]
        dossier_note="20-F via ADR NVO" if kind == "full" else "kein 10-K/20-F",
        no_sec_source_reason="no_annual_form" if kind == "quant_only" else None,
        can_start=can_start,
        needs_quant_only_ack=kind == "quant_only",
    )


class FakePreflight:
    def __init__(
        self, result: PreflightResult | None = None, error: Exception | None = None
    ) -> None:
        self.result = result or _result()
        self.error = error
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, ticker: str, peers: list[str]) -> PreflightResult:
        self.calls.append((ticker, peers))
        if self.error is not None:
            raise self.error
        return self.result


class FakePeers:
    def __init__(
        self, data: dict[str, dict[str, Any]] | None = None, fail: bool = False
    ) -> None:
        self.data = data or {}
        self.fail = fail

    def __call__(self, ticker: str) -> dict[str, Any] | None:
        if self.fail:
            raise DataSourceError("Firestore get failed: unavailable")
        return self.data.get(ticker)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def manager(tmp_path: Path) -> RunManager:
    return RunManager(
        tmp_path / "runs", base_command=[sys.executable, str(FAKE)], cwd=tmp_path
    )


def _client(
    manager: RunManager,
    *,
    preflight: FakePreflight | None = None,
    peers: FakePeers | None = None,
    clock: Clock | None = None,
    viewer_url: str = "",
    root_path: str = "",
) -> TestClient:
    app = create_app(
        preflight=preflight or FakePreflight(),
        peers_lookup=peers or FakePeers(),
        run_manager=manager,
        root_path=root_path,
        viewer_url=viewer_url,
        preflight_ttl_minutes=15,
        clock=clock or Clock(),
    )
    return TestClient(app)


def _preflight(
    client: TestClient, ticker: str = "nvo", peers: list[str] | None = None
) -> dict:
    res = client.post(
        "/api/preflight", json={"ticker": ticker, "peers": peers or PEERS}
    )
    assert res.status_code == 200
    return res.json()


def _start(client: TestClient, token: str, **extra: Any) -> Any:
    body = {"ticker": "NVO", "peers": PEERS, "preflight_token": token, **extra}
    return client.post("/api/runs", json=body)


def test_health(manager: RunManager) -> None:
    assert _client(manager).get("/health").json() == {"status": "ok"}


def test_index_renders_empty_history(manager: RunManager) -> None:
    res = _client(manager, root_path="/deepdive/").get("/")
    assert res.status_code == 200
    assert "Noch keine Läufe." in res.text
    assert 'data-base="/deepdive"' in res.text
    assert 'maxlength="200"' in res.text
    assert "<script src" not in res.text  # nothing external to load


def test_index_check_ui_names_rows_and_real_block_reason(manager: RunManager) -> None:
    # The JS is not unit-tested; this pins the user-visible strings of the
    # 2026-10-24 browser-test fix (empty peer showed as quant-only blocker).
    text = _client(manager).get("/").text
    assert "<th>Feld</th><th>Symbol</th>" in text
    assert 'cell(tr, "Peer " + slot)' in text
    # slot numbers come from the API only (missing_peer_slots), no client copy
    assert "givenSlots(r, missing)" in text
    # caps always carry their currency (check table and chips)
    assert "formatCap(c.market_cap, c.currency)" in text
    assert "formatCap(s.market_cap, s.currency)" in text
    assert "peerSlots" not in text
    assert '"(leer)"' in text
    assert "Bitte einen Ticker eingeben" in text
    assert "genau drei Peers eingeben" not in text  # fewer peers -> suggestions
    # missing peer slots: neutral row + hint verdict, suggestion chips
    assert "fehlt, Vorschlag unten" in text
    assert "Vorschlag wählen oder eintragen" in text
    assert '"Vorschläge (gleiche Branche: "' in text
    assert "gleicher Sektor" in text
    assert '" · Stand "' in text
    assert 'id="suggest-note"' in text
    assert "hint-row" in text
    assert '" — Start gesperrt: " + block.text' in text
    # quant-only sentence shows the human note first, not the reason code
    assert "(note || r.no_sec_source_reason" in text


def test_stored_peers_found(manager: RunManager) -> None:
    peers = FakePeers(
        {
            "NVO": {
                "peers": PEERS,
                "rationale": "Big <Pharma>",
                "last_updated": "2026-09-04T10:00:00+00:00",
            }
        }
    )
    res = _client(manager, peers=peers).get("/api/peers/nvo")
    assert res.status_code == 200
    assert res.json() == {
        "peers": PEERS,
        "rationale": "Big <Pharma>",
        "last_updated": "2026-09-04T10:00:00+00:00",
    }


def test_stored_peers_missing_is_empty(manager: RunManager) -> None:
    assert _client(manager).get("/api/peers/ASML.AS").json() == {}


def test_stored_peers_outage_is_503_not_empty(manager: RunManager) -> None:
    res = _client(manager, peers=FakePeers(fail=True)).get("/api/peers/NVO")
    assert res.status_code == 503
    assert "gespeicherte Peers nicht abrufbar" in res.json()["detail"]


def test_stored_peers_invalid_symbol(manager: RunManager) -> None:
    assert _client(manager).get("/api/peers/--site").status_code == 422


def test_preflight_normalizes_and_issues_token(manager: RunManager) -> None:
    fake = FakePreflight()
    data = _preflight(
        _client(manager, preflight=fake), "  nvo ", ["lly", " pfe", "mrk "]
    )
    assert fake.calls == [("NVO", PEERS)]
    assert data["dossier_kind"] == "full"
    assert data["ticker"]["symbol"] == "NVO"
    assert len(data["peers"]) == 3
    assert data["preflight_token"]


def test_preflight_failing_check_gets_no_token(manager: RunManager) -> None:
    fake = FakePreflight(_result(peers_ok=False))
    assert _preflight(_client(manager, preflight=fake))["preflight_token"] is None


@pytest.mark.parametrize(
    ("sent", "passed"),
    [
        ([], []),
        (["lly"], ["LLY"]),
        (["LLY", "", " "], ["LLY", "", ""]),
        (["", "pfe", "MRK"], ["", "PFE", "MRK"]),
        (PEERS, PEERS),
    ],
)
def test_preflight_accepts_zero_to_three_peers_keeps_empty_slots_in_position(
    manager: RunManager, sent: list[str], passed: list[str]
) -> None:
    fake = FakePreflight()
    res = _client(manager, preflight=fake).post(
        "/api/preflight", json={"ticker": "NVO", "peers": sent}
    )
    assert res.status_code == 200
    assert fake.calls == [("NVO", passed)]


def test_preflight_peers_optional_in_body(manager: RunManager) -> None:
    fake = FakePreflight()
    res = _client(manager, preflight=fake).post(
        "/api/preflight", json={"ticker": "NVO"}
    )
    assert res.status_code == 200
    assert fake.calls == [("NVO", [])]


@pytest.mark.parametrize(
    "body",
    [
        {"ticker": "NVO", "peers": ["A", "B", "C", "D"]},
        {"ticker": "", "peers": PEERS},
        {"ticker": "   ", "peers": PEERS},
        {"peers": PEERS},
    ],
)
def test_preflight_rejects_bad_body(manager: RunManager, body: dict) -> None:
    fake = FakePreflight()
    res = _client(manager, preflight=fake).post("/api/preflight", json=body)
    assert res.status_code == 422
    assert fake.calls == []


def test_preflight_passes_missing_slots_and_suggestions_through(
    manager: RunManager,
) -> None:
    result = PreflightResult(
        ticker=SymbolCheck(
            symbol="SAF.PA",
            ok=True,
            name="SAFRAN",
            currency="EUR",
            market_cap=9.0e10,
            message="gefunden",
            industry="Aerospace & Defense",
            sector="Industrials",
        ),
        peers=[_check("RR.L"), _check("AIR.PA")],
        dossier_kind="quant_only",
        dossier_note="kein SEC-Registrant",
        no_sec_source_reason="not_sec_registrant",
        can_start=False,
        needs_quant_only_ack=True,
        missing_peer_slots=[3],
        peer_suggestions=[
            PeerSuggestion(
                symbol="MTX.DE",
                name="MTU Aero Engines",
                market_cap=1.23e10,
                currency="EUR",
                match="industry",
                industry="Aerospace & Defense",
                cached_at="2026-10-20T08:00:00+00:00",
            ),
            PeerSuggestion(
                symbol="SIE.DE",
                name="Siemens",
                market_cap=1.5e11,
                currency="EUR",
                match="sector",
                industry="Specialty Industrial Machinery",
                cached_at=None,
            ),
        ],
        suggestion_note=None,
    )
    data = _preflight(
        _client(manager, preflight=FakePreflight(result)),
        "SAF.PA",
        ["RR.L", "AIR.PA", ""],
    )
    assert data["preflight_token"] is None  # fewer than three: no start
    assert data["missing_peer_slots"] == [3]
    assert data["ticker"]["industry"] == "Aerospace & Defense"
    assert [p["symbol"] for p in data["peers"]] == ["RR.L", "AIR.PA"]
    assert data["peer_suggestions"][0] == {
        "symbol": "MTX.DE",
        "name": "MTU Aero Engines",
        "market_cap": 1.23e10,
        "currency": "EUR",
        "match": "industry",
        "industry": "Aerospace & Defense",
        "cached_at": "2026-10-20T08:00:00+00:00",
    }
    assert data["peer_suggestions"][1]["match"] == "sector"
    assert data["suggestion_note"] is None


def test_preflight_passes_suggestion_note_through(manager: RunManager) -> None:
    result = PreflightResult(
        ticker=_check("NVO"),
        peers=[],
        dossier_kind="full",
        dossier_note="20-F via ADR NVO",
        no_sec_source_reason=None,
        can_start=False,
        needs_quant_only_ack=False,
        missing_peer_slots=[1, 2, 3],
        suggestion_note="Vorschläge nicht abrufbar (Quelle nicht erreichbar)",
    )
    data = _preflight(_client(manager, preflight=FakePreflight(result)), "NVO", [])
    assert data["peer_suggestions"] == []
    assert data["suggestion_note"].startswith("Vorschläge nicht abrufbar")


def test_preflight_unexpected_source_error_is_503(manager: RunManager) -> None:
    fake = FakePreflight(error=DataSourceError("OpenFIGI down"))
    res = _client(manager, preflight=fake).post(
        "/api/preflight", json={"ticker": "NVO", "peers": PEERS}
    )
    assert res.status_code == 503


def test_start_without_token_is_422(manager: RunManager) -> None:
    res = _start(_client(manager), "")
    assert res.status_code == 422
    assert manager.list() == []


def test_start_with_token_for_other_peers_is_422(manager: RunManager) -> None:
    client = _client(manager)
    token = _preflight(client)["preflight_token"]
    res = client.post(
        "/api/runs",
        json={
            "ticker": "NVO",
            "peers": ["LLY", "PFE", "ABBV"],
            "preflight_token": token,
        },
    )
    assert res.status_code == 422


def test_expired_token_is_422(manager: RunManager) -> None:
    clock = Clock()
    client = _client(manager, clock=clock)
    token = _preflight(client)["preflight_token"]
    clock.now += 15 * 60 + 1
    assert _start(client, token).status_code == 422


def test_quant_only_requires_ack(manager: RunManager) -> None:
    client = _client(manager, preflight=FakePreflight(_result(kind="quant_only")))
    token = _preflight(client)["preflight_token"]
    assert _start(client, token).status_code == 422
    res = _start(client, token, quant_only_ack=True)  # token not consumed by the 422
    assert res.status_code == 201
    assert res.json()["quant_only_ack"] is True
    manager.join(timeout=30)


def test_rationale_too_long_is_422(manager: RunManager) -> None:
    client = _client(manager)
    token = _preflight(client)["preflight_token"]
    assert _start(client, token, rationale="x" * 201).status_code == 422


def test_start_run_and_poll_until_done(tmp_path: Path) -> None:
    manager = _manager_with(tmp_path, "--status-line", "Published to: d/W/F.md")
    client = _client(manager, viewer_url="https://example.test/fisher/")
    token = _preflight(client)["preflight_token"]
    res = _start(client, token, rationale="  Big Pharma  ", no_insider=True, site=True)
    assert res.status_code == 201
    record = res.json()
    assert record["status"] == "running"
    assert record["rationale"] == "Big Pharma"
    assert record["flags"] == {"no_cache": False, "no_insider": True, "site": True}
    assert record["viewer_link"] is None
    # single use: the token is consumed by the successful start
    manager.join(timeout=30)
    assert _start(client, token).status_code == 422

    run_id = record["run_id"]
    status = client.get(f"/api/runs/{run_id}").json()
    assert status["status"] == "ok"
    assert status["exit_text"] == "ok"
    assert status["dossier_path"] == "output/Watchlist/FAKE_2026-10-24.md"
    assert status["viewer_link"] == "https://example.test/fisher/ticker/NVO.html"
    assert "Dossier written to" in status["log_tail"]

    partial = client.get(f"/runs/{run_id}")
    assert partial.status_code == 200
    assert 'data-status="ok"' in partial.text
    assert "https://example.test/fisher/ticker/NVO.html" in partial.text

    history = client.get("/api/runs").json()
    assert [r["run_id"] for r in history] == [run_id]
    page = client.get("/")
    assert run_id in page.text
    assert "Noch keine Läufe." not in page.text


def _manager_with(tmp_path: Path, *opts: str) -> RunManager:
    return RunManager(
        tmp_path / "runs",
        base_command=[sys.executable, str(FAKE), *opts],
        cwd=tmp_path,
    )


def test_index_has_no_publish_checkbox_and_sends_it(manager: RunManager) -> None:
    text = _client(manager).get("/").text
    assert 'id="no_publish"' in text
    assert "Nicht veröffentlichen (<code>--no-publish</code>)" in text
    assert 'no_publish: $("no_publish").checked' in text


def test_no_publish_passes_through_to_the_cli(tmp_path: Path) -> None:
    manager = _manager_with(tmp_path)
    client = _client(manager)
    token = _preflight(client)["preflight_token"]
    run_id = _start(client, token, no_publish=True).json()["run_id"]
    manager.join(timeout=30)
    record = manager.get(run_id)
    assert record is not None
    assert "--no-publish" in record.argv


@pytest.mark.parametrize(
    ("line", "text", "link", "css"),
    [
        ("Published to: d/Watchlist/F.md", "ok · veröffentlicht", True, False),
        (
            "WARNING: dossier NOT published: boom",
            "ok · nicht veröffentlicht",
            False,
            True,
        ),
        ("Dossier not published (--no-publish)", None, False, False),
    ],
)
def test_publish_status_in_view_and_partial(
    tmp_path: Path, line: str, text: str | None, link: bool, css: bool
) -> None:
    manager = _manager_with(tmp_path, "--status-line", line)
    client = _client(manager, viewer_url="https://example.test/fisher")
    run_id = _start(client, _preflight(client)["preflight_token"]).json()["run_id"]
    manager.join(timeout=30)
    data = client.get(f"/api/runs/{run_id}").json()
    assert data["published_text"] == (text.split(" · ")[1] if text else None)
    assert (data["viewer_link"] is not None) is link
    html = client.get(f"/runs/{run_id}").text
    if text:
        assert text in html
    else:
        assert "veröffentlicht" not in html
    assert ("st-warn" in html) is css
    assert ("erscheint im Viewer innerhalb von ~5 min" in html) is link
    assert ("Im Viewer öffnen" in html) is link


def test_no_viewer_link_without_viewer_url(manager: RunManager) -> None:
    client = _client(manager)
    token = _preflight(client)["preflight_token"]
    run_id = _start(client, token).json()["run_id"]
    manager.join(timeout=30)
    assert client.get(f"/api/runs/{run_id}").json()["viewer_link"] is None
    assert "Im Viewer öffnen" not in client.get(f"/runs/{run_id}").text


def test_second_start_while_running_is_409(tmp_path: Path) -> None:
    gate = tmp_path / "gate"
    manager = RunManager(
        tmp_path / "runs",
        base_command=[sys.executable, str(FAKE), "--wait-for", str(gate)],
        cwd=tmp_path,
    )
    client = _client(manager)
    first = _start(client, _preflight(client)["preflight_token"])
    assert first.status_code == 201
    run_id = first.json()["run_id"]

    page = client.get("/")  # running run is shown and polled
    assert 'data-status="running"' in page.text
    assert "läuft seit" in client.get(f"/runs/{run_id}").text

    second_token = _preflight(client)["preflight_token"]
    second = _start(client, second_token)
    assert second.status_code == 409
    assert "läuft noch" in second.json()["detail"]

    gate.write_text("go", encoding="utf-8")
    manager.join(timeout=30)
    assert client.get(f"/api/runs/{run_id}").json()["status"] == "ok"
    # the 409 did not consume the token: a retry after the first run works
    assert _start(client, second_token).status_code == 201
    manager.join(timeout=30)


def test_failed_run_partial_shows_exit_text(tmp_path: Path) -> None:
    manager = RunManager(
        tmp_path / "runs",
        base_command=[sys.executable, str(FAKE), "--exit", "2", "--no-dossier"],
        cwd=tmp_path,
    )
    client = _client(manager, viewer_url="https://example.test")
    run_id = _start(client, _preflight(client)["preflight_token"]).json()["run_id"]
    manager.join(timeout=30)
    data = client.get(f"/api/runs/{run_id}").json()
    assert data["status"] == "failed"
    assert data["viewer_link"] is None
    assert "Datenquelle nicht erreichbar" in client.get(f"/runs/{run_id}").text


@pytest.mark.parametrize("run_id", ["2026-10-24T20-31-07_NOPE", "..%2F..%2Fsecret"])
def test_unknown_or_bad_run_id_is_404(manager: RunManager, run_id: str) -> None:
    client = _client(manager)
    assert client.get(f"/api/runs/{run_id}").status_code == 404
    assert client.get(f"/runs/{run_id}").status_code == 404


def test_validation_error_from_manager_is_422(manager: RunManager) -> None:
    # A symbol the preflight accepted but start() rejects (defence in depth).
    client = _client(manager)
    token = client.post(
        "/api/preflight", json={"ticker": "^GSPC", "peers": PEERS}
    ).json()["preflight_token"]
    res = client.post(
        "/api/runs", json={"ticker": "^GSPC", "peers": PEERS, "preflight_token": token}
    )
    assert res.status_code == 422
    assert "ungültige Symbole" in res.json()["detail"]


def test_tokens_prune_expired_on_issue() -> None:
    clock = Clock()
    tokens = PreflightTokens(10, clock)
    old = tokens.issue("NVO", PEERS, False)
    clock.now += 11
    tokens.issue("NVO", PEERS, False)
    assert tokens.check(old, "NVO", PEERS) is None
    assert old not in tokens._tokens
