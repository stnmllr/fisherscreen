import pytest
from pydantic import ValidationError

from app.models.deep_dive_record import (
    DeepDiveRecord,
    FisherPoint,
    PointInTimeQuant,
    QuantSnapshot,
    SourceCoverage,
)


def _valid_point(**over):
    base = dict(number=1, title="Marktpotential", rating=4,
                confidence="🟢", reasoning="Solide.", sources=["20-F §4"])
    base.update(over)
    return FisherPoint(**base)


def test_fisher_point_minimal_valid():
    p = _valid_point()
    assert p.number == 1 and p.rating == 4 and p.sources == ["20-F §4"]


def test_fisher_point_rejects_extra_field():
    with pytest.raises(ValidationError):
        FisherPoint(number=1, title="x", rating=3, confidence="🟡",
                    reasoning="r", sources=["x"], bogus=1)


def test_fisher_point_rating_out_of_range_rejected():
    with pytest.raises(ValidationError):
        _valid_point(rating=6)
    with pytest.raises(ValidationError):
        _valid_point(rating=0)


def test_fisher_point_confidence_must_be_marker():
    with pytest.raises(ValidationError):
        _valid_point(confidence="high")


def test_fisher_point_sources_not_empty():
    with pytest.raises(ValidationError):
        _valid_point(sources=[])


def test_fisher_point_reasoning_word_cap_70():
    with pytest.raises(ValidationError):
        _valid_point(reasoning=" ".join(["w"] * 71))


def test_fisher_point_reasoning_exactly_70_words_accepted():
    p = _valid_point(reasoning=" ".join(["w"] * 70))
    assert len(p.reasoning.split()) == 70


def test_fisher_point_inference_only_caps_confidence_to_yellow():
    # sources == ['Inferenz'] must force confidence != 🟢 (ADR-5c / spec §5)
    p = _valid_point(sources=["Inferenz"], confidence="🟢")
    assert p.confidence == "🟡"


def test_fisher_point_inference_only_keeps_red():
    p = _valid_point(sources=["Inferenz"], confidence="🔴")
    assert p.confidence == "🔴"


def test_quant_snapshot_defaults_allow_missing_optional():
    qs = QuantSnapshot(point_in_time=PointInTimeQuant(ticker="NOVO-B.CO"))
    assert qs.historical_series is None
    assert qs.trend_metrics is None
    assert qs.gemini_dimensions is None


def test_deep_dive_record_roundtrip_and_forbid_extra():
    rec = DeepDiveRecord(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278",
        form_type="20-F", filing_sections={"20-F_item5": "text"},
        section_flags={}, quant_snapshot=QuantSnapshot(
            point_in_time=PointInTimeQuant(ticker="NOVO-B.CO")),
        synthesis=[_valid_point(number=n) for n in range(1, 16)],
        source_coverage=SourceCoverage(),
    )
    assert len(rec.synthesis) == 15
    assert rec.generated_at is not None
    with pytest.raises(ValidationError):
        DeepDiveRecord(**{**rec.model_dump(), "nope": 1})


def test_deep_dive_record_form_type_literal():
    with pytest.raises(ValidationError):
        DeepDiveRecord(
            ticker="X", adr_ticker=None, cik="0000000001", form_type="8-K",
            filing_sections={}, section_flags={},
            quant_snapshot=QuantSnapshot(point_in_time=PointInTimeQuant(ticker="X")),
            synthesis=[], source_coverage=SourceCoverage(),
        )
