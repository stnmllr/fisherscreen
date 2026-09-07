"""Unit tests for the EDGAR companyfacts history probe.

The probe's whole value rests on one decision: a fact's ``fy``/``fp`` names the
FILING that reported it, not the period the value covers. Keying by ``fy`` would
collapse a 10-K's comparative years into one. These tests pin the period-keyed
behaviour, because that is the difference between "EDGAR gives us three years"
and "EDGAR gives us ten".
"""

from datetime import date

from scripts.probe_edgar_history import (
    HAND_MARKER,
    ConceptCoverage,
    available_tags,
    contiguous_run,
    extract_concept,
    fiscal_label,
    is_us_ticker,
    parse_crosshits_tickers,
    parse_dropouts_scored,
    preserve_handwritten,
    taxonomies,
)


def _duration(start, end, val, *, fy, filed, form="10-K", fp="FY"):
    return {
        "start": start,
        "end": end,
        "val": val,
        "accn": f"acc-{filed}-{start}",
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def _instant(end, val, *, fy, filed, form="10-K", fp="FY"):
    return {
        "end": end,
        "val": val,
        "accn": f"acc-{filed}-{end}",
        "fy": fy,
        "fp": fp,
        "form": form,
        "filed": filed,
    }


def _facts(taxonomy, concept, entries, unit="USD"):
    return {
        "cik": 1234,
        "entityName": "Test Corp",
        "facts": {taxonomy: {concept: {"label": concept, "units": {unit: entries}}}},
    }


# --- the core deviation: comparatives are separate years -------------------


def test_comparatives_from_one_filing_are_three_years_not_one():
    """A single FY2025 10-K carries FY2023 and FY2024 as comparatives. All three
    entries say fy=2025, fp=FY. Period keying must see three years; fy keying
    sees one."""
    entries = [
        _duration("2023-01-01", "2023-12-31", 100.0, fy=2025, filed="2026-02-01"),
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2025, filed="2026-02-01"),
        _duration("2025-01-01", "2025-12-31", 120.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == (2023, 2024, 2025)
    assert cov.contiguous == 3
    assert cov.values == (100.0, 110.0, 120.0)
    assert cov.naive_fy_count == 1  # what the fy-keyed reading would have claimed


def test_ten_years_assemble_from_four_overlapping_filings():
    entries = []
    for filing_year in (2019, 2022, 2025, 2026):
        for offset in (2, 1, 0):
            year = filing_year - offset
            entries.append(
                _duration(
                    f"{year}-01-01",
                    f"{year}-12-31",
                    float(year),
                    fy=filing_year,
                    filed=f"{filing_year + 1}-02-15",
                )
            )
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == tuple(range(2017, 2027))
    assert cov.contiguous == 10
    assert cov.naive_fy_count == 4


# --- restatements ----------------------------------------------------------


def test_restatement_keeps_latest_filed_and_is_counted():
    entries = [
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2024, filed="2025-02-01"),
        _duration("2024-01-01", "2024-12-31", 105.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.values == (105.0,)  # the later filing wins
    assert cov.restatements == 1


def test_identical_value_refiled_is_not_a_restatement():
    entries = [
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2024, filed="2025-02-01"),
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.restatements == 0


# --- what does NOT count ---------------------------------------------------


def test_quarterly_durations_are_ignored():
    entries = [
        _duration(
            "2025-01-01",
            "2025-03-31",
            30.0,
            fy=2025,
            filed="2025-05-01",
            form="10-Q",
            fp="Q1",
        ),
        _duration("2025-01-01", "2025-12-31", 120.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == (2025,)


def test_forms_other_than_10k_are_ignored():
    entries = [
        _duration(
            "2024-01-01", "2024-12-31", 110.0, fy=2024, filed="2025-02-01", form="20-F"
        ),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == ()
    assert cov.concept is None


def test_amended_10k_counts():
    entries = [
        _duration(
            "2024-01-01",
            "2024-12-31",
            110.0,
            fy=2024,
            filed="2025-06-01",
            form="10-K/A",
        ),
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == (2024,)


# --- contiguity ------------------------------------------------------------


def test_gap_breaks_the_run_and_the_run_ends_at_the_newest_year():
    years = [2016, 2017, 2020, 2021, 2022]
    entries = [
        _duration(f"{y}-01-01", f"{y}-12-31", float(y), fy=y, filed=f"{y + 1}-02-01")
        for y in years
    ]
    cov = extract_concept(_facts("us-gaap", "Revenues", entries), ["Revenues"])

    assert cov.years == (2016, 2017, 2020, 2021, 2022)
    assert cov.contiguous == 3


def test_contiguous_run_tolerates_a_52_53_week_fiscal_year():
    ends = [date(2023, 1, 1), date(2023, 12, 31), date(2024, 12, 29)]
    assert contiguous_run(ends) == 3


def test_contiguous_run_of_nothing_is_zero():
    assert contiguous_run([]) == 0


# --- concept fallbacks -----------------------------------------------------


def test_fallback_concept_is_used_and_named():
    entries = [
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2024, filed="2025-02-01"),
    ]
    facts = _facts("us-gaap", "SalesRevenueNet", entries)
    cov = extract_concept(
        facts,
        [
            "Revenues",
            "RevenueFromContractWithCustomerExcludingAssessedTax",
            "SalesRevenueNet",
        ],
    )

    assert cov.concept == "SalesRevenueNet"
    assert cov.years == (2024,)


def test_first_candidate_with_annual_data_wins_over_a_present_but_empty_one():
    """A tag can exist and still carry no annual 10-K facts. Presence is not
    coverage — the fallback must keep walking."""
    facts = {
        "cik": 1,
        "entityName": "Test Corp",
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": []}},
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            _duration(
                                "2024-01-01",
                                "2024-12-31",
                                9.0,
                                fy=2024,
                                filed="2025-02-01",
                            )
                        ]
                    }
                },
            }
        },
    }
    cov = extract_concept(facts, ["Revenues", "SalesRevenueNet"])

    assert cov.concept == "SalesRevenueNet"


def test_a_tag_switch_is_merged_into_one_series():
    """ASC 606 made most US filers move from ``Revenues`` to
    ``RevenueFromContractWithCustomerExcludingAssessedTax`` around 2018. Taking
    the first candidate that carries data would return the stale tag and a
    series that ends in 2017 — measured on the real Agilent (CIK 1090872)
    filings, where ``Revenues`` stops at FY2017 and the contract tag runs
    2016-2025. The candidates are one concept, so their years are one series."""
    old = [
        _duration(f"{y}-01-01", f"{y}-12-31", float(y), fy=y, filed=f"{y + 1}-02-01")
        for y in (2015, 2016, 2017)
    ]
    new = [
        _duration(f"{y}-01-01", f"{y}-12-31", float(y), fy=y, filed=f"{y + 1}-02-01")
        for y in (2018, 2019, 2020)
    ]
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {"units": {"USD": old}},
                "RevenueFromContractWithCustomerExcludingAssessedTax": {
                    "units": {"USD": new}
                },
            }
        }
    }
    cov = extract_concept(
        facts, ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"]
    )

    assert cov.years == (2015, 2016, 2017, 2018, 2019, 2020)
    assert cov.contiguous == 6
    assert cov.concept == "Revenues+RevenueFromContractWithCustomerExcludingAssessedTax"


def test_an_overlapping_year_takes_the_earlier_candidate_and_is_no_restatement():
    """Two tags can report the same year with different definitions (total
    revenues vs. revenue from contracts). That is a definitional difference, not
    a correction — counting it as a restatement would invent a data problem."""
    facts = {
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _duration(
                                "2018-01-01",
                                "2018-12-31",
                                100.0,
                                fy=2018,
                                filed="2019-02-01",
                            )
                        ]
                    }
                },
                "SalesRevenueNet": {
                    "units": {
                        "USD": [
                            _duration(
                                "2018-01-01",
                                "2018-12-31",
                                90.0,
                                fy=2018,
                                filed="2019-02-01",
                            )
                        ]
                    }
                },
            }
        }
    }
    cov = extract_concept(facts, ["Revenues", "SalesRevenueNet"])

    assert cov.values == (100.0,)
    assert cov.restatements == 0
    assert cov.concept == "Revenues"


def test_missing_concept_yields_empty_coverage():
    facts = _facts("us-gaap", "Assets", [])
    cov = extract_concept(facts, ["Revenues"])

    assert cov == ConceptCoverage(
        concept=None,
        unit=None,
        years=(),
        values=(),
        contiguous=0,
        restatements=0,
        naive_fy_count=0,
    )


def test_non_usd_unit_is_reported_rather_than_silently_dropped():
    entries = [
        _duration("2024-01-01", "2024-12-31", 110.0, fy=2024, filed="2025-02-01"),
    ]
    facts = _facts("us-gaap", "Revenues", entries, unit="EUR")
    cov = extract_concept(facts, ["Revenues"])

    assert cov.unit == "EUR"
    assert cov.years == (2024,)


# --- instant (balance-sheet) concepts --------------------------------------


def test_instant_concept_uses_balance_dates():
    entries = [
        _instant("2023-12-31", 900.0, fy=2025, filed="2026-02-01"),
        _instant("2024-12-31", 950.0, fy=2025, filed="2026-02-01"),
        _instant("2025-12-31", 1000.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Assets", entries), ["Assets"])

    assert cov.years == (2023, 2024, 2025)
    assert cov.contiguous == 3
    assert cov.values == (900.0, 950.0, 1000.0)


def test_a_quarterly_balance_date_in_a_10k_does_not_displace_a_year_end():
    """Measured on Akamai (CIK 1086222): its 10-K tags 2022-03-31, 2022-06-30 and
    2022-09-30 alongside the year ends. 2022-03-31 carries the fiscal label 2021
    and, being the later date, would push the real 2021-12-31 balance out of the
    series — leaving a 455-day step that breaks the chain down to four years.
    The annual series is anchored on the fiscal year-end anniversary, so an
    off-anniversary date is dropped instead of competing."""
    ends = [
        "2019-12-31",
        "2020-12-31",
        "2021-12-31",
        "2022-03-31",
        "2022-06-30",
        "2022-09-30",
        "2022-12-31",
        "2023-12-31",
    ]
    entries = [_instant(e, float(e[:4]), fy=2023, filed="2024-02-01") for e in ends]
    cov = extract_concept(_facts("us-gaap", "Assets", entries), ["Assets"])

    assert cov.years == (2019, 2020, 2021, 2022, 2023)
    assert cov.contiguous == 5


def test_a_january_fiscal_year_end_is_its_own_anniversary():
    """The anchor is taken from the data, not from the calendar: a retailer
    closing on 31 January must not be mistaken for an off-anniversary date."""
    entries = [
        _instant(e, 1.0, fy=2024, filed="2025-03-01")
        for e in ("2023-01-31", "2024-01-31", "2025-01-31")
    ]
    cov = extract_concept(_facts("us-gaap", "Assets", entries), ["Assets"])

    assert cov.years == (2022, 2023, 2024)
    assert cov.contiguous == 3


def test_instant_mid_year_balance_dates_do_not_create_phantom_years():
    """A 10-K can carry a non-year-end instant. It must not displace the
    year-end value that shares its fiscal label."""
    entries = [
        _instant("2024-12-31", 950.0, fy=2024, filed="2025-02-01"),
        _instant("2025-06-30", 975.0, fy=2025, filed="2026-02-01"),
        _instant("2025-12-31", 1000.0, fy=2025, filed="2026-02-01"),
    ]
    cov = extract_concept(_facts("us-gaap", "Assets", entries), ["Assets"])

    assert cov.years == (2024, 2025)
    assert cov.values == (950.0, 1000.0)


# --- taxonomy and tag reporting -------------------------------------------


def test_taxonomies_names_what_is_present():
    facts = {
        "facts": {
            "ifrs-full": {"Revenue": {}},
            "dei": {"EntityCommonStockSharesOutstanding": {}},
        }
    }
    assert taxonomies(facts) == ["dei", "ifrs-full"]


def test_available_tags_lists_us_gaap_tags_for_the_gap_list():
    facts = {
        "facts": {
            "us-gaap": {
                "InterestAndDividendIncomeOperating": {},
                "Assets": {},
            }
        }
    }
    assert available_tags(facts, "us-gaap") == [
        "Assets",
        "InterestAndDividendIncomeOperating",
    ]


def test_available_tags_of_an_absent_taxonomy_is_empty():
    assert available_tags({"facts": {}}, "us-gaap") == []


# --- fiscal labelling ------------------------------------------------------


def test_fiscal_label_of_a_calendar_year_end():
    assert fiscal_label(date(2025, 12, 31)) == 2025


def test_fiscal_label_of_an_early_year_end_belongs_to_the_prior_year():
    """A retailer closing 2025-01-31 is reporting fiscal 2024."""
    assert fiscal_label(date(2025, 1, 31)) == 2024


def test_fiscal_label_boundary_is_june():
    assert fiscal_label(date(2025, 5, 31)) == 2024
    assert fiscal_label(date(2025, 6, 30)) == 2025


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
