"""Unit tests for the script-only helpers of the EDGAR history probe.

Die Extraktion selbst ist nach app/services/edgar_annual_series_client.py
gewandert; ihre Tests liegen in tests/services/. Hier bleibt, was nur das
Skript betrifft: Ticker-Basis, Report-Parser und der Schutz der
handgeschriebenen Empfehlung.
"""

from scripts.probe_edgar_history import (
    HAND_MARKER,
    is_us_ticker,
    parse_crosshits_tickers,
    parse_dropouts_scored,
    preserve_handwritten,
)

# --- ticker basis ----------------------------------------------------------


def test_us_ticker_detection_follows_the_dot_convention():
    assert is_us_ticker("NEM")
    assert is_us_ticker("BRK-B")  # US class shares use a hyphen
    assert not is_us_ticker("EDV.L")
    assert not is_us_ticker("ADYEN.AS")


def test_parse_dropouts_takes_only_the_scoring_stage():
    csv_text = (
        "ticker,stage,reason_code,severity_bucket,is_large_cap,sector_wide,"
        "market_cap_eur,gics_sector,detail\n"
        "AMS.VI,resolution,RESOLUTION_DEGRADED_DICT,REVIEW,False,False,,,\n"
        "AAL,crosshits,SCORE_BELOW_THRESHOLD,BENIGN,True,False,1.0,Industrials,\n"
        "A,crosshits,SCORE_BELOW_THRESHOLD,BENIGN,True,False,2.0,Healthcare,\n"
    )
    assert parse_dropouts_scored(csv_text) == ["AAL", "A"]


def test_parse_crosshits_reads_the_table_and_strips_flag_markers():
    md_text = (
        "# Universum 2026-09 — Crosshits\n"
        "\n"
        "| Stufe | rein | raus | uebrig |\n"
        "|---|---|---|---|\n"
        "| Universum | 1322 | 0 | 1322 |\n"
        "\n"
        "| # | Ticker | Name | Sektor | Crosshits | Dimensionen | O Score |\n"
        "|---|---|---|---|---|---|---|\n"
        "| 1 | EDV.L  | ENDEAVOUR MINING PLC | Basic Materials | 3 | growth | 4.67 |\n"
        "| 2 | FICO ~ | Fair Isaac Corporation | Technology | 3 | growth | 4.67 |\n"
        "| 3 | SNDK ⚠ | Sandisk Corporation | Technology | 3 | growth | 4.33 |\n"
    )
    assert parse_crosshits_tickers(md_text) == ["EDV.L", "FICO", "SNDK"]


# --- the report must not eat the assessment written under it ---------------


def test_a_rerun_keeps_everything_below_the_hand_marker():
    """The measurement is reproducible, the assessment written under it is not.
    A re-run that silently ate the recommendation would be a data loss."""
    existing = "# old measurement\n\n" + HAND_MARKER + "\n\n## Empfehlung\n\nBauen.\n"
    out = preserve_handwritten("# new measurement\n", existing)

    assert out.startswith("# new measurement\n")
    assert "## Empfehlung\n\nBauen.\n" in out
    assert "old measurement" not in out


def test_a_report_without_the_marker_is_replaced_wholesale():
    assert preserve_handwritten("# new\n", "# old\n") == "# new\n"
