# FisherScreen Repo Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Initialize the fisherscreen git repo at `D:\programme\fisherscreen`, connect it to GitHub (`stnmllr/fisherscreen`, private), install uv, scaffold the project structure, and implement the three foundational modules (config, error hierarchy, logging) with full test coverage.

**Architecture:** uv manages packages and the venv. Python 3.12 is pinned via `.python-version`. Three modules form the foundation every later phase builds on: `config.py` (env vars), `errors.py` (exception hierarchy), `logging_config.py` (Cloud Logging-compatible JSON). Service Protocols define the DI contract without implementing anything — concrete implementations come in Phase 1.

**Tech Stack:** Python 3.12, uv, pytest, pytest-cov, pydantic-settings, yfinance, git, gh CLI

> **Branch exception (this plan only):** Bootstrap commits go directly to `main` — explicit approval granted for this setup run (2026-05-10). From Phase 1 onwards the CLAUDE.md branch convention applies strictly: all work via `feature/*`, `bugfix/*` etc.

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `CLAUDE.md` | exists | Project conventions — do not modify |
| `.gitignore` | create | Exclude venv, .env, __pycache__, credentials |
| `.env.example` | create | Env var documentation with empty placeholders |
| `.python-version` | create (uv) | Python 3.12 pin |
| `pyproject.toml` | create | uv project, dependencies, pytest + coverage config |
| `app/__init__.py` | create | Package marker |
| `app/config.py` | create | FISHERSCREEN_* settings via pydantic-settings |
| `app/errors.py` | create | FisherScreenError hierarchy |
| `app/logging_config.py` | create | CloudJsonFormatter + configure_logging |
| `app/services/__init__.py` | create | Package marker |
| `app/services/yfinance_client.py` | create | Protocol stub |
| `app/services/edgar_client.py` | create | Protocol stub |
| `app/services/gemini_client.py` | create | Protocol stub |
| `app/services/apify_client.py` | create | Protocol stub |
| `app/services/marketaux_client.py` | create | Protocol stub |
| `app/services/firestore_client.py` | create | Protocol stub |
| `tests/__init__.py` | create | Package marker |
| `tests/conftest.py` | create | Shared mock fixtures |
| `tests/test_config.py` | create | Config tests |
| `tests/test_errors.py` | create | Error hierarchy tests |
| `tests/test_logging_config.py` | create | Logging formatter tests |
| `Universum/.gitkeep` | create | Obsidian output dir placeholder |
| `Portfolio/.gitkeep` | create | Obsidian output dir placeholder |
| `Watchlist/.gitkeep` | create | Obsidian output dir placeholder |
| `config/.gitkeep` | create | portfolio_normalized.json will live here |

---

### Task 1: Install uv

**Files:** none (system-level install)

- [ ] **Step 1: Install uv via winget**

  ```
  winget install astral-sh.uv
  ```

  Expected: installs successfully. Close and reopen cmd after install for PATH to update.

- [ ] **Step 2: Verify**

  ```
  uv --version
  ```

  Expected: `uv 0.x.x (...)` — any version ≥ 0.4.0.

---

### Task 2: Create GitHub repo

**Files:** none (remote only)

- [ ] **Step 1: Verify gh CLI is authenticated**

  ```
  gh auth status
  ```

  Expected: `Logged in to github.com as stnmllr`. If not: run `gh auth login` and follow prompts. If gh not installed: https://cli.github.com

- [ ] **Step 2: Create private repo on GitHub**

  Run from `D:\programme\fisherscreen`:

  ```
  gh repo create stnmllr/fisherscreen --private --description "Phil Fisher stock screener — 15 principles on public data"
  ```

  Expected: `✓ Created repository stnmllr/fisherscreen on GitHub`

---

### Task 3: Initialize git and connect remote

**Files:** `.git/` (created by git init)

- [ ] **Step 1: Initialize git**

  From `D:\programme\fisherscreen`:

  ```
  git init
  git branch -M main
  ```

  Expected: `Initialized empty Git repository in D:/programme/fisherscreen/.git/`

- [ ] **Step 2: Connect to remote**

  ```
  git remote add origin https://github.com/stnmllr/fisherscreen.git
  ```

- [ ] **Step 3: Verify remote**

  ```
  git remote -v
  ```

  Expected:
  ```
  origin  https://github.com/stnmllr/fisherscreen.git (fetch)
  origin  https://github.com/stnmllr/fisherscreen.git (push)
  ```

---

### Task 4: pyproject.toml, Python version, dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `.python-version` (via uv)

- [ ] **Step 1: Initialize uv project**

  From `D:\programme\fisherscreen`:

  ```
  uv init --no-readme --python 3.12
  ```

  This writes a minimal `pyproject.toml` and `.python-version`. Delete the auto-generated stub if present:

  ```
  del hello.py
  ```

- [ ] **Step 2: Replace pyproject.toml with project config**

  Overwrite `pyproject.toml` with:

  ```toml
  [project]
  name = "fisherscreen"
  version = "0.1.0"
  description = "Phil Fisher stock screener applying 15 principles to public data"
  requires-python = ">=3.12"
  dependencies = [
      "pydantic-settings>=2.4.0",
      "yfinance>=0.2.50",
      "httpx>=0.27.0",
  ]

  [project.optional-dependencies]
  dev = [
      "pytest>=8.0.0",
      "pytest-cov>=5.0.0",
      "pytest-asyncio>=0.23.0",
  ]

  [tool.pytest.ini_options]
  addopts = "--cov=app --cov-report=term-missing --cov-fail-under=90"
  markers = [
      "integration: integration tests requiring real APIs",
  ]

  [tool.coverage.run]
  omit = [
      "app/services/*",
  ]

  [tool.coverage.report]
  exclude_lines = [
      "\\.\\.\\.",
  ]

  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"
  ```

  Note: `app/services/*` is excluded from coverage — these are Protocol stubs (interface definitions only). Add them back as implementations land in Phase 1.

- [ ] **Step 3: Pin Python 3.12**

  ```
  uv python pin 3.12
  ```

  Verify `.python-version` contains `3.12`.

- [ ] **Step 4: Install all dependencies**

  ```
  uv sync --extra dev
  ```

  Expected: resolves deps, creates `uv.lock`, installs into `.venv`. First run may take 30–60 seconds.

- [ ] **Step 5: Verify Python version in venv**

  ```
  uv run python --version
  ```

  Expected: `Python 3.12.x`

---

### Task 5: Directory structure, .gitignore, .env.example

**Files:**
- Create: all directories and marker files
- Create: `.gitignore`
- Create: `.env.example`

- [ ] **Step 1: Create directories**

  From `D:\programme\fisherscreen`:

  ```
  mkdir app
  mkdir app\services
  mkdir tests
  mkdir Universum
  mkdir Portfolio
  mkdir Watchlist
  mkdir config
  ```

- [ ] **Step 2: Create package markers and gitkeep placeholders**

  ```
  type nul > app\__init__.py
  type nul > app\services\__init__.py
  type nul > tests\__init__.py
  type nul > Universum\.gitkeep
  type nul > Portfolio\.gitkeep
  type nul > Watchlist\.gitkeep
  type nul > config\.gitkeep
  ```

- [ ] **Step 3: Write .gitignore**

  Create `.gitignore`:

  ```gitignore
  # Python
  __pycache__/
  *.py[cod]
  *.egg-info/
  .pytest_cache/
  .coverage
  htmlcov/
  dist/

  # uv / venv
  .venv/

  # Environment — never commit secrets
  .env
  *.env.local

  # GCP service account keys only (not all JSON)
  *-credentials.json
  service-account-*.json
  *-sa-key.json

  # Editor
  .vscode/settings.json
  *.swp
  *.swo

  # OS
  Thumbs.db
  desktop.ini
  ```

- [ ] **Step 4: Write .env.example**

  Create `.env.example`:

  ```dotenv
  # FisherScreen — environment variable template
  # Copy to .env for local development.
  # On Cloud Run: configure via Secret Manager, not .env.

  FISHERSCREEN_GCP_PROJECT_ID=your-gcp-project-id
  FISHERSCREEN_EDGAR_USER_AGENT=FisherScreen/1.0 your@email.com
  FISHERSCREEN_GEMINI_TOKEN_CAP=500000
  FISHERSCREEN_APIFY_API_KEY=your-apify-key
  FISHERSCREEN_GITHUB_TOKEN=your-github-token
  ```

---

### Task 6: Config module (TDD)

**Files:**
- Create: `tests/test_config.py`
- Create: `app/config.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_config.py`:

  ```python
  from app.config import FisherScreenSettings


  def test_reads_gcp_project_from_env(monkeypatch):
      monkeypatch.setenv("FISHERSCREEN_GCP_PROJECT_ID", "test-project-123")
      settings = FisherScreenSettings(_env_file=None)
      assert settings.gcp_project_id == "test-project-123"


  def test_gcp_project_defaults_to_empty():
      settings = FisherScreenSettings(_env_file=None)
      assert settings.gcp_project_id == ""


  def test_reads_edgar_user_agent(monkeypatch):
      monkeypatch.setenv("FISHERSCREEN_EDGAR_USER_AGENT", "TestAgent/1.0 test@test.com")
      settings = FisherScreenSettings(_env_file=None)
      assert settings.edgar_user_agent == "TestAgent/1.0 test@test.com"


  def test_reads_gemini_token_cap(monkeypatch):
      monkeypatch.setenv("FISHERSCREEN_GEMINI_TOKEN_CAP", "250000")
      settings = FisherScreenSettings(_env_file=None)
      assert settings.gemini_token_cap == 250000


  def test_gemini_token_cap_default():
      settings = FisherScreenSettings(_env_file=None)
      assert settings.gemini_token_cap == 500_000


  def test_reads_apify_api_key(monkeypatch):
      monkeypatch.setenv("FISHERSCREEN_APIFY_API_KEY", "apify-key-abc")
      settings = FisherScreenSettings(_env_file=None)
      assert settings.apify_api_key == "apify-key-abc"
  ```

- [ ] **Step 2: Run — verify FAIL**

  ```
  uv run pytest tests/test_config.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.config'`

- [ ] **Step 3: Implement app/config.py**

  Create `app/config.py`:

  ```python
  from pydantic_settings import BaseSettings


  class FisherScreenSettings(BaseSettings):
      gcp_project_id: str = ""
      edgar_user_agent: str = ""  # must be set via FISHERSCREEN_EDGAR_USER_AGENT; validated in edgar_client
      gemini_token_cap: int = 500_000
      apify_api_key: str = ""
      github_token: str = ""

      model_config = {
          "env_prefix": "FISHERSCREEN_",
          "env_file": ".env",
          "env_file_encoding": "utf-8",
      }


  settings = FisherScreenSettings()
  ```

- [ ] **Step 4: Run — verify PASS**

  ```
  uv run pytest tests/test_config.py -v
  ```

  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```
  git add app/config.py tests/test_config.py pyproject.toml .python-version uv.lock
  git commit -m "Add config module with FISHERSCREEN_ env prefix"
  ```

  > **⏸ PAUSE — review before Task 7.**

---

### Task 7: Error hierarchy (TDD)

**Files:**
- Create: `tests/test_errors.py`
- Create: `app/errors.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_errors.py`:

  ```python
  import pytest
  from app.errors import DataSourceError, FilterConfigError, FisherScreenError, GeminiError


  def test_all_subclass_base():
      assert issubclass(DataSourceError, FisherScreenError)
      assert issubclass(GeminiError, FisherScreenError)
      assert issubclass(FilterConfigError, FisherScreenError)


  def test_base_subclasses_exception():
      assert issubclass(FisherScreenError, Exception)


  def test_datasource_catchable_as_base():
      with pytest.raises(FisherScreenError):
          raise DataSourceError("yfinance timeout on AAPL")


  def test_gemini_catchable_as_base():
      with pytest.raises(FisherScreenError):
          raise GeminiError("quota exceeded: 500000 tokens")


  def test_filter_config_catchable_as_base():
      with pytest.raises(FisherScreenError):
          raise FilterConfigError("gross_margin_threshold must be > 0")


  def test_errors_carry_message():
      err = DataSourceError("connection refused")
      assert str(err) == "connection refused"
  ```

- [ ] **Step 2: Run — verify FAIL**

  ```
  uv run pytest tests/test_errors.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.errors'`

- [ ] **Step 3: Implement app/errors.py**

  Create `app/errors.py`:

  ```python
  class FisherScreenError(Exception):
      """Base exception for all FisherScreen errors."""


  class DataSourceError(FisherScreenError):
      """Raised when an external data source fails: yfinance, EDGAR, Apify, Marketaux."""


  class GeminiError(FisherScreenError):
      """Raised on Gemini API call failure (Flash Lite or Pro)."""


  class FilterConfigError(FisherScreenError):
      """Raised when negative filter configuration is invalid or contradictory."""
  ```

- [ ] **Step 4: Run — verify PASS**

  ```
  uv run pytest tests/test_errors.py -v
  ```

  Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

  ```
  git add app/errors.py tests/test_errors.py
  git commit -m "Add FisherScreen error hierarchy"
  ```

  > **⏸ PAUSE — review before Task 8.**

---

### Task 8: Logging config (TDD)

**Files:**
- Create: `tests/test_logging_config.py`
- Create: `app/logging_config.py`

- [ ] **Step 1: Write failing tests**

  Create `tests/test_logging_config.py`:

  ```python
  import json
  import logging

  from app.logging_config import CloudJsonFormatter, configure_logging


  def _make_record(msg: str, level: int = logging.INFO) -> logging.LogRecord:
      return logging.LogRecord(
          name="test",
          level=level,
          pathname="",
          lineno=0,
          msg=msg,
          args=(),
          exc_info=None,
      )


  def test_produces_valid_json():
      formatter = CloudJsonFormatter()
      output = formatter.format(_make_record("hello world"))
      parsed = json.loads(output)
      assert parsed["message"] == "hello world"


  def test_uses_severity_not_level():
      formatter = CloudJsonFormatter()
      parsed = json.loads(formatter.format(_make_record("msg", logging.WARNING)))
      assert parsed["severity"] == "WARNING"
      assert "level" not in parsed


  def test_includes_module_and_funcname():
      formatter = CloudJsonFormatter()
      parsed = json.loads(formatter.format(_make_record("msg")))
      assert "module" in parsed
      assert "funcName" in parsed


  def test_includes_trace_when_set():
      formatter = CloudJsonFormatter()
      record = _make_record("traced")
      record.trace = "projects/myproject/traces/abc123"
      parsed = json.loads(formatter.format(record))
      assert parsed["logging.googleapis.com/trace"] == "projects/myproject/traces/abc123"


  def test_omits_trace_when_absent():
      formatter = CloudJsonFormatter()
      parsed = json.loads(formatter.format(_make_record("no trace")))
      assert "logging.googleapis.com/trace" not in parsed


  def test_configure_logging_does_not_raise():
      configure_logging()
  ```

- [ ] **Step 2: Run — verify FAIL**

  ```
  uv run pytest tests/test_logging_config.py -v
  ```

  Expected: `ERROR` — `ModuleNotFoundError: No module named 'app.logging_config'`

- [ ] **Step 3: Implement app/logging_config.py**

  Create `app/logging_config.py`:

  ```python
  import json
  import logging


  class CloudJsonFormatter(logging.Formatter):
      def format(self, record: logging.LogRecord) -> str:
          log_entry = {
              "severity": record.levelname,
              "message": record.getMessage(),
              "module": record.module,
              "funcName": record.funcName,
          }
          trace = getattr(record, "trace", None)
          if trace:
              log_entry["logging.googleapis.com/trace"] = trace
          return json.dumps(log_entry)


  def configure_logging(level: int = logging.INFO) -> None:
      handler = logging.StreamHandler()
      handler.setFormatter(CloudJsonFormatter())
      logging.basicConfig(level=level, handlers=[handler], force=True)
  ```

- [ ] **Step 4: Run — verify PASS**

  ```
  uv run pytest tests/test_logging_config.py -v
  ```

  Expected: 5 tests PASS.

- [ ] **Step 5: Run full suite — verify coverage threshold**

  ```
  uv run pytest
  ```

  Expected: all tests PASS, coverage ≥ 90% (services excluded by `[tool.coverage.run] omit`). If coverage fails, check what's missing with `--cov-report=term-missing` and add tests before committing.

- [ ] **Step 6: Commit**

  ```
  git add app/logging_config.py tests/test_logging_config.py
  git commit -m "Add CloudJsonFormatter with Cloud Logging trace correlation"
  ```

  > **⏸ PAUSE — review before Task 9.**

---

### Task 9: Service Protocol stubs

**Files:**
- Create: `app/services/yfinance_client.py`
- Create: `app/services/edgar_client.py`
- Create: `app/services/gemini_client.py`
- Create: `app/services/apify_client.py`
- Create: `app/services/marketaux_client.py`
- Create: `app/services/firestore_client.py`

These define the DI contract. No implementation, no tests yet — implementations and tests come in Phase 1. The `app/services/*` directory is excluded from coverage in `pyproject.toml`.

- [ ] **Step 1: Write app/services/yfinance_client.py**

  ```python
  from typing import Any, Protocol


  class YFinanceClient(Protocol):
      def get_ticker_info(self, ticker: str) -> dict[str, Any]: ...
      def get_historical(self, ticker: str, period: str) -> Any: ...
      def get_financials(self, ticker: str) -> dict[str, Any]: ...
  ```

- [ ] **Step 2: Write app/services/edgar_client.py**

  ```python
  from typing import Protocol


  class EdgarClient(Protocol):
      def has_going_concern(self, ticker: str) -> bool: ...
      def has_restatement(self, ticker: str, years: int = 3) -> bool: ...
      def has_active_enforcement(self, ticker: str) -> bool: ...
      def get_earnings_call_transcripts(self, ticker: str, quarters: int = 4) -> list[str]: ...
  ```

- [ ] **Step 3: Write app/services/gemini_client.py**

  ```python
  from typing import Protocol


  class GeminiClient(Protocol):
      def complete(self, prompt: str, model: str, max_tokens: int) -> str: ...
  ```

- [ ] **Step 4: Write app/services/apify_client.py**

  ```python
  from typing import Protocol


  class ApifyClient(Protocol):
      def get_glassdoor_reviews(self, company: str, limit: int = 100) -> list[dict]: ...
      def get_kununu_reviews(self, company: str, limit: int = 100) -> list[dict]: ...
  ```

- [ ] **Step 5: Write app/services/marketaux_client.py**

  ```python
  from typing import Protocol


  class MarketauxClient(Protocol):
      def get_news(self, ticker: str, days: int = 90) -> list[dict]: ...
  ```

- [ ] **Step 6: Write app/services/firestore_client.py**

  ```python
  from typing import Any, Protocol


  class FirestoreClient(Protocol):
      def get(self, collection: str, document_id: str) -> dict[str, Any] | None: ...
      def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None: ...
      def delete(self, collection: str, document_id: str) -> None: ...
  ```

- [ ] **Step 7: Write tests/test_service_stubs.py**

  This test only imports the six Protocol modules. It guards against silent typos in the stub files. It does NOT count toward coverage (services are omitted in `pyproject.toml`).

  Create `tests/test_service_stubs.py`:

  ```python
  def test_service_protocol_imports():
      from app.services.apify_client import ApifyClient
      from app.services.edgar_client import EdgarClient
      from app.services.firestore_client import FirestoreClient
      from app.services.gemini_client import GeminiClient
      from app.services.marketaux_client import MarketauxClient
      from app.services.yfinance_client import YFinanceClient

      assert all([
          ApifyClient, EdgarClient, FirestoreClient,
          GeminiClient, MarketauxClient, YFinanceClient,
      ])
  ```

  Run to verify it passes:

  ```
  uv run pytest tests/test_service_stubs.py -v
  ```

  Expected: 1 test PASS.

- [ ] **Step 8: Commit**

  ```
  git add app/services/ tests/test_service_stubs.py
  git commit -m "Add service Protocol stubs for dependency injection"
  ```

  > **⏸ PAUSE — review before Task 10.**

---

### Task 10: conftest.py and initial push

**Files:**
- Create: `tests/conftest.py`
- Push: `origin main`

- [ ] **Step 1: Write tests/conftest.py**

  ```python
  from unittest.mock import MagicMock

  import pytest


  @pytest.fixture
  def mock_yfinance():
      return MagicMock()


  @pytest.fixture
  def mock_edgar():
      return MagicMock()


  @pytest.fixture
  def mock_gemini():
      return MagicMock()


  @pytest.fixture
  def mock_firestore():
      return MagicMock()
  ```

- [ ] **Step 2: Run full suite one final time**

  ```
  uv run pytest -v
  ```

  Expected: 17 tests PASS, coverage ≥ 90%, exit code 0.

- [ ] **Step 3: Stage remaining files and review**

  ```
  git add .
  git status
  ```

  Verify before committing:
  - `.env` is **not** listed (covered by .gitignore)
  - `uv.lock` **is** listed
  - `CLAUDE.md`, `.gitignore`, `.env.example`, `Universum/.gitkeep` etc. **are** listed

- [ ] **Step 4: Final commit**

  ```
  git commit -m "Initial project scaffold: structure, config, errors, logging, service stubs"
  ```

- [ ] **Step 5: Push to GitHub**

  ```
  git push -u origin main
  ```

  Expected: `Branch 'main' set up to track remote branch 'main' from 'origin'.`

- [ ] **Step 6: Verify on GitHub**

  ```
  gh repo view stnmllr/fisherscreen --web
  ```

  Opens repo in browser. Check: CLAUDE.md visible, directory structure correct, repo private.
