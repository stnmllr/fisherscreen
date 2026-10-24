# Dossier Publishing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every successful deep dive (PC or server) is published to the private repo `stnmllr/fisherscreen-dossiers`; the PC vault and the server-built viewer read from there.

**Architecture:** A small `publish_dossier` function pushes the written dossier via the existing `GitHubClientImpl` (repo + token from new settings). The CLI calls it after writing, never lets a publish failure change the exit code, and prints exactly one status line that the start UI parses into `RunRecord.published`. On the server a oneshot systemd service on a 5-minute timer pulls a read-only clone and rebuilds the viewer into a new directory, switching `/var/www/fisher` via symlink.

**Tech Stack:** Python 3.12, httpx (via `GitHubClientImpl`), FastAPI/Jinja2 (start UI), bash + systemd (server), pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-dossier-publishing-design.md`

## Global Constraints

- Env vars use the prefix `FISHERSCREEN_`: `FISHERSCREEN_DOSSIER_REPO`, `FISHERSCREEN_DOSSIER_TOKEN`, `FISHERSCREEN_DOSSIER_BRANCH` (default `main`).
- Repo layout: one folder `Watchlist/`, file names unchanged (`<TICKER>_<YYYY-MM-DD>.md`).
- Commit message: `Publish <TICKER> deep dive <YYYY-MM-DD> (<host>)`, host = `socket.gethostname()`.
- Status lines, exactly one per successful run (verbatim):
  `Published to: <repo>/Watchlist/<file>` · `WARNING: dossier NOT published: <reason>` · `Dossier not published (--no-publish)` · `Dossier not published (no dossier repo configured)`.
- A publish failure never changes the exit code (stays 0) and is never silent: the WARNING line plus `logger.error`/`logger.exception`.
- No new dependency. No change to `app/viewer/`. `FISHERSCREEN_GITHUB_TOKEN` (Tool A) is not reused.
- Invocation: `uv run python -m pytest -m "not integration"`, `uv run python -m black .` (never the `.exe` shims). Coverage floor 90 %.
- User-facing UI text and docs in German; code, commits, docstrings in English. Docs give commands in cmd.exe syntax (PC) or bash (server).

## Review Focus

- **Half-configured publishing** (repo set, token empty or vice versa): the paid run must still happen; the misconfiguration surfaces after the run as `WARNING: dossier NOT published: …`, never as an abort before the run → test in Task 2.
- **Non-`DataSourceError` failure while publishing** (e.g. `OSError` reading the dossier, unexpected exception): exit code stays 0, WARNING line printed, traceback logged → test in Task 2.
- **`--site` together with publishing:** publish runs first (the paid result goes out before a slow renderer), both outputs appear → test in Task 2.
- **Refresh cleanup deleting the wrong build:** pruning must never remove the build `current` points to, nor `legacy-*` → guarded in the script (Task 4) and checked in the server acceptance.
- **A broken build or failed pull on the server:** the live site stays on the previous build, the service exits non-zero → Task 4 acceptance.

---

### Task 1: Settings, `publish_dossier`, publisher builder

**Files:**
- Modify: `app/config.py`, `.env.example`
- Create: `app/deepdive/publish.py`
- Modify: `app/deepdive/compose.py`
- Test: `tests/deepdive/test_publish.py`, `tests/deepdive/test_compose.py`, `tests/test_config.py`

**Interfaces:**
- Produces:
  - `settings.dossier_repo: str = ""`, `settings.dossier_token: str = ""`, `settings.dossier_branch: str = "main"`
  - `app.deepdive.publish.DOSSIER_REPO_DIR: Final[str] = "Watchlist"`
  - `publish_dossier(path: Path, *, github: GitHubClient, repo: str, host: str) -> str` — pushes `path` to `Watchlist/<path.name>` with the commit message above; returns `"<repo>/Watchlist/<name>"`; lets `DataSourceError` from the client propagate.
  - `app.deepdive.compose.build_dossier_publisher() -> GitHubClientImpl | None` — `None` when `settings.dossier_repo` is empty; otherwise `GitHubClientImpl(token=settings.dossier_token, repo=settings.dossier_repo, branch=settings.dossier_branch)` (raises `DataSourceError` when the token is empty — Task 2 handles that).

- [ ] **Step 1: Write failing tests**

```python
# tests/deepdive/test_publish.py
def test_publish_dossier_pushes_to_watchlist_with_host_in_message(tmp_path):
    f = tmp_path / "SU.PA_2026-10-24.md"; f.write_text("# x", encoding="utf-8")
    gh = FakeGitHub()
    out = publish_dossier(f, github=gh, repo="stnmllr/fisherscreen-dossiers", host="tools-prod-01")
    assert gh.calls == [("Watchlist/SU.PA_2026-10-24.md", "# x",
                         "Publish SU.PA deep dive 2026-10-24 (tools-prod-01)")]
    assert out == "stnmllr/fisherscreen-dossiers/Watchlist/SU.PA_2026-10-24.md"

def test_publish_dossier_propagates_data_source_error(tmp_path): ...  # FakeGitHub raising DataSourceError -> raises

def test_publish_dossier_splits_ticker_and_date_at_last_underscore(tmp_path):
    # "NOVO-B.CO_2026-05-26.md" -> message "Publish NOVO-B.CO deep dive 2026-05-26 (pc)"
```

`tests/deepdive/test_compose.py`: `build_dossier_publisher()` returns `None` with `dossier_repo=""`; returns a `GitHubClientImpl` with repo/branch set when configured (monkeypatch `settings`). `tests/test_config.py`: defaults `""`, `""`, `"main"` and env override.

- [ ] **Step 2: Run, expect FAIL** — `uv run python -m pytest tests/deepdive/test_publish.py tests/deepdive/test_compose.py tests/test_config.py -q` → ImportError / AttributeError.

- [ ] **Step 3: Implement** the three settings, `publish_dossier` (ticker/date from `path.stem.rsplit("_", 1)`; read text as UTF-8), `build_dossier_publisher`; add the three lines (empty values) with a one-line comment to `.env.example`.

- [ ] **Step 4: Run, expect PASS**, then full suite + `uv run python -m black --check .`.

- [ ] **Step 5: Commit** — `git commit -m "Add dossier publishing to a data repo (settings, publish_dossier)"`

---

### Task 2: Publish from the `deepdive` CLI

**Files:**
- Modify: `app/deepdive/__main__.py`
- Test: `tests/deepdive/test_cli.py`

**Interfaces:**
- Consumes: `build_dossier_publisher`, `publish_dossier`, `settings.dossier_repo` (Task 1).
- Produces: `deepdive --no-publish` flag; `_publish(out: Path, *, no_publish: bool) -> None` that prints exactly one status line (Global Constraints) and never raises. Called after `print(f"Dossier written to: {out}")` and `sys.stdout.flush()`, **before** `_refresh_site`.

- [ ] **Step 1: Write failing tests** (style of the existing CLI tests: monkeypatch `run_deep_dive` and the builders on `app.deepdive.__main__`, capture stdout with `capsys`)

```python
def test_deepdive_publishes_after_writing(...):      # fake publisher; stdout has "Published to: stnmllr/fisherscreen-dossiers/Watchlist/X_2026-10-25.md"; exit 0
def test_deepdive_no_publish_flag(...):              # "Dossier not published (--no-publish)"; publisher never built
def test_deepdive_publish_unconfigured(...):         # dossier_repo="" -> "Dossier not published (no dossier repo configured)"
def test_deepdive_publish_failure_keeps_exit_zero(..., caplog):  # publish raises DataSourceError -> exit 0, "WARNING: dossier NOT published: " in stdout, ERROR in caplog
def test_deepdive_publish_half_configured_runs_then_warns(...):  # repo set, token "" -> run_deep_dive WAS called, exit 0, WARNING line
def test_deepdive_publish_unexpected_error_keeps_exit_zero(...): # publish raises OSError -> exit 0, WARNING line, traceback logged
def test_deepdive_publishes_before_site_refresh(...):            # --site: "Published to" appears before the render_site call (record call order)
def test_deepdive_exactly_one_status_line(...):                  # each case above: exactly one of the four line prefixes
```

- [ ] **Step 2: Run, expect FAIL** — `uv run python -m pytest tests/deepdive/test_cli.py -q`.

- [ ] **Step 3: Implement** `--no-publish` and `_publish`: catch `(Exception, SystemExit)` like `_refresh_site` — with a comment that the paid dossier is on disk and the failure is reported, not swallowed; the builder is called inside `_publish` so a half-configured setup fails there, after the run.

- [ ] **Step 4: Run, expect PASS**, full suite, black.

- [ ] **Step 5: Commit** — `git commit -m "Publish the dossier after a successful deep dive"`

---

### Task 3: Start UI shows the publish status

**Files:**
- Modify: `app/deepdive_ui/runs.py`, `app/deepdive_ui/server.py`, `app/deepdive_ui/templates/index.html`, `app/deepdive_ui/templates/_run.html`
- Test: `tests/deepdive_ui/test_runs.py`, `tests/deepdive_ui/test_server.py`, `tests/deepdive_ui/fake_deepdive.py`

**Interfaces:**
- Consumes: the four status lines (Task 2).
- Produces: `RunRequest.no_publish: bool = False` → argv `--no-publish`; `RunRecord.published: bool | None = None` (default keeps old JSON records loadable), set at finish from the log: `Published to:` → `True`, `WARNING: dossier NOT published:` → `False`, otherwise `None`; `RunBody.no_publish`; `_record_view` sets `viewer_link` only if `viewer_url` and `status == "ok"` and `published is True`, plus `published_text`: `"veröffentlicht"` / `"nicht veröffentlicht"` / `None`.

- [ ] **Step 1: Write failing tests**
  - `fake_deepdive.py`: new option to print a chosen status line.
  - `test_runs.py`: `published` is `True` / `False` / `None` for the three line kinds and for no line; `--no-publish` lands in argv; a pre-existing JSON record without `published` still loads (`None`).
  - `test_server.py`: `no_publish` passes through to `RunRequest`; `viewer_link` only for `published is True`; `_run.html` shows "ok · veröffentlicht", "ok · nicht veröffentlicht" (with a warning CSS class), plain "ok" for `None`; page has the checkbox "Nicht veröffentlichen (`--no-publish`)" and the hint "erscheint im Viewer innerhalb von ~5 min" next to the link.

- [ ] **Step 2: Run, expect FAIL** — `uv run python -m pytest tests/deepdive_ui -q`.

- [ ] **Step 3: Implement** as in Interfaces; regexes anchored like `_DOSSIER_LINE` (`re.MULTILINE`, line start).

- [ ] **Step 4: Run, expect PASS**, full suite (coverage ≥ 90 %), black, `node --check` on the extracted inline script (as before).

- [ ] **Step 5: Commit** — `git commit -m "Show the publish status of a run in the start UI"`

---

### Task 4: Server viewer refresh + runbook + docs

**Files:**
- Create: `infra/hetzner/fisherscreen-viewer-refresh.sh`, `infra/hetzner/fisherscreen-viewer.service`, `infra/hetzner/fisherscreen-viewer.timer`
- Modify: `infra/hetzner/env.example` (add `FISHERSCREEN_DOSSIER_REPO=stnmllr/fisherscreen-dossiers`, `FISHERSCREEN_DOSSIER_TOKEN=`, set `FISHERSCREEN_DEEPDIVE_UI_VIEWER_URL=https://macro.stnmllr.com/fisher` again, comment why it is safe now)
- Create: `docs/superpowers/specs/2026-10-25-dossier-publishing-runbook.md`
- Modify: `Projektstand.md`, `CLAUDE.md` (output table: dossiers are published to `stnmllr/fisherscreen-dossiers`, vault folder `FisherScreen\Deep Dives`)

**Interfaces:**
- Consumes: viewer CLI `python -m app.viewer --in <dir> --out <dir>` (unchanged).
- Produces (server paths, fixed):
  - clone `/opt/fisherscreen-dossiers` (read-only deploy key `~stef/.ssh/fisherscreen-dossiers-ro`, host alias `github-dossiers` in `~stef/.ssh/config`)
  - builds `/var/www/fisher-builds/<short-sha>/`, pointer `/var/www/fisher-builds/current` (symlink), stamp `/var/www/fisher-builds/.built-sha`
  - `/var/www/fisher` → symlink to `/var/www/fisher-builds/current`; legacy site kept at `/var/www/fisher-builds/legacy-2026-10-25`

- [ ] **Step 1: Write `fisherscreen-viewer-refresh.sh`** (`set -euo pipefail`): pull `--ff-only`; if HEAD equals `.built-sha` and `current` resolves → exit 0; build into `<short-sha>.tmp`, rename to `<short-sha>`; `ln -sfn <short-sha> current.tmp && mv -T current.tmp current`; write `.built-sha`; prune build dirs except the two newest **and** the `current` target **and** `legacy-*`. Any failure before the switch exits non-zero without touching `current`.

- [ ] **Step 2: Write the units** — `fisherscreen-viewer.service`: `Type=oneshot`, `User=stef`, `ExecStart=/opt/fisherscreen/infra/hetzner/fisherscreen-viewer-refresh.sh`; `fisherscreen-viewer.timer`: `OnBootSec=2min`, `OnUnitActiveSec=5min`, `Persistent=false`.

- [ ] **Step 3: Write the runbook** (style of `2026-10-24-deepdive-ui-hetzner-runbook.md`, cmd.exe for PC, bash for server):
  1. `gh repo create stnmllr/fisherscreen-dossiers --private` + README; fine-grained PAT (only this repo, Contents: read/write) — Stephan in GitHub settings.
  2. Server: deploy key (`ssh-keygen -t ed25519 -N "" -f ~/.ssh/fisherscreen-dossiers-ro`), add as **read-only** deploy key, ssh config alias, clone to `/opt/fisherscreen-dossiers`.
  3. `/etc/fisherscreen/env`: `FISHERSCREEN_DOSSIER_REPO`, `FISHERSCREEN_DOSSIER_TOKEN`, viewer URL; `git pull` + `uv sync --frozen --no-default-groups` in `/opt/fisherscreen`; restart `fisherscreen-deepdive`.
  4. **Symlink check first:** test that Caddy serves through a symlink (`/var/www/fisher-test` → a dir with `index.html`, temporary) before switching; then `sudo install -d -o stef -g stef /var/www/fisher-builds`, `sudo mv /var/www/fisher /var/www/fisher-builds/legacy-2026-10-25`, `sudo ln -s /var/www/fisher-builds/current /var/www/fisher`, run the service once, enable the timer.
  5. PC: `git clone` to `D:\entwicklung\fisherscreen-dossiers`; `mklink /J "D:\Obsidian\stef_remote\Wissen\Finanzen\FisherScreen\Deep Dives" "D:\entwicklung\fisherscreen-dossiers\Watchlist"`; `.env`: repo + token.
  6. Acceptance per spec §8 (PC run, server run, invalid token, legacy kept); rollback: `sudo ln -sfn /var/www/fisher-builds/legacy-2026-10-25 /var/www/fisher`, disable timer.

- [ ] **Step 4: Verify** — `bash -n infra/hetzner/fisherscreen-viewer-refresh.sh` (syntax), `uv run python -m black --check .`, full suite; `tests/test_gitignore_build_context.py` still green.

- [ ] **Step 5: Commit** — `git commit -m "Add server viewer refresh timer and dossier publishing runbook"`

---

### Task 5: Server and PC setup (Stephan + Claude, per runbook)

Not code. Executed together after merge, following the runbook; `sudo`, the PAT and the GitHub deploy-key dialog are Stephan's. Acceptance per spec §8. Record the outcome in the runbook ("Durchgeführt …") and `Projektstand.md`.
