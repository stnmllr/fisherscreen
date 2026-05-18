# Tool B Phase B.0 — Gerüst-Skeleton: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Tool B scaffold so Phase B.1 starts on a finished skeleton — CLI entrypoint, static ADR table, `DeepDiveError`, Tool-B composition root, and the `output/Watchlist/` push path.

**Architecture:** New `app/deepdive/` package mirroring the existing `app/screener/` patterns (Protocol-based services, `compose.py` composition root, pydantic/DI test style). CLI via stdlib `argparse` with `add_subparsers` (no new dependency — CLAUDE.md). Static ADR mapping as a repo-root `data/adr_table.json` (stdlib JSON, no YAML dependency) with a thin validating loader; the full `resolve()` logic is deliberately deferred to B.1-2. The deep-dive pipeline itself is **not** built here — `deepdive <TICKER>` parses args and prints a B.0-skeleton notice.

**Tech Stack:** Python 3.12, stdlib `argparse` + `json`, pydantic (existing), pytest with DI (`uv run python -m pytest`), uv, hatchling build.

**Reference:** Master-Brainstorm `docs/superpowers/brainstorm/2026-05-18-tool-b-master.md` §4 (B.0 row), B.1-Spec `docs/superpowers/specs/2026-05-18-tool-b-phase-b1-design.md` (E3, E4 — B.0 lays the foundation B.1 tasks 1/2/7 build on).

**Constraints (CLAUDE.md):** cmd.exe syntax in any user-facing instruction; `uv run python -m pytest` (never `uv run pytest` — SOPRA EPDR); 90 % coverage enforced centrally; no new dependency; English code/commits (imperative); never commit to `main` without approval.

**Acceptance (Master §4 B.0):** `uv run fisherscreen deepdive --help` runs; ADR table loads + format test green; `output/Watchlist/` exists and the vault junction is visible.

---

### Task 0: Branch

- [ ] **Step 1: Create the implementation branch**

```bash
git checkout main
git checkout -b feature/tool-b-b0-skeleton
git branch --show-current
```

Expected: `feature/tool-b-b0-skeleton`

> If the B.1 spec/master docs are not yet on `main`, branch from wherever they are reachable instead; B.0 code does not import them. Do **not** commit to `main` directly.

---

### Task 1: `DeepDiveError` exception

**Files:**
- Modify: `app/errors.py`
- Test: `tests/test_errors.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_errors.py`:

```python
def test_deepdive_subclass_base():
    from app.errors import DeepDiveError

    assert issubclass(DeepDiveError, FisherScreenError)


def test_deepdive_catchable_as_base():
    from app.errors import DeepDiveError

    with pytest.raises(FisherScreenError):
        raise DeepDiveError("ticker NOVO-B.CO not resolvable")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_errors.py -v`
Expected: FAIL — `ImportError: cannot import name 'DeepDiveError'`

- [ ] **Step 3: Add the exception**

Append to `app/errors.py`:

```python
class DeepDiveError(FisherScreenError):
    """Raised on Tool B deep-dive failures: unresolvable ticker, missing filing."""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_errors.py -v`
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add app/errors.py tests/test_errors.py
git commit -m "Add DeepDiveError to AppError hierarchy"
```

---

### Task 2: Static ADR table — data file

**Files:**
- Create: `data/adr_table.json`

- [ ] **Step 1: Create the seed table**

Create `data/adr_table.json` (seed entry per Master ADR-1: `NOVO-B.CO → NVO → CIK 0000353278 → 20-F`):

```json
{
  "version": 1,
  "entries": {
    "NOVO-B.CO": {
      "adr_ticker": "NVO",
      "cik": "0000353278",
      "form_type": "20-F"
    }
  }
}
```

- [ ] **Step 2: Verify it is valid JSON**

Run: `uv run python -c "import json,pathlib; print(json.loads(pathlib.Path('data/adr_table.json').read_text())['entries']['NOVO-B.CO'])"`
Expected: `{'adr_ticker': 'NVO', 'cik': '0000353278', 'form_type': '20-F'}`

- [ ] **Step 3: Commit**

```bash
git add data/adr_table.json
git commit -m "Add static ADR mapping table with Novo Nordisk seed"
```

---

### Task 3: ADR table loader

**Files:**
- Create: `app/deepdive/__init__.py`
- Create: `app/deepdive/adr_table.py`
- Create: `tests/deepdive/__init__.py`
- Create: `tests/deepdive/test_adr_table.py`

- [ ] **Step 1: Create empty package markers**

Create `app/deepdive/__init__.py` (empty file).
Create `tests/deepdive/__init__.py` (empty file).

- [ ] **Step 2: Write the failing tests**

Create `tests/deepdive/test_adr_table.py`:

```python
import json

import pytest

from app.deepdive.adr_table import load_adr_table
from app.errors import DeepDiveError


def test_load_seed_has_novo():
    entries = load_adr_table()
    assert entries["NOVO-B.CO"] == {
        "adr_ticker": "NVO",
        "cik": "0000353278",
        "form_type": "20-F",
    }


def test_missing_file_raises(tmp_path):
    with pytest.raises(DeepDiveError, match="not found"):
        load_adr_table(tmp_path / "nope.json")


def test_invalid_json_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text("{ not json", encoding="utf-8")
    with pytest.raises(DeepDiveError, match="not valid JSON"):
        load_adr_table(bad)


def test_missing_entries_key_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(json.dumps({"version": 1}), encoding="utf-8")
    with pytest.raises(DeepDiveError, match="entries"):
        load_adr_table(bad)


def test_bad_cik_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {"version": 1, "entries": {"X.CO": {"adr_ticker": "X", "cik": "353278", "form_type": "20-F"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="10-digit"):
        load_adr_table(bad)


def test_bad_form_type_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps(
            {"version": 1, "entries": {"X.CO": {"adr_ticker": "X", "cik": "0000000001", "form_type": "8-K"}}}
        ),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="form_type"):
        load_adr_table(bad)


def test_entry_not_object_raises(tmp_path):
    bad = tmp_path / "adr.json"
    bad.write_text(
        json.dumps({"version": 1, "entries": {"X.CO": "nope"}}),
        encoding="utf-8",
    )
    with pytest.raises(DeepDiveError, match="must be an object"):
        load_adr_table(bad)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_adr_table.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.adr_table'`

- [ ] **Step 4: Write the loader**

Create `app/deepdive/adr_table.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.errors import DeepDiveError

DEFAULT_ADR_TABLE_PATH = Path(__file__).resolve().parents[2] / "data" / "adr_table.json"
_VALID_FORM_TYPES = {"10-K", "20-F"}


def load_adr_table(path: Path | None = None) -> dict[str, dict[str, str]]:
    """Load and validate the static ADR mapping table.

    Returns the ``entries`` mapping (ticker -> {adr_ticker, cik, form_type}).
    Raises DeepDiveError on a missing file, invalid JSON, or any schema violation
    — fail loud, never return a partial/empty table silently.
    """
    table_path = path or DEFAULT_ADR_TABLE_PATH
    try:
        raw: Any = json.loads(table_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise DeepDiveError(f"ADR table not found: {table_path}") from exc
    except json.JSONDecodeError as exc:
        raise DeepDiveError(f"ADR table is not valid JSON: {exc}") from exc

    if not isinstance(raw, dict) or "entries" not in raw:
        raise DeepDiveError("ADR table missing top-level 'entries' object")
    entries = raw["entries"]
    if not isinstance(entries, dict):
        raise DeepDiveError("ADR table 'entries' must be an object")

    for ticker, entry in entries.items():
        _validate_entry(ticker, entry)
    return entries


def _validate_entry(ticker: str, entry: Any) -> None:
    if not isinstance(entry, dict):
        raise DeepDiveError(f"ADR entry for {ticker} must be an object")
    adr = entry.get("adr_ticker")
    cik = entry.get("cik")
    form = entry.get("form_type")
    if not isinstance(adr, str) or not adr:
        raise DeepDiveError(f"ADR entry for {ticker}: 'adr_ticker' must be a non-empty string")
    if not isinstance(cik, str) or not (cik.isdigit() and len(cik) == 10):
        raise DeepDiveError(f"ADR entry for {ticker}: 'cik' must be a 10-digit zero-padded string")
    if form not in _VALID_FORM_TYPES:
        raise DeepDiveError(
            f"ADR entry for {ticker}: 'form_type' must be one of {sorted(_VALID_FORM_TYPES)}"
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_adr_table.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Commit**

```bash
git add app/deepdive/__init__.py app/deepdive/adr_table.py tests/deepdive/__init__.py tests/deepdive/test_adr_table.py
git commit -m "Add validating ADR table loader"
```

---

### Task 4: Tool-B composition root

**Files:**
- Create: `app/deepdive/compose.py`
- Create: `tests/deepdive/test_compose.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_compose.py`:

```python
import app.deepdive.compose as deepdive_compose
import app.screener.compose as screener_compose


def test_build_adr_table_returns_seed():
    table = deepdive_compose.build_adr_table()
    assert "NOVO-B.CO" in table
    assert table["NOVO-B.CO"]["adr_ticker"] == "NVO"


def test_github_client_builder_is_reused_not_duplicated():
    # Tool B shares Tool A's GitHub push path — same builder, no copy.
    assert deepdive_compose.build_github_client is screener_compose.build_github_client
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_compose.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.compose'`

- [ ] **Step 3: Write the composition root**

Create `app/deepdive/compose.py`:

```python
from __future__ import annotations

from app.deepdive.adr_table import load_adr_table
from app.screener.compose import build_github_client

__all__ = ["build_adr_table", "build_github_client"]


def build_adr_table() -> dict[str, dict[str, str]]:
    """Composition entrypoint for the static ADR table.

    B.1-2 builds the full resolve() service on top of this loader.
    """
    return load_adr_table()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_compose.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add app/deepdive/compose.py tests/deepdive/test_compose.py
git commit -m "Add Tool B composition root reusing GitHub push path"
```

---

### Task 5: CLI entrypoint (argparse skeleton)

**Files:**
- Create: `app/deepdive/__main__.py`
- Create: `tests/deepdive/test_cli.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Write the failing tests**

Create `tests/deepdive/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/deepdive/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.deepdive.__main__'`

- [ ] **Step 3: Write the CLI**

Create `app/deepdive/__main__.py`:

```python
from __future__ import annotations

import argparse
import logging
import sys

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fisherscreen", description="FisherScreen CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    deepdive = subparsers.add_parser(
        "deepdive", help="Run a Tool B deep dive on one ticker"
    )
    deepdive.add_argument("ticker", help="Ticker symbol, e.g. NOVO-B.CO")
    deepdive.add_argument(
        "--model", default=None, help="Override the Gemini synthesis model"
    )
    deepdive.add_argument(
        "--no-cache",
        action="store_true",
        help="Ignore the local filing/historical caches",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logger.info(
        "deepdive skeleton invoked for ticker=%s — pipeline lands in Phase B.1",
        args.ticker,
    )
    print(
        f"deepdive '{args.ticker}': Tool B skeleton (Phase B.0). "
        "The deep-dive pipeline is implemented in Phase B.1."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/deepdive/test_cli.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Register the console script**

In `pyproject.toml`, insert this block immediately after the `[project.optional-dependencies]` block (after the closing `]` of `dev = [ ... ]`, before `[tool.pytest.ini_options]`):

```toml
[project.scripts]
fisherscreen = "app.deepdive.__main__:main"
```

- [ ] **Step 6: Re-sync and verify the console script**

Run: `uv sync`
Then run: `uv run fisherscreen deepdive --help`
Expected: argparse help text for the `deepdive` subcommand (exit 0), showing `ticker`, `--model`, `--no-cache`.

- [ ] **Step 7: Commit**

```bash
git add app/deepdive/__main__.py tests/deepdive/test_cli.py pyproject.toml uv.lock
git commit -m "Add deepdive CLI skeleton and register fisherscreen console script"
```

---

### Task 6: `output/Watchlist/` push target

**Files:**
- Create: `output/Watchlist/.gitkeep`

- [ ] **Step 1: Create the tracked directory**

Create an empty file `output/Watchlist/.gitkeep` (mirrors the existing `output/Universum/.gitkeep` convention; `output/` is **not** gitignored).

- [ ] **Step 2: Verify it is tracked, not ignored**

Run: `git check-ignore output/Watchlist/.gitkeep; echo "exit $?"`
Expected: `exit 1` (no output — the path is **not** ignored)

- [ ] **Step 3: Commit**

```bash
git add output/Watchlist/.gitkeep
git commit -m "Add output/Watchlist push target directory"
```

---

### Task 7: Full suite + coverage gate

- [ ] **Step 1: Run the entire test suite with coverage**

Run: `uv run python -m pytest`
Expected: all tests PASS; `--cov-fail-under=90` not violated (coverage line ≥ 90 %).

> If coverage dips below 90 %, the new `app/deepdive/*` modules are the likely cause — add the missing-line test rather than lowering the threshold.

- [ ] **Step 2: Commit only if Step 1 changed anything**

If no files changed, skip. Otherwise:

```bash
git add -A
git commit -m "Fix coverage gaps in deepdive skeleton"
```

---

### Task 8: Manual acceptance gate (no pytest)

This task is a **documented manual gate** — Master §4 B.0 acceptance. It is not an automated test.

- [ ] **Step 1: CLI smoke**

Run (cmd.exe): `uv run fisherscreen deepdive --help`
Confirm: subcommand help prints, exit code 0.

Run (cmd.exe): `uv run fisherscreen deepdive NOVO-B.CO`
Confirm: prints the B.0-skeleton notice mentioning `NOVO-B.CO` and `Phase B.1`, exit code 0.

- [ ] **Step 2: ADR table loads**

Run: `uv run python -c "from app.deepdive.compose import build_adr_table; print(build_adr_table()['NOVO-B.CO'])"`
Confirm: `{'adr_ticker': 'NVO', 'cik': '0000353278', 'form_type': '20-F'}`

- [ ] **Step 3: Create the vault Watchlist junction (cmd.exe, manual)**

The Obsidian vault currently has a real `Watchlist` directory; it must become a junction into the repo `output/Watchlist/` (mirrors the existing `Universum` junction). In cmd.exe, **after backing up any existing vault Watchlist content**:

```
rmdir "D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\Watchlist"
mklink /J "D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\Watchlist" "D:\programme\fisherscreen\output\Watchlist"
dir "D:\programme\stef-vault\Wissen\Finanzen\FisherScreen\Watchlist"
```

> `rmdir` without `/s` only succeeds if the directory is empty — if it is not, Stephan must decide what to do with existing content first. This step requires Stephan's explicit confirmation before running (destructive on the vault side). Do not run it unattended.

Confirm: the vault `Watchlist` path resolves to the repo `output/Watchlist/` (junction visible in `dir` output as `<JUNCTION>`).

- [ ] **Step 4: Report**

Summarize to Stephan: CLI smoke result, ADR-table load result, junction status. B.0 done when all three are green.

---

## Self-Review

**1. Spec coverage** (Master §4 B.0 row + B.1-Spec E3/E4):
- CLI-Package-Skeleton (`app/deepdive/`, argparse + `add_subparsers`, `[project.scripts]`) → Task 5 ✓
- `output/Watchlist/`-Junction + GitHub-Push-Pfad → Task 6 (repo dir) + Task 8 Step 3 (vault junction) + Task 4 (`build_github_client` reused) ✓
- Statische ADR-Tabelle (Seed NOVO) → Task 2 (data) + Task 3 (loader) ✓
- `DeepDiveError` → Task 1 ✓
- `compose.py`-Analog → Task 4 ✓
- Acceptance (`--help` runs; ADR loads + format test green; junction visible) → Task 8 ✓
- E3 args `TICKER/--model/--no-cache`, exit-code shape → Task 5 ✓ (full pipeline exit-codes 1/2/3 are B.1; B.0 skeleton returns 0 by design)
No gaps.

**2. Placeholder scan:** No TBD/TODO; every code step contains complete code; every command has expected output. The `deepdive` command intentionally prints a skeleton notice — that is the B.0 deliverable, not a placeholder (the pipeline is explicitly B.1 scope per the goal).

**3. Type consistency:** `load_adr_table(path: Path | None = None) -> dict[str, dict[str, str]]` defined in Task 3, consumed unchanged in Task 4 (`build_adr_table`) and Tasks 3/8 tests. `build_parser()` / `main(argv)` signatures defined in Task 5, used consistently in its tests. `DeepDiveError` defined in Task 1, imported in Tasks 3. `data/adr_table.json` schema written in Task 2 matches the validator in Task 3 and the assertions in Tasks 3/4/8. Consistent.

---

*Ende des Plans.*
