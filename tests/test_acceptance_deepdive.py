"""Unit tests for the consolidated pre-flight prerequisite check in the
Tool B B.1 acceptance script. Pure logic only — no network calls.
"""
from __future__ import annotations

from unittest.mock import patch

from google.auth.exceptions import DefaultCredentialsError

from scripts.acceptance_deepdive import check_prerequisites, main


def _all_set():
    """Context where every prerequisite is satisfied."""
    return patch.multiple(
        "scripts.acceptance_deepdive.settings",
        edgar_user_agent="FisherScreen test@example.com",
        gemini_api_key="key-123",
        gcp_project_id="fisherscreen-prod",
    )


def test_all_prerequisites_satisfied_returns_empty():
    with _all_set(), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        return_value=(object(), "fisherscreen-prod"),
    ):
        assert check_prerequisites() == []


def test_missing_edgar_user_agent():
    with patch.multiple(
        "scripts.acceptance_deepdive.settings",
        edgar_user_agent="",
        gemini_api_key="key-123",
        gcp_project_id="fisherscreen-prod",
    ), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        return_value=(object(), "p"),
    ):
        msgs = check_prerequisites()
    assert any("FISHERSCREEN_EDGAR_USER_AGENT not set" in m for m in msgs)
    assert len(msgs) == 1


def test_missing_gemini_api_key():
    with patch.multiple(
        "scripts.acceptance_deepdive.settings",
        edgar_user_agent="UA",
        gemini_api_key="",
        gcp_project_id="fisherscreen-prod",
    ), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        return_value=(object(), "p"),
    ):
        msgs = check_prerequisites()
    assert any("FISHERSCREEN_GEMINI_API_KEY not set" in m for m in msgs)
    assert len(msgs) == 1


def test_missing_gcp_project_id():
    with patch.multiple(
        "scripts.acceptance_deepdive.settings",
        edgar_user_agent="UA",
        gemini_api_key="key-123",
        gcp_project_id="",
    ), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        return_value=(object(), "p"),
    ):
        msgs = check_prerequisites()
    assert any("FISHERSCREEN_GCP_PROJECT_ID not set" in m for m in msgs)
    assert len(msgs) == 1


def test_adc_not_configured():
    with _all_set(), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        side_effect=DefaultCredentialsError("x"),
    ):
        msgs = check_prerequisites()
    assert any("GCP ADC not configured" in m for m in msgs)
    assert len(msgs) == 1


def test_all_missing_reports_all():
    with patch.multiple(
        "scripts.acceptance_deepdive.settings",
        edgar_user_agent="",
        gemini_api_key="",
        gcp_project_id="",
    ), patch(
        "scripts.acceptance_deepdive._google_auth_default",
        side_effect=DefaultCredentialsError("x"),
    ):
        msgs = check_prerequisites()
    assert len(msgs) == 4


def test_main_returns_2_and_prints_header_when_missing(capsys):
    with patch(
        "scripts.acceptance_deepdive.check_prerequisites",
        return_value=["X missing"],
    ), patch("scripts.acceptance_deepdive.run_deep_dive") as run_dd, patch(
        "scripts.acceptance_deepdive.build_synthesizer"
    ) as build_syn:
        rc = main()
    out = capsys.readouterr().out
    assert rc == 2
    assert "PRE-FLIGHT FAILED" in out
    assert "X missing" in out
    assert "Fix (cmd.exe):" in out
    run_dd.assert_not_called()
    build_syn.assert_not_called()
