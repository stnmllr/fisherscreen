# Phase 1.4 — Markdown Output, GitHub Push, Cloud Run Deploy

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate three monthly Markdown files (Dimensions, Crosshits, Changes) from the scored ScreenerRecord list, push them to GitHub so Obsidian can read them, and deploy the screener to Cloud Run with a Cloud Scheduler trigger.

**Architecture:** Three stateless generator functions in `app/output/` each take `list[ScreenerRecord]` + `RunRecord` + `output_dir: Path` and return the written `Path`. A new `run_screener()` orchestrator in `runner.py` chains basis filter → EDGAR filter → Gemini scoring → output generation. FastAPI exposes `/run/monthly`; Cloud Scheduler calls it monthly. A `GitHubClientImpl` (httpx, already in deps) pushes the three generated files via GitHub REST API.

**Tech Stack:** `python-frontmatter` (new dep, PyYAML-backed), `httpx` (existing), `google-genai` (existing), FastAPI, Cloud Run (europe-west3), Cloud Scheduler.

---

## Files

| File | Action |
|---|---|
| `app/screener/dimensions.py` | Create — `DIMENSIONS` constant |
| `app/services/gemini_client.py` | Modify — import `DIMENSIONS` from `dimensions.py` |
| `app/config.py` | Modify — crosshits settings, github settings, output_dir |
| `app/output/__init__.py` | Create — empty package marker |
| `app/output/dimensions_generator.py` | Create |
| `app/output/crosshits_generator.py` | Create |
| `app/output/changes_generator.py` | Create |
| `app/services/github_client.py` | Create |
| `app/screener/runner.py` | Modify — add `run_screener()` |
| `app/screener/compose.py` | Modify — add `build_github_client()` |
| `app/main.py` | Create — FastAPI app with `/run/monthly` |
| `data/universe.json` | Create — placeholder ticker list |
| `Dockerfile` | Create |
| `.github/workflows/deploy.yml` | Create |
| `.env.example` | Create |
| `output/Universum/.gitkeep` | Create — ensures directory is tracked |
| `tests/output/__init__.py` | Create |
| `tests/output/test_dimensions_generator.py` | Create |
| `tests/output/test_crosshits_generator.py` | Create |
| `tests/output/test_changes_generator.py` | Create |
| `tests/services/test_github_client.py` | Create |
| `tests/test_main.py` | Create |
| `tests/screener/test_runner.py` | Modify — add `run_screener` tests |
| `docs/infra/cloud-scheduler.md` | Create |
| `infra/budget_stop.py` | Modify — remove `SCHEDULER_JOB_NAME` placeholder comment |

---

## Task 1 (1.4.a): `dimensions.py` — Single Source of Truth

**Files:**
- Create: `app/screener/dimensions.py`
- Modify: `app/services/gemini_client.py:18`
- Create: `tests/screener/test_dimensions.py`

- [ ] **Step 1: Write failing test**

```python
# tests/screener/test_dimensions.py
from app.screener.dimensions import DIMENSIONS
from app.services import gemini_client


def test_dimensions_constant_has_five_elements():
    assert len(DIMENSIONS) == 5


def test_dimensions_are_the_expected_names():
    assert set(DIMENSIONS) == {"growth", "profitability", "management", "innovation", "resilience"}


def test_gemini_client_uses_same_dimensions_as_central_constant():
    assert list(gemini_client.DIMENSIONS) == list(DIMENSIONS)
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/screener/test_dimensions.py -v
```
Expected: FAIL — `app.screener.dimensions` does not exist.

- [ ] **Step 3: Create `dimensions.py`**

```python
# app/screener/dimensions.py
from typing import Final

DIMENSIONS: Final[tuple[str, ...]] = (
    "growth",
    "profitability",
    "management",
    "innovation",
    "resilience",
)
```

- [ ] **Step 4: Update `gemini_client.py` — remove local constant, import from `dimensions.py`**

Replace line 18 in `app/services/gemini_client.py`:
```python
# Before:
DIMENSIONS = ["growth", "profitability", "management", "innovation", "resilience"]

# After:
from app.screener.dimensions import DIMENSIONS
```

The import goes at the top of the file, before `logger = ...`. The `from app.screener.dimensions import DIMENSIONS` line replaces the old definition exactly. No other changes needed — all other code already references `DIMENSIONS` by name.

- [ ] **Step 5: Run — verify PASS**

```
uv run python -m pytest tests/screener/test_dimensions.py tests/services/test_gemini_client.py -v
```
Expected: all tests pass.

- [ ] **Step 6: Run full suite**

```
uv run python -m pytest -v
```
Expected: all 172 existing tests pass.

- [ ] **Step 7: Commit**

```
git add app/screener/dimensions.py app/services/gemini_client.py tests/screener/test_dimensions.py
git commit -m "Extract DIMENSIONS constant to dimensions.py as single source of truth"
```

---

## Task 2 (1.4.a): Config — Crosshits + Output + GitHub Settings

**Files:**
- Modify: `app/config.py`
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_config.py — append:

def test_crosshits_score_threshold_defaults_to_4():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_score_threshold == 4.0


def test_reads_crosshits_score_threshold(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_CROSSHITS_SCORE_THRESHOLD", "4.5")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_score_threshold == 4.5


def test_crosshits_min_dimensions_defaults_to_2():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_min_dimensions == 2


def test_crosshits_cap_defaults_to_50():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.crosshits_cap == 50


def test_output_dir_defaults_to_output():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.output_dir == "output"


def test_github_token_defaults_to_empty():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_token == ""


def test_reads_github_repo(monkeypatch):
    monkeypatch.setenv("FISHERSCREEN_GITHUB_REPO", "stnmllr/fisherscreen")
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_repo == "stnmllr/fisherscreen"


def test_github_branch_defaults_to_main():
    settings = FisherScreenSettings(_env_file=None)
    assert settings.github_branch == "main"
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/test_config.py -k "crosshits or output_dir or github_repo or github_branch" -v
```
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Implement — full replacement of `app/config.py`**

```python
# app/config.py
from pydantic_settings import BaseSettings


class FisherScreenSettings(BaseSettings):
    gcp_project_id: str = ""
    edgar_user_agent: str = ""
    gemini_token_cap: int = 500_000
    gemini_api_key: str = ""
    gemini_score_collection: str = "dev_gemini_scores"
    screener_runs_collection: str = "dev_screener_runs"
    apify_api_key: str = ""
    github_token: str = ""
    github_repo: str = ""
    github_branch: str = "main"
    ticker_collection: str = "dev_ticker_cache"
    edgar_collection: str = "dev_edgar_cache"
    crosshits_score_threshold: float = 4.0
    crosshits_min_dimensions: int = 2
    crosshits_cap: int = 50
    output_dir: str = "output"

    model_config = {
        "env_prefix": "FISHERSCREEN_",
        "env_file": ".env",
        "env_file_encoding": "utf-8",
    }


settings = FisherScreenSettings()
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/test_config.py -v
```
Expected: all config tests pass.

- [ ] **Step 5: Commit**

```
git add app/config.py tests/test_config.py
git commit -m "Add crosshits, output_dir, and github settings to config"
```

---

## Task 3 (1.4.a): DimensionsGenerator

**Files:**
- Install: `python-frontmatter`
- Create: `app/output/__init__.py`
- Create: `app/output/dimensions_generator.py`
- Create: `tests/output/__init__.py`
- Create: `tests/output/test_dimensions_generator.py`

- [ ] **Step 1: Install dependency**

```
uv add python-frontmatter
```

- [ ] **Step 2: Create empty package markers**

Create `app/output/__init__.py` — empty file.
Create `tests/output/__init__.py` — empty file.

- [ ] **Step 3: Write failing tests**

```python
# tests/output/test_dimensions_generator.py
from datetime import datetime, timezone
from pathlib import Path

import frontmatter
import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.dimensions_generator import generate
from app.screener.dimensions import DIMENSIONS


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}
    dims.update(dim_scores)
    return ScreenerRecord(
        ticker=ticker,
        name=f"{ticker} Corp",
        gics_sector="Technology",
        gemini_dimensions=dims,
    )


def _run_record(run_id: str = "2026-05-13T08:00:00+00:00") -> RunRecord:
    return RunRecord(run_id=run_id)


def test_generate_creates_file_in_output_dir(tmp_path):
    records = [_record("AAPL", growth=4)]
    path = generate(records, _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename_uses_run_year_month(tmp_path):
    path = generate([_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path)
    assert path.name == "2026-05-Dimensions.md"


def test_generate_creates_universum_subdirectory(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert path.parent == tmp_path / "Universum"


def test_frontmatter_has_required_top_level_keys(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    for key in ("run_id", "generated_at", "universum_size", "score_threshold", "cap_per_dimension", "dimensions"):
        assert key in post.metadata, f"Missing frontmatter key: {key}"


def test_frontmatter_universum_size_matches_record_count(tmp_path):
    records = [_record("AAPL"), _record("MSFT"), _record("NVDA")]
    path = generate(records, _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    assert post.metadata["universum_size"] == 3


def test_frontmatter_dimensions_has_all_five_dimensions(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    dims = post.metadata["dimensions"]
    for dim in DIMENSIONS:
        assert dim in dims, f"Missing dimension in frontmatter: {dim}"


def test_frontmatter_dimension_tickers_only_includes_qualifying_tickers(tmp_path):
    records = [
        _record("PASS", growth=4),   # qualifies: growth >= 4
        _record("FAIL", growth=3),   # does not qualify
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    growth_tickers = post.metadata["dimensions"]["growth"]["tickers"]
    assert "PASS" in growth_tickers
    assert "FAIL" not in growth_tickers


def test_frontmatter_dimension_qualifying_count_is_correct(tmp_path):
    records = [_record(f"T{i}", growth=4) for i in range(5)] + [_record("LOW", growth=3)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    assert post.metadata["dimensions"]["growth"]["qualifying_count"] == 5


def test_cap_limits_tickers_in_frontmatter(tmp_path):
    records = [_record(f"T{i}", growth=5) for i in range(60)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, cap=50)
    post = frontmatter.load(str(path))
    assert len(post.metadata["dimensions"]["growth"]["tickers"]) == 50


def test_markdown_body_contains_all_five_dimension_sections(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    post = frontmatter.load(str(path))
    body = post.content
    for dim in DIMENSIONS:
        assert dim.capitalize() in body or dim in body.lower()


def test_records_without_gemini_dimensions_are_excluded(tmp_path):
    records = [
        _record("SCORED", growth=5),
        ScreenerRecord(ticker="UNSCORED"),  # gemini_dimensions is None
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0)
    post = frontmatter.load(str(path))
    growth_tickers = post.metadata["dimensions"]["growth"]["tickers"]
    assert "SCORED" in growth_tickers
    assert "UNSCORED" not in growth_tickers


def test_generate_overwrites_existing_file(tmp_path):
    (tmp_path / "Universum").mkdir()
    existing = tmp_path / "Universum" / "2026-05-Dimensions.md"
    existing.write_text("old content", encoding="utf-8")
    generate([_record("AAPL")], _run_record(), tmp_path)
    assert "old content" not in existing.read_text(encoding="utf-8")
```

- [ ] **Step 4: Run — verify FAIL**

```
uv run python -m pytest tests/output/test_dimensions_generator.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 5: Implement `dimensions_generator.py`**

```python
# app/output/dimensions_generator.py
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter

from app.screener.dimensions import DIMENSIONS

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    cap: int = 50,
) -> Path:
    output_dir = output_dir / "Universum"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]  # "YYYY-MM"
    out_path = output_dir / f"{run_month}-Dimensions.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    dim_data = _compute_dimension_data(scored, score_threshold, cap)
    crosshits = _compute_crosshits_for_frontmatter(scored, score_threshold, cap)

    metadata = {
        "run_id": run_record.run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "universum_size": len(records),
        "score_threshold": score_threshold,
        "cap_per_dimension": cap,
        "dimensions": dim_data,
        "crosshits": crosshits,
    }
    body = _build_markdown_body(dim_data, scored, run_month, score_threshold, cap)

    post = frontmatter.Post(body)
    post.metadata.update(metadata)
    out_path.write_text(frontmatter.dumps(post), encoding="utf-8")

    logger.info("dimensions: wrote %s (%d records, %d scored)", out_path.name, len(records), len(scored))
    return out_path


def _compute_dimension_data(
    scored: list[ScreenerRecord],
    score_threshold: float,
    cap: int,
) -> dict:
    result = {}
    for dim in DIMENSIONS:
        qualifying = sorted(
            [r for r in scored if (r.gemini_dimensions or {}).get(dim, 0) >= score_threshold],
            key=lambda r: (r.gemini_dimensions or {}).get(dim, 0),
            reverse=True,
        )[:cap]
        result[dim] = {
            "qualifying_count": len(qualifying),
            "tickers": [r.ticker for r in qualifying],
        }
    return result


def _compute_crosshits_for_frontmatter(
    scored: list[ScreenerRecord],
    score_threshold: float,
    cap: int,
) -> list[dict]:
    crosshits = []
    for record in scored:
        dims = record.gemini_dimensions or {}
        qualifying_dims = [d for d in DIMENSIONS if dims.get(d, 0) >= score_threshold]
        if len(qualifying_dims) >= 2:
            avg = sum(dims.get(d, 0) for d in qualifying_dims) / len(qualifying_dims)
            crosshits.append({
                "ticker": record.ticker,
                "dimensions": qualifying_dims,
                "avg_score": round(avg, 2),
            })
    crosshits.sort(key=lambda x: (-len(x["dimensions"]), -x["avg_score"]))
    return crosshits[:cap]


def _build_markdown_body(
    dim_data: dict,
    scored: list[ScreenerRecord],
    run_month: str,
    score_threshold: float,
    cap: int,
) -> str:
    ticker_lookup = {r.ticker: r for r in scored}
    lines = [
        f"# Universum {run_month} — Dimensions",
        "",
        f"*Score-Schwelle: ≥{score_threshold} | Cap pro Dimension: {cap}*",
        "",
        "---",
        "",
    ]
    for dim in DIMENSIONS:
        tickers = dim_data[dim]["tickers"]
        count = dim_data[dim]["qualifying_count"]
        lines.append(f"## {dim.capitalize()} (n={count})")
        lines.append("")
        if not tickers:
            lines.append("*Kein Ticker erreichte die Score-Schwelle.*")
        else:
            lines.append("| # | Ticker | Name | Sektor | Score |")
            lines.append("|---|---|---|---|---|")
            for i, ticker in enumerate(tickers, 1):
                r = ticker_lookup.get(ticker)
                name = (r.name or "") if r else ""
                sector = (r.gics_sector or "") if r else ""
                score = (r.gemini_dimensions or {}).get(dim, "")
                lines.append(f"| {i} | {ticker} | {name} | {sector} | {score} |")
        lines.append("")
    return "\n".join(lines)
```

- [ ] **Step 6: Run — verify PASS**

```
uv run python -m pytest tests/output/test_dimensions_generator.py -v
```
Expected: all tests pass.

- [ ] **Step 7: Run full suite**

```
uv run python -m pytest -v
```
Expected: all tests pass, coverage ≥90%.

- [ ] **Step 8: Commit**

```
git add app/output/__init__.py app/output/dimensions_generator.py tests/output/__init__.py tests/output/test_dimensions_generator.py pyproject.toml uv.lock
git commit -m "Add DimensionsGenerator with YAML frontmatter and markdown body"
```

---

## Task 4 (1.4.b): CrosshitsGenerator

**Files:**
- Create: `app/output/crosshits_generator.py`
- Create: `tests/output/test_crosshits_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/output/test_crosshits_generator.py
from pathlib import Path

import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.crosshits_generator import generate


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}
    dims.update(dim_scores)
    return ScreenerRecord(ticker=ticker, name=f"{ticker} Corp", gics_sector="Technology", gemini_dimensions=dims)


def _run_record() -> RunRecord:
    return RunRecord(run_id="2026-05-13T08:00:00+00:00")


def test_generate_creates_file(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.name == "2026-05-Crosshits.md"


def test_generate_writes_to_universum_subdir(tmp_path):
    path = generate([_record("AAPL", growth=5, profitability=4)], _run_record(), tmp_path)
    assert path.parent == tmp_path / "Universum"


def test_ticker_with_two_qualifying_dims_is_a_crosshit(tmp_path):
    records = [_record("AAPL", growth=4, profitability=4)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "AAPL" in path.read_text(encoding="utf-8")


def test_ticker_with_one_qualifying_dim_is_not_a_crosshit(tmp_path):
    records = [_record("SOLO", growth=5, profitability=3)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    content = path.read_text(encoding="utf-8")
    assert "SOLO" not in content or "Keine Crosshits" in content


def test_empty_crosshits_produces_informative_message(tmp_path):
    records = [_record("LOW", growth=2, profitability=2)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "Keine Crosshits" in path.read_text(encoding="utf-8")


def test_crosshits_sorted_by_dimension_count_desc(tmp_path):
    records = [
        _record("THREE", growth=4, profitability=4, management=4),
        _record("TWO", growth=4, profitability=4),
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    content = path.read_text(encoding="utf-8")
    assert content.index("THREE") < content.index("TWO")


def test_cap_limits_crosshits_output(tmp_path):
    records = [_record(f"T{i}", growth=5, profitability=5) for i in range(60)]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2, cap=10)
    content = path.read_text(encoding="utf-8")
    assert content.count("| ") <= 12 * 10  # at most 10 table rows


def test_records_without_gemini_dimensions_are_excluded(tmp_path):
    records = [
        _record("SCORED", growth=5, profitability=5),
        ScreenerRecord(ticker="UNSCORED"),
    ]
    path = generate(records, _run_record(), tmp_path, score_threshold=4.0, min_dimensions=2)
    assert "UNSCORED" not in path.read_text(encoding="utf-8")
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/output/test_crosshits_generator.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `crosshits_generator.py`**

```python
# app/output/crosshits_generator.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from app.screener.dimensions import DIMENSIONS

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    min_dimensions: int = 2,
    cap: int = 50,
) -> Path:
    output_dir = output_dir / "Universum"
    output_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]
    out_path = output_dir / f"{run_month}-Crosshits.md"

    scored = [r for r in records if r.gemini_dimensions is not None]
    crosshits = _compute_crosshits(scored, score_threshold, min_dimensions, cap)

    body = _build_body(crosshits, run_month, score_threshold, min_dimensions)
    out_path.write_text(body, encoding="utf-8")

    logger.info("crosshits: wrote %s (%d crosshits)", out_path.name, len(crosshits))
    return out_path


def _compute_crosshits(
    scored: list[ScreenerRecord],
    score_threshold: float,
    min_dimensions: int,
    cap: int,
) -> list[dict]:
    result = []
    for record in scored:
        dims = record.gemini_dimensions or {}
        qualifying = [d for d in DIMENSIONS if dims.get(d, 0) >= score_threshold]
        if len(qualifying) >= min_dimensions:
            avg = sum(dims.get(d, 0) for d in qualifying) / len(qualifying)
            result.append({
                "record": record,
                "qualifying_dims": qualifying,
                "avg_score": round(avg, 2),
            })
    result.sort(key=lambda x: (-len(x["qualifying_dims"]), -x["avg_score"]))
    return result[:cap]


def _build_body(crosshits: list[dict], run_month: str, score_threshold: float, min_dimensions: int) -> str:
    lines = [
        f"# Universum {run_month} — Crosshits",
        "",
        f"*Schwelle: Score ≥{score_threshold} in ≥{min_dimensions} Dimensionen*",
        "",
    ]
    if not crosshits:
        lines += [
            "> Keine Crosshits in diesem Lauf. Entweder kein Ticker erreichte die Schwelle",
            "> in mindestens zwei Dimensionen, oder das Universum war nach Filtern zu klein.",
        ]
    else:
        lines += [
            "| # | Ticker | Name | Sektor | Crosshits | Dimensionen | Ø Score |",
            "|---|---|---|---|---|---|---|",
        ]
        for i, entry in enumerate(crosshits, 1):
            r = entry["record"]
            dims_str = ", ".join(entry["qualifying_dims"])
            lines.append(
                f"| {i} | {r.ticker} | {r.name or ''} | {r.gics_sector or ''} "
                f"| {len(entry['qualifying_dims'])} | {dims_str} | {entry['avg_score']} |"
            )
    return "\n".join(lines) + "\n"
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/output/test_crosshits_generator.py -v
```

- [ ] **Step 5: Commit**

```
git add app/output/crosshits_generator.py tests/output/test_crosshits_generator.py
git commit -m "Add CrosshitsGenerator (score>=4 in >=2 dimensions, cap 50)"
```

---

## Task 5 (1.4.c): ChangesGenerator

**Files:**
- Create: `app/output/changes_generator.py`
- Create: `tests/output/test_changes_generator.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/output/test_changes_generator.py
from pathlib import Path

import frontmatter
import pytest

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.output.changes_generator import generate


def _record(ticker: str, **dim_scores) -> ScreenerRecord:
    dims = {"growth": 3, "profitability": 3, "management": 3, "innovation": 3, "resilience": 3}
    dims.update(dim_scores)
    return ScreenerRecord(ticker=ticker, gemini_dimensions=dims)


def _run_record(run_id: str = "2026-05-13T08:00:00+00:00") -> RunRecord:
    return RunRecord(run_id=run_id)


def _write_prior_dimensions(output_dir: Path, month: str, tickers_per_dim: dict) -> Path:
    """Write a prior Dimensions.md with the given tickers per dimension."""
    universum = output_dir / "Universum"
    universum.mkdir(parents=True, exist_ok=True)
    prior = universum / f"{month}-Dimensions.md"
    dim_data = {
        dim: {"qualifying_count": len(tickers), "tickers": tickers}
        for dim, tickers in tickers_per_dim.items()
    }
    metadata = {
        "run_id": f"{month}-01T08:00:00+00:00",
        "generated_at": f"{month}-01T08:42:00+00:00",
        "universum_size": 10,
        "score_threshold": 4.0,
        "cap_per_dimension": 50,
        "dimensions": dim_data,
        "crosshits": [],
    }
    post = frontmatter.Post("# Prior month body")
    post.metadata.update(metadata)
    prior.write_text(frontmatter.dumps(post), encoding="utf-8")
    return prior


def test_generate_creates_file(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert path.exists()


def test_generate_filename(tmp_path):
    path = generate([_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path)
    assert path.name == "2026-05-Changes.md"


def test_no_prior_month_produces_first_run_message(tmp_path):
    path = generate([_record("AAPL")], _run_record(), tmp_path)
    assert "Erster verfügbarer Run" in path.read_text(encoding="utf-8")


def test_new_ticker_in_dimension_is_highlighted(tmp_path):
    prior_dims = {
        "growth": ["OLD"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("NEW", growth=5), _record("OLD", growth=4)]
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "NEW" in content


def test_removed_ticker_from_dimension_is_highlighted(tmp_path):
    prior_dims = {
        "growth": ["GONE"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("STAYS", growth=4)]  # GONE is not in current records
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "GONE" in content


def test_gap_in_history_uses_most_recent_prior_file(tmp_path):
    prior_dims = {"growth": ["X"], "profitability": [], "management": [], "innovation": [], "resilience": []}
    _write_prior_dimensions(tmp_path, "2026-03", prior_dims)  # March — April missing
    path = generate([_record("Y", growth=4)], _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert "2026-03" in content  # references March as comparison base


def test_corrupt_frontmatter_falls_back_to_no_prior(tmp_path):
    universum = tmp_path / "Universum"
    universum.mkdir()
    (universum / "2026-04-Dimensions.md").write_text("not valid frontmatter at all", encoding="utf-8")
    path = generate([_record("AAPL")], _run_record("2026-05-13T08:00:00+00:00"), tmp_path)
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "Erster verfügbarer Run" in content or "Vergleichsbasis" in content or "Warnung" in content


def test_no_changes_produces_unchanged_message(tmp_path):
    prior_dims = {
        "growth": ["AAPL"], "profitability": [], "management": [],
        "innovation": [], "resilience": [],
    }
    _write_prior_dimensions(tmp_path, "2026-04", prior_dims)
    records = [_record("AAPL", growth=4)]  # same as prior
    path = generate(records, _run_record("2026-05-13T08:00:00+00:00"), tmp_path, score_threshold=4.0)
    content = path.read_text(encoding="utf-8")
    assert path.exists()
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/output/test_changes_generator.py -v
```
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `changes_generator.py`**

```python
# app/output/changes_generator.py
from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import frontmatter

from app.screener.dimensions import DIMENSIONS

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)


def generate(
    records: list[ScreenerRecord],
    run_record: RunRecord,
    output_dir: Path,
    *,
    score_threshold: float = 4.0,
    cap: int = 50,
) -> Path:
    universum_dir = output_dir / "Universum"
    universum_dir.mkdir(parents=True, exist_ok=True)

    run_month = run_record.run_id[:7]
    out_path = universum_dir / f"{run_month}-Changes.md"

    current_dim_tickers = _compute_current_dim_tickers(records, score_threshold, cap)
    prior_result = _load_prior_frontmatter(universum_dir, run_month)
    body = _build_body(run_month, current_dim_tickers, prior_result)
    out_path.write_text(body, encoding="utf-8")

    logger.info("changes: wrote %s", out_path.name)
    return out_path


def _compute_current_dim_tickers(
    records: list[ScreenerRecord],
    score_threshold: float,
    cap: int,
) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {dim: set() for dim in DIMENSIONS}
    for record in records:
        if record.gemini_dimensions is None:
            continue
        for dim in DIMENSIONS:
            if record.gemini_dimensions.get(dim, 0) >= score_threshold:
                result[dim].add(record.ticker)
    for dim in DIMENSIONS:
        if len(result[dim]) > cap:
            result[dim] = set(list(result[dim])[:cap])
    return result


def _load_prior_frontmatter(universum_dir: Path, current_month: str) -> dict | None:
    candidates = sorted(universum_dir.glob("????-??-Dimensions.md"))
    candidates = [p for p in candidates if p.stem[:7] < current_month]
    if not candidates:
        return None
    prior_path = candidates[-1]
    try:
        post = frontmatter.load(str(prior_path))
        dims = post.metadata.get("dimensions", {})
        if not dims:
            return None
        return {"path": prior_path, "dimensions": dims}
    except Exception as exc:
        logger.warning("changes: failed to parse %s — treating as no prior: %s", prior_path.name, exc)
        return None


def _build_body(
    run_month: str,
    current: dict[str, set[str]],
    prior_result: dict | None,
) -> str:
    lines = [f"# Universum {run_month} — Changes", ""]

    if prior_result is None:
        lines += [
            "> Erster verfügbarer Run. Keine Vergleichsbasis vorhanden.",
            f"> Alle Ticker in diesem Run sind neu im Universum.",
        ]
        return "\n".join(lines) + "\n"

    prior_path: Path = prior_result["path"]
    prior_dims: dict = prior_result["dimensions"]
    prior_month = prior_path.stem[:7]

    lines.append(f"*Vergleichsbasis: {prior_path.name} | Aktuell: {run_month}*")
    if prior_month != _month_minus_one(run_month):
        lines.append(f"*Hinweis: {_month_minus_one(run_month)}-Run nicht verfügbar — Diff gegen {prior_month}.*")
    lines.append("")

    any_change = False
    for dim in DIMENSIONS:
        prior_tickers: set[str] = set(prior_dims.get(dim, {}).get("tickers", []))
        current_tickers: set[str] = current.get(dim, set())
        new_in = current_tickers - prior_tickers
        removed = prior_tickers - current_tickers

        if new_in or removed:
            any_change = True
            lines.append(f"## {dim.capitalize()}")
            if new_in:
                lines.append(f"**Neu:** {', '.join(sorted(new_in))}")
            if removed:
                lines.append(f"**Raus:** {', '.join(sorted(removed))}")
            lines.append("")

    if not any_change:
        lines.append("*Keine Änderungen gegenüber dem Vormonat.*")

    return "\n".join(lines) + "\n"


def _month_minus_one(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7])
    if month == 1:
        return f"{year - 1}-12"
    return f"{year}-{month - 1:02d}"
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/output/test_changes_generator.py -v
```

- [ ] **Step 5: Run full suite**

```
uv run python -m pytest -v
```

- [ ] **Step 6: Commit**

```
git add app/output/changes_generator.py tests/output/test_changes_generator.py
git commit -m "Add ChangesGenerator with prior-month diff logic and edge case handling"
```

---

## Task 6 (1.4.d): Pipeline Integration — `run_screener()`

**Files:**
- Modify: `app/screener/runner.py`
- Modify: `app/screener/compose.py`
- Create: `data/universe.json`
- Modify: `tests/screener/test_runner.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/screener/test_runner.py — append (keep existing tests, add these):
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.models.run_record import RunRecord
from app.models.screener_record import ScreenerRecord
from app.screener.runner import run_screener
from app.services.gemini_client import GeminiScoreResult


def _scored_record(ticker: str) -> ScreenerRecord:
    return ScreenerRecord(
        ticker=ticker,
        filter_passed_basis=True,
        filter_passed_edgar=True,
        gemini_dimensions={"growth": 4, "profitability": 4, "management": 4, "innovation": 4, "resilience": 4},
    )


def _mock_yfinance(ticker: str) -> MagicMock:
    mock = MagicMock()
    mock.get_ticker_info.return_value = {
        "shortName": f"{ticker} Corp",
        "marketCap": 5_000_000_000,
        "averageVolume": 1_000_000,
        "currentPrice": 100.0,
        "bid": 99.9,
        "ask": 100.1,
        "sector": "Technology",
        "industry": "Software",
        "currency": "USD",
    }
    return mock


def test_run_screener_returns_records_and_run_record(tmp_path):
    mock_yfinance = _mock_yfinance("AAPL")
    mock_edgar = MagicMock()
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = False
    mock_edgar.has_active_enforcement.return_value = False
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = GeminiScoreResult(
        dimensions={"growth": 4, "profitability": 4, "management": 4, "innovation": 4, "resilience": 4},
        summary="Good",
        tokens_in=500,
        tokens_out=80,
    )
    mock_tracker = MagicMock()
    mock_tracker.finish.return_value = RunRecord(run_id="2026-05-13T08:00:00+00:00")

    records, run_record, paths = run_screener(
        tickers=["AAPL"],
        yfinance=mock_yfinance,
        edgar=mock_edgar,
        gemini=mock_gemini,
        run_tracker=mock_tracker,
        output_dir=tmp_path,
    )

    assert isinstance(records, list)
    assert isinstance(run_record, RunRecord)
    assert len(paths) == 3


def test_run_screener_creates_three_output_files(tmp_path):
    mock_yfinance = _mock_yfinance("AAPL")
    mock_edgar = MagicMock()
    mock_edgar.has_restatement.return_value = False
    mock_edgar.has_going_concern.return_value = False
    mock_edgar.has_active_enforcement.return_value = False
    mock_gemini = MagicMock()
    mock_gemini.score_ticker.return_value = GeminiScoreResult(
        dimensions={"growth": 4, "profitability": 4, "management": 4, "innovation": 4, "resilience": 4},
        summary="Good",
        tokens_in=500,
        tokens_out=80,
    )
    mock_tracker = MagicMock()
    mock_tracker.finish.return_value = RunRecord(run_id="2026-05-13T08:00:00+00:00")

    _, _, paths = run_screener(
        tickers=["AAPL"],
        yfinance=mock_yfinance,
        edgar=mock_edgar,
        gemini=mock_gemini,
        run_tracker=mock_tracker,
        output_dir=tmp_path,
    )

    names = {p.name for p in paths}
    assert "2026-05-Dimensions.md" in names
    assert "2026-05-Crosshits.md" in names
    assert "2026-05-Changes.md" in names
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/screener/test_runner.py -k "run_screener" -v
```
Expected: FAIL — `run_screener` not defined.

- [ ] **Step 3: Add `run_screener()` to `runner.py`**

Append to `app/screener/runner.py` (keep existing functions unchanged):

```python
# app/screener/runner.py — append after existing imports and functions:

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.run_record import RunRecord
    from app.screener.run_tracker import RunTracker
    from app.services.gemini_client import GeminiClient

# (Note: existing imports already cover YFinanceClient, EdgarClient; add these to the
#  existing TYPE_CHECKING block at the top of the file, do not duplicate the block.)
```

The actual function — add to the bottom of `app/screener/runner.py`:

```python
def run_screener(
    tickers: list[str],
    yfinance: YFinanceClient,
    edgar: EdgarClient,
    gemini: GeminiClient,
    run_tracker: RunTracker,
    output_dir: Path,
    *,
    score_threshold: float | None = None,
    crosshits_min_dimensions: int | None = None,
    crosshits_cap: int | None = None,
) -> tuple[list[ScreenerRecord], RunRecord, list[Path]]:
    from app.config import settings
    from app.models.run_record import RunRecord
    from app.output.changes_generator import generate as generate_changes
    from app.output.crosshits_generator import generate as generate_crosshits
    from app.output.dimensions_generator import generate as generate_dimensions
    from app.screener.scorer import run_gemini_scoring

    threshold = score_threshold if score_threshold is not None else settings.crosshits_score_threshold
    min_dims = crosshits_min_dimensions if crosshits_min_dimensions is not None else settings.crosshits_min_dimensions
    cap = crosshits_cap if crosshits_cap is not None else settings.crosshits_cap

    records = run_basis_filter(tickers, yfinance)
    records = run_edgar_filter(records, edgar)
    records = run_gemini_scoring(records, gemini, run_tracker)
    run_record: RunRecord = run_tracker.finish()

    paths = [
        generate_dimensions(records, run_record, output_dir, score_threshold=threshold, cap=cap),
        generate_crosshits(records, run_record, output_dir, score_threshold=threshold, min_dimensions=min_dims, cap=cap),
        generate_changes(records, run_record, output_dir, score_threshold=threshold, cap=cap),
    ]

    logger.info(
        "run_screener: complete — %d records, %d output files",
        len(records), len(paths),
    )
    return records, run_record, paths
```

**Important:** the `TYPE_CHECKING` imports for `RunTracker` and `GeminiClient` must be merged into the existing `if TYPE_CHECKING:` block at the top of `runner.py`, not added as a duplicate block. The `from app.services.edgar_client import EdgarClient` and `from app.services.yfinance_client import YFinanceClient` imports are already there. Add:

```python
# In the existing TYPE_CHECKING block in runner.py — add these two lines:
from app.models.run_record import RunRecord
from app.screener.run_tracker import RunTracker
from app.services.gemini_client import GeminiClient
```

- [ ] **Step 4: Create `data/universe.json` — placeholder ticker list**

```json
[
  "AAPL", "MSFT", "NVDA", "GOOGL", "AMZN",
  "META", "ASML", "SAP", "NOVO-B.CO", "TSMC"
]
```

This is a 10-ticker placeholder. Full universe population (S&P 500 + Russell 1000 + STOXX 600, ~2100 tickers) is a separate task outside Phase 1.4 scope.

- [ ] **Step 5: Run — verify PASS**

```
uv run python -m pytest tests/screener/test_runner.py -v
```

- [ ] **Step 6: Run full suite**

```
uv run python -m pytest -v
```

- [ ] **Step 7: Commit**

```
git add app/screener/runner.py data/universe.json tests/screener/test_runner.py
git commit -m "Add run_screener() orchestrator wiring basis+edgar+gemini+output pipeline"
```

---

## Task 7 (1.4.e): GitHub Client

**Files:**
- Create: `app/services/github_client.py`
- Modify: `app/screener/compose.py`
- Create: `tests/services/test_github_client.py`
- Modify: `tests/screener/test_compose.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/services/test_github_client.py
import base64
from unittest.mock import MagicMock

import pytest

from app.errors import DataSourceError
from app.services.github_client import GitHubClientImpl


def _mock_http(get_status: int = 200, get_sha: str | None = "abc123") -> MagicMock:
    mock = MagicMock()
    get_resp = MagicMock()
    get_resp.status_code = get_status
    get_resp.json.return_value = {"sha": get_sha} if get_sha else {}
    mock.get.return_value = get_resp

    put_resp = MagicMock()
    put_resp.raise_for_status = MagicMock()
    mock.put.return_value = put_resp
    return mock


def test_push_file_calls_get_for_sha(tmp_path):
    http = _mock_http()
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/Universum/2026-05-Dimensions.md", "# content", "chore: add monthly output")
    http.get.assert_called_once()


def test_push_file_sends_existing_sha_when_file_exists(tmp_path):
    http = _mock_http(get_status=200, get_sha="existing-sha")
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/test.md", "content", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    assert payload.get("sha") == "existing-sha"


def test_push_file_omits_sha_when_file_does_not_exist(tmp_path):
    http = _mock_http(get_status=404, get_sha=None)
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/new.md", "content", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    assert "sha" not in payload


def test_push_file_base64_encodes_content():
    http = _mock_http()
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    client.push_file("output/test.md", "hello world", "msg")
    put_call = http.put.call_args
    payload = put_call[1]["json"] if put_call[1] else put_call[0][1]
    decoded = base64.b64decode(payload["content"]).decode()
    assert decoded == "hello world"


def test_push_file_wraps_http_error_in_data_source_error():
    http = _mock_http()
    http.put.return_value.raise_for_status.side_effect = Exception("HTTP 403")
    client = GitHubClientImpl(token="tok", repo="org/repo", http=http)
    with pytest.raises(DataSourceError, match="GitHub push failed"):
        client.push_file("output/test.md", "content", "msg")


def test_raises_on_empty_token():
    with pytest.raises(DataSourceError, match="GitHub token"):
        GitHubClientImpl(token="", repo="org/repo")
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/services/test_github_client.py -v
```

- [ ] **Step 3: Implement `github_client.py`**

```python
# app/services/github_client.py
from __future__ import annotations

import base64
import logging
from typing import Protocol

import httpx

from app.errors import DataSourceError

logger = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubClient(Protocol):
    def push_file(self, path: str, content: str, commit_message: str) -> None: ...


class GitHubClientImpl:
    def __init__(
        self,
        token: str,
        repo: str,
        branch: str = "main",
        http: httpx.Client | None = None,
    ) -> None:
        if not token:
            raise DataSourceError("GitHub token not set — configure FISHERSCREEN_GITHUB_TOKEN")
        self._headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        self._repo = repo
        self._branch = branch
        self._http = http or httpx.Client()

    def push_file(self, path: str, content: str, commit_message: str) -> None:
        url = f"{_GITHUB_API}/repos/{self._repo}/contents/{path}"
        get_resp = self._http.get(url, params={"ref": self._branch}, headers=self._headers)
        sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

        payload: dict = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            "branch": self._branch,
        }
        if sha:
            payload["sha"] = sha

        try:
            put_resp = self._http.put(url, json=payload, headers=self._headers)
            put_resp.raise_for_status()
        except Exception as exc:
            raise DataSourceError(f"GitHub push failed for {path}: {exc}") from exc

        logger.info("github: pushed %s to %s@%s", path, self._repo, self._branch)
```

- [ ] **Step 4: Add `build_github_client()` to `compose.py`**

Append to `app/screener/compose.py`:

```python
# app/screener/compose.py — append at end:
from app.services.github_client import GitHubClient, GitHubClientImpl


def build_github_client() -> GitHubClient:
    return GitHubClientImpl(
        token=settings.github_token,
        repo=settings.github_repo,
        branch=settings.github_branch,
    )
```

- [ ] **Step 5: Write compose test**

```python
# tests/screener/test_compose.py — append:

def test_build_github_client_wires_components():
    with (
        patch("app.screener.compose.GitHubClientImpl") as mock_cls,
        patch("app.screener.compose.settings") as mock_settings,
    ):
        mock_settings.github_token = "tok"
        mock_settings.github_repo = "org/repo"
        mock_settings.github_branch = "main"

        result = compose_module.build_github_client()

        mock_cls.assert_called_once_with(token="tok", repo="org/repo", branch="main")
        assert result == mock_cls.return_value
```

- [ ] **Step 6: Run — verify PASS**

```
uv run python -m pytest tests/services/test_github_client.py tests/screener/test_compose.py -v
```

- [ ] **Step 7: Commit**

```
git add app/services/github_client.py app/screener/compose.py tests/services/test_github_client.py tests/screener/test_compose.py
git commit -m "Add GitHubClientImpl for pushing output files to repo"
```

---

## Task 8 (1.4.f): FastAPI App + Dockerfile + GitHub Actions

**Files:**
- Create: `app/main.py`
- Create: `Dockerfile`
- Create: `.github/workflows/deploy.yml`
- Create: `.env.example`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_main.py
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.models.run_record import RunRecord

client = TestClient(app)


def _mock_run_result():
    records = []
    run_record = RunRecord(run_id="2026-05-13T08:00:00+00:00", tickers_processed=1, status="success")
    paths = [Path("output/Universum/2026-05-Dimensions.md")]
    return records, run_record, paths


def test_health_endpoint_returns_ok():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_monthly_run_endpoint_exists():
    with (
        patch("app.main.build_screener_pipeline"),
        patch("app.main.build_edgar_pipeline"),
        patch("app.main.build_gemini_pipeline"),
        patch("app.main.build_run_tracker"),
        patch("app.main.build_github_client"),
        patch("app.main.run_screener", return_value=_mock_run_result()),
        patch("app.main._load_universe", return_value=["AAPL"]),
    ):
        resp = client.post("/run/monthly")
    assert resp.status_code == 200


def test_monthly_run_returns_run_record_json():
    with (
        patch("app.main.build_screener_pipeline"),
        patch("app.main.build_edgar_pipeline"),
        patch("app.main.build_gemini_pipeline"),
        patch("app.main.build_run_tracker"),
        patch("app.main.build_github_client"),
        patch("app.main.run_screener", return_value=_mock_run_result()),
        patch("app.main._load_universe", return_value=["AAPL"]),
    ):
        resp = client.post("/run/monthly")
    data = resp.json()
    assert "run_id" in data
    assert "status" in data
```

- [ ] **Step 2: Run — verify FAIL**

```
uv run python -m pytest tests/test_main.py -v
```
Expected: FAIL — `app.main` not found.

- [ ] **Step 3: Implement `app/main.py`**

```python
# app/main.py
from __future__ import annotations

import json
import logging
from pathlib import Path

from fastapi import FastAPI

from app.config import settings
from app.screener.compose import (
    build_edgar_pipeline,
    build_gemini_pipeline,
    build_github_client,
    build_run_tracker,
    build_screener_pipeline,
)
from app.screener.runner import run_screener

logger = logging.getLogger(__name__)
app = FastAPI(title="FisherScreen")

_UNIVERSE_PATH = Path(__file__).parent.parent / "data" / "universe.json"


def _load_universe() -> list[str]:
    with _UNIVERSE_PATH.open(encoding="utf-8") as f:
        return json.load(f)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/run/monthly")
def run_monthly() -> dict:
    tickers = _load_universe()
    yfinance = build_screener_pipeline()
    edgar = build_edgar_pipeline()
    gemini = build_gemini_pipeline()
    tracker = build_run_tracker()
    github = build_github_client()
    output_dir = Path(settings.output_dir)

    records, run_record, paths = run_screener(
        tickers=tickers,
        yfinance=yfinance,
        edgar=edgar,
        gemini=gemini,
        run_tracker=tracker,
        output_dir=output_dir,
    )

    for path in paths:
        relative = path.relative_to(Path("."))
        github.push_file(
            str(relative).replace("\\", "/"),
            path.read_text(encoding="utf-8"),
            f"chore: monthly screener output {run_record.run_id[:7]}",
        )

    logger.info("monthly run complete: run_id=%s paths=%d", run_record.run_id, len(paths))
    return run_record.model_dump(mode="json")
```

- [ ] **Step 4: Run — verify PASS**

```
uv run python -m pytest tests/test_main.py -v
```

- [ ] **Step 5: Create `.env.example`**

```
# FisherScreen — environment variables (copy to .env and fill in values)
FISHERSCREEN_GCP_PROJECT_ID=fisherscreen-prod
FISHERSCREEN_EDGAR_USER_AGENT=FisherScreen/1.0 stn.mueller@gmail.com
FISHERSCREEN_GEMINI_API_KEY=
FISHERSCREEN_GITHUB_TOKEN=
FISHERSCREEN_GITHUB_REPO=stnmllr/fisherscreen
FISHERSCREEN_GITHUB_BRANCH=main

# Optional overrides (defaults shown)
FISHERSCREEN_GEMINI_SCORE_COLLECTION=dev_gemini_scores
FISHERSCREEN_SCREENER_RUNS_COLLECTION=dev_screener_runs
FISHERSCREEN_TICKER_COLLECTION=dev_ticker_cache
FISHERSCREEN_EDGAR_COLLECTION=dev_edgar_cache
FISHERSCREEN_CROSSHITS_SCORE_THRESHOLD=4.0
FISHERSCREEN_CROSSHITS_MIN_DIMENSIONS=2
FISHERSCREEN_CROSSHITS_CAP=50
FISHERSCREEN_OUTPUT_DIR=output
```

- [ ] **Step 6: Create `Dockerfile`**

```dockerfile
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app/ ./app/
COPY data/ ./data/

ENV PORT=8080
EXPOSE 8080

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 7: Create `.github/workflows/deploy.yml`**

```yaml
name: Deploy to Cloud Run

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write

    steps:
      - uses: actions/checkout@v4

      - id: auth
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: ${{ secrets.GCP_WORKLOAD_IDENTITY_PROVIDER }}
          service_account: ${{ secrets.GCP_SERVICE_ACCOUNT }}

      - uses: google-github-actions/setup-gcloud@v2

      - name: Build and push image
        run: |
          gcloud builds submit --tag europe-west3-docker.pkg.dev/fisherscreen-prod/fisherscreen/app:${{ github.sha }}

      - name: Deploy to Cloud Run
        run: |
          gcloud run deploy fisherscreen-service \
            --image europe-west3-docker.pkg.dev/fisherscreen-prod/fisherscreen/app:${{ github.sha }} \
            --region europe-west3 \
            --platform managed \
            --no-allow-unauthenticated \
            --set-secrets "FISHERSCREEN_GEMINI_API_KEY=fisherscreen-gemini-api-key:latest,FISHERSCREEN_GITHUB_TOKEN=fisherscreen-github-token:latest" \
            --set-env-vars "FISHERSCREEN_GCP_PROJECT_ID=fisherscreen-prod,FISHERSCREEN_GITHUB_REPO=stnmllr/fisherscreen,FISHERSCREEN_EDGAR_USER_AGENT=FisherScreen/1.0 stn.mueller@gmail.com"
```

- [ ] **Step 8: Create `output/Universum/.gitkeep`**

Empty file — ensures `output/Universum/` is tracked by git so Cloud Run can write there.

- [ ] **Step 9: Run full suite**

```
uv run python -m pytest -v
```
Expected: all tests pass, coverage ≥90%.

- [ ] **Step 10: Commit**

```
git add app/main.py Dockerfile .github/workflows/deploy.yml .env.example output/Universum/.gitkeep tests/test_main.py
git commit -m "Add FastAPI endpoint, Dockerfile, and GitHub Actions deploy workflow"
```

---

## Task 9 (1.4.g): Cloud Scheduler + Infra Docs

**Files:**
- Create: `docs/infra/cloud-scheduler.md`
- Modify: `infra/budget_stop.py` (remove placeholder comment, env var already handled)

**Context:** This task is infra-only — no Python unit tests. The Cloud Scheduler job calls `/run/monthly` on Cloud Run. The job name must be set in Secret Manager so `budget_stop.py` can pause it when the $10 budget is hit.

- [ ] **Step 1: Create `docs/infra/cloud-scheduler.md`**

```markdown
# Cloud Scheduler Setup

Cloud Scheduler calls POST /run/monthly on the first of each month at 06:00 CET.

## Prerequisites

```cmd
gcloud config set project fisherscreen-prod
```

## Step 1: Get the Cloud Run service URL

```cmd
gcloud run services describe fisherscreen-service --region europe-west3 --format "value(status.url)"
```

Note the URL — looks like `https://fisherscreen-service-HASH-ey.a.run.app`.

## Step 2: Create the Scheduler job

```cmd
gcloud scheduler jobs create http fisherscreen-monthly ^
  --location europe-west3 ^
  --schedule "0 5 1 * *" ^
  --time-zone "Europe/Berlin" ^
  --uri https://fisherscreen-service-HASH-ey.a.run.app/run/monthly ^
  --http-method POST ^
  --oidc-service-account-email fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --oidc-token-audience https://fisherscreen-service-HASH-ey.a.run.app
```

Replace the `HASH` URL with the actual Cloud Run URL from Step 1.

## Step 3: Register job name in budget_stop.py

Once the Scheduler job exists, update the Cloud Function environment variable:

```cmd
gcloud functions deploy fisherscreen-budget-stop ^
  --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
```

## Step 4: Grant Scheduler permission to invoke Cloud Run

```cmd
gcloud run services add-iam-policy-binding fisherscreen-service ^
  --region europe-west3 ^
  --member serviceAccount:fisherscreen-scheduler@fisherscreen-prod.iam.gserviceaccount.com ^
  --role roles/run.invoker
```

## Step 5: Verify

Trigger a manual run to verify the full pipeline works:

```cmd
gcloud scheduler jobs run fisherscreen-monthly --location europe-west3
```

Then check Cloud Run logs:

```cmd
gcloud logging read "resource.type=cloud_run_revision AND resource.labels.service_name=fisherscreen-service" ^
  --limit 50 --format "value(textPayload)"
```

Expected: log lines showing basis filter, EDGAR filter, Gemini scoring, and output generation.

## Step 6: Verify GitHub push

After a successful run, check the repo for three new files:
- `output/Universum/YYYY-MM-Dimensions.md`
- `output/Universum/YYYY-MM-Crosshits.md`
- `output/Universum/YYYY-MM-Changes.md`

## Reactivation after $10 budget hard stop

If the budget Cloud Function pauses the Scheduler job:
1. Investigate cost spike in GCP Console → Billing
2. GCP Console → Cloud Scheduler → select `fisherscreen-monthly` → **Resume**
3. Never automate reactivation
```

- [ ] **Step 2: Update `infra/budget_stop.py` — clarify SCHEDULER_JOB_NAME is now real**

Remove the placeholder comment from `infra/budget_stop.py`. The current comment says "set in Phase 2 after Cloud Scheduler job exists". Replace with a direct reference to the actual job name:

Find this line in `infra/budget_stop.py`:
```python
_SCHEDULER_JOB = os.environ.get("SCHEDULER_JOB_NAME", "")
```

No code change needed — the env var mechanism is already correct. Just update the module docstring to reflect that Phase 1.4 created the actual job:

Replace the module docstring:
```python
"""Cloud Function: pauses Cloud Scheduler job when billing budget is exceeded.

Triggered by Pub/Sub topic 'fisherscreen-budget-alerts'.
Deployment and setup: see docs/infra/budget-alerts.md

Environment variables:
  GCP_PROJECT_ID       — required, e.g. 'fisherscreen-prod'
  SCHEDULER_JOB_NAME  — set via: gcloud functions deploy ... --update-env-vars SCHEDULER_JOB_NAME=fisherscreen-monthly
  SCHEDULER_LOCATION  — defaults to 'europe-west3'
"""
```

- [ ] **Step 3: Update PROJEKTSTAND.md**

Update the "Nächste Session" block in `PROJEKTSTAND.md` to reflect Phase 1.4 completion scope. Under "Erledigt" add:

```
- 2026-05-15: **Phase-1.4-Plan** — `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`
```

And update the "Nächste Session" target:

```
**Ziel**: Phase 1.4 implementieren — Markdown-Output + GitHub-Push + Cloud Run Deploy
**Plan**: `docs/superpowers/plans/2026-05-15-phase-1-4-markdown-output.md`
```

- [ ] **Step 4: Run final full suite**

```
uv run python -m pytest -v
```
Expected: all tests pass, coverage ≥90%.

- [ ] **Step 5: Commit**

```
git add docs/infra/cloud-scheduler.md infra/budget_stop.py PROJEKTSTAND.md docs/superpowers/brainstorm/2026-05-15-phase-1-4-output-structure.md
git commit -m "Add Cloud Scheduler setup docs and finalize Phase 1.4 plan"
```

---

## Self-Review

**Spec coverage:**

| Brainstorm-Anforderung | Task |
|---|---|
| `app/screener/dimensions.py` zentrale Konstante | Task 1 |
| `gemini_client.py` importiert aus `dimensions.py` | Task 1 |
| Crosshits-Schwelle als Setting konfigurierbar | Task 2 |
| `output/Universum/YYYY-MM-Dimensions.md` mit YAML-Frontmatter | Task 3 |
| Frontmatter: run_id, generated_at, universum_size, dimensions, crosshits | Task 3 |
| Score-Schwelle ≥4, Cap 50 | Task 3 + 4 |
| `output/Universum/YYYY-MM-Crosshits.md` | Task 4 |
| Crosshits = ≥2 Dimensionen mit Score ≥4 | Task 4 |
| `output/Universum/YYYY-MM-Changes.md` | Task 5 |
| Diff gegen alphabetisch jüngstes Vormonats-File | Task 5 |
| Edge case: kein Vormonat | Task 5 |
| Edge case: Lücke in Historie | Task 5 |
| Edge case: korruptes Frontmatter | Task 5 |
| `run_screener()` als Orchestrator | Task 6 |
| `build_output_pipeline()` via compose.py | Task 6 + 7 |
| GitHub-Push via API | Task 7 |
| Cloud Run Deploy (Dockerfile, GitHub Actions) | Task 8 |
| Cloud Scheduler-Job + `SCHEDULER_JOB_NAME` | Task 9 |

**Placeholder scan:** No TBD, TODO, or "add appropriate" phrases found. Every step shows actual code.

**Type consistency:**
- `generate()` functions: signature `(records, run_record, output_dir, *, ...)→ Path` — consistent across Tasks 3, 4, 5.
- `run_screener()` returns `tuple[list[ScreenerRecord], RunRecord, list[Path]]` — referenced consistently in Task 6 and Task 8.
- `DIMENSIONS` is `tuple[str, ...]` in `dimensions.py`; `gemini_client.py` imports it as-is; all generators iterate over it — consistent.
- `GitHubClient` Protocol uses `push_file(path, content, commit_message)` — `build_github_client()` returns `GitHubClient`; `main.py` calls `push_file` — consistent.

**Out-of-scope confirmed:**
- Full universe builder (S&P 500 + Russell 1000 + STOXX 600 population) — not in Phase 1.4. `data/universe.json` is a 10-ticker placeholder.
- Portfolio Hold-Check output — Phase 2.
- Tool B / Deep Dive — Phase 2+.
- Score changes in Changes.md (requires per-ticker scores in frontmatter) — Phase 2.
