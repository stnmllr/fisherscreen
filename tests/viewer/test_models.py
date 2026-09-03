"""Model-level tests for the viewer data model.

Honest-label invariant under test: every content field is optional. A
missing value must surface as None / empty container, never as a
fabricated default that a later renderer would print as fact.
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.viewer.models import Dossier, ParsedPoint


def test_parsed_point_defaults_are_empty_not_fabricated():
    point = ParsedPoint(number=7)

    assert point.number == 7
    assert point.title is None
    assert point.rating is None
    assert point.confidence is None
    assert point.reasoning is None
    assert point.sources == []


def test_parsed_point_sources_not_shared_between_instances():
    first = ParsedPoint(number=1)
    second = ParsedPoint(number=2)
    first.sources.append("10-K Item 1")

    assert second.sources == []


def test_parsed_point_rejects_rating_out_of_range():
    with pytest.raises(ValidationError):
        ParsedPoint(number=1, rating=6)


def test_dossier_minimal_construction(tmp_path):
    dossier = Dossier(
        ticker="ARGX",
        form_type="20-F",
        generated_at=datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc),
        source_path=tmp_path / "ARGX_2026-08-20.md",
    )

    assert dossier.ticker == "ARGX"
    assert dossier.company_name is None
    assert dossier.executive_summary is None
    assert dossier.filing_date is None
    assert dossier.days_since_filing is None
    assert dossier.metrics == {}
    assert dossier.raw_metric_lines == {}
    assert dossier.metric_extras == {}
    assert dossier.peer_table == []
    assert dossier.peer_tickers == []
    assert dossier.points == []
    assert dossier.insider_summary_line is None
    assert dossier.insider_detail_lines == []
    assert dossier.source_coverage == {}
    assert dossier.notes is None
    assert dossier.headline_metrics == {}
    assert isinstance(dossier.source_path, Path)


def test_dossier_requires_ticker():
    with pytest.raises(ValidationError):
        Dossier(
            form_type="10-K",
            generated_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            source_path=Path("x.md"),
        )


def test_dossier_coerces_cik_to_string():
    """YAML renders an unquoted CIK as int in some generations; the viewer
    must not carry two types for the same field."""
    dossier = Dossier(
        ticker="FICO",
        form_type="10-K",
        generated_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
        source_path=Path("FICO_2026-07-01.md"),
        cik=814547,
    )

    assert dossier.cik == "814547"


def test_parsed_point_is_not_a_placeholder_by_default():
    """A placeholder point is one the parser invented to complete 1..15.
    The renderer must be able to tell it apart from a real one."""
    assert ParsedPoint(number=3).is_placeholder is False
    assert ParsedPoint(number=3, is_placeholder=True).is_placeholder is True
