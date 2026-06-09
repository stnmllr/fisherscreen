"""Regression guard for the 2026-06-09 prod outage.

An unanchored `output/` pattern in .gitignore matched `app/output/` too. With no
.gcloudignore present, `gcloud builds submit` derives its upload filter from
.gitignore and applies the pattern literally (without git's tracked-file
exemption), so `app/output/` was dropped from the build context. The Dockerfile's
`COPY app/ ./app/` then shipped an image WITHOUT the package, and the dry-run
endpoint crashed at runtime with `ModuleNotFoundError: No module named 'app.output'`.

Root-anchoring the generated-output patterns (`/output/`) restricts them to the
repo-root directory so they can never swallow a source package named `output/`.
"""

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GENERATED_OUTPUT_DIRS = {"output", "output-test"}


def test_generated_output_ignores_are_root_anchored() -> None:
    lines = (_REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    unanchored = [
        line
        for line in lines
        # gitignore: trailing whitespace is insignificant unless backslash-quoted.
        if (stripped := line.strip()).rstrip("/") in _GENERATED_OUTPUT_DIRS
        and not stripped.startswith("/")
    ]
    assert not unanchored, (
        "Generated-output .gitignore patterns must be root-anchored (e.g. `/output/`). "
        f"Unanchored pattern(s) also match app/output/ and break the Cloud Build "
        f"context (ModuleNotFoundError in prod): {unanchored}"
    )
