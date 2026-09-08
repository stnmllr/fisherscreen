"""Unit tests for the EDGAR annual-series extraction.

The probe's whole value rests on one decision: a fact's ``fy``/``fp`` names the
FILING that reported it, not the period the value covers. Keying by ``fy`` would
collapse a 10-K's comparative years into one. These tests pin the period-keyed
behaviour, because that is the difference between "EDGAR gives us three years"
and "EDGAR gives us ten".
"""

from datetime import date

from app.services.edgar_annual_series_client import (
    ConceptCoverage,
    available_tags,
    contiguous_run,
    extract_concept,
    fiscal_label,
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


# --- the client layer: three concepts, no equity ---------------------------


def _annual(tag, years, form="10-K"):
    return {
        tag: {
            "units": {
                "USD": [
                    _duration(
                        f"{y}-01-01",
                        f"{y}-12-31",
                        float(y),
                        fy=y,
                        filed=f"{y + 1}-02-01",
                        form=form,
                    )
                    for y in years
                ]
            }
        }
    }


def _three_concept_facts(years=(2023, 2024, 2025)):
    tags = {}
    tags.update(_annual("Revenues", years))
    tags.update(_annual("OperatingIncomeLoss", years))
    tags.update(_annual("NetIncomeLoss", years))
    return {"entityName": "Test Corp", "facts": {"us-gaap": tags}}


class _FakeEdgar:
    def __init__(self, facts):
        self.facts = facts
        self.seen = []

    def get_company_facts(self, cik):
        self.seen.append(cik)
        return self.facts


def test_the_client_asks_for_the_cik_it_was_given_and_returns_three_series():
    from app.services.edgar_annual_series_client import EdgarAnnualSeriesClientImpl

    edgar = _FakeEdgar(_three_concept_facts())
    record = EdgarAnnualSeriesClientImpl(edgar).get_annual_series("0000320193")

    assert edgar.seen == ["0000320193"]
    assert record.cik == "0000320193"
    assert record.entity == "Test Corp"
    assert set(record.concepts) == {"revenue", "operating_income", "net_income"}
    assert record.usable


def test_equity_is_not_among_the_concepts():
    """Dropped when S3 became the worst net margin: 41 of 610 measured titles
    carry too few years of positive equity, FICO and TDG among them — the very
    titles the dimension must keep on top."""
    from app.services.edgar_annual_series_client import CONCEPTS

    flat = [tag for tags in CONCEPTS.values() for tag in tags]
    assert not [tag for tag in flat if "StockholdersEquity" in tag]
    assert "Assets" not in flat


def test_a_missing_concept_sets_a_reason_rather_than_an_empty_series():
    """The gate reads the reason, never a score value (spec 8.1). A record that
    merely looked empty would be indistinguishable from a real weak result."""
    from app.services.edgar_annual_series_client import (
        NO_CONCEPT,
        build_annual_series,
    )

    facts = {"entityName": "Bank Corp", "facts": {"us-gaap": {}}}
    facts["facts"]["us-gaap"].update(_annual("Revenues", (2023, 2024, 2025)))
    record = build_annual_series("0000000001", facts)

    assert record.reason == NO_CONCEPT
    assert not record.usable
    assert record.concepts["revenue"].concept == "Revenues"
    assert record.concepts["net_income"].concept is None


def test_the_long_operating_income_fallbacks_are_spelled_exactly():
    """Both are written across two source lines. A slip in the join would make
    them silently unmatchable — and they carry 59 and 38 titles."""
    from app.services.edgar_annual_series_client import CONCEPTS

    assert CONCEPTS["operating_income"][1:] == [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
        "ExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest"
        "AndIncomeLossFromEquityMethodInvestments",
    ]


def test_coverage_survives_a_round_trip_through_the_persisted_shape():
    """What gets cached is the extract, never the multi-MB companyfacts doc.

    The written shape uses lists, not tuples: Firestore has no tuple type and
    returns arrays as lists either way. Writing tuples would make the value
    read back differ from the value written — a difference that only shows up
    against a real store, never against a dict-shaped fake."""
    from app.services.edgar_annual_series_client import (
        build_annual_series,
        coverage_from_dict,
        coverage_to_dict,
    )

    record = build_annual_series("1", _three_concept_facts())
    payload = coverage_to_dict(record.concepts["revenue"])

    assert payload["years"] == [2023, 2024, 2025]
    assert isinstance(payload["values"], list)
    assert coverage_from_dict(payload) == record.concepts["revenue"]


def test_a_20f_filer_with_us_gaap_tags_still_yields_nothing():
    """Measured on ASML (CIK 937966): it carries 623 us-gaap tags and files on
    Form 20-F. Only the form filter keeps those facts out — without it the title
    would receive a steadiness score built from a series the spec never examined
    (spec section 3 excludes 20-F/ifrs-full deliberately).

    Novo Nordisk is the easy half of the case: it reports under ifrs-full and
    has no us-gaap node at all. ASML is the hard half, and the one that needs a
    test."""
    from app.services.edgar_annual_series_client import build_annual_series

    facts = {
        "entityName": "ASML HOLDING NV",
        "facts": {
            "us-gaap": {
                "Revenues": {
                    "units": {
                        "USD": [
                            _duration(
                                f"{y}-01-01",
                                f"{y}-12-31",
                                float(y),
                                fy=y,
                                filed=f"{y + 1}-02-01",
                                form="20-F",
                            )
                            for y in range(2015, 2026)
                        ]
                    }
                }
            }
        },
    }
    record = build_annual_series("0000937966", facts)

    assert record.reason == "no_concept"
    assert record.concepts["revenue"].years == ()
