import frontmatter

from app.deepdive.dossier_generator import generate_dossier
from app.models.deep_dive_record import (
    DeepDiveRecord, FisherPoint, PointInTimeQuant, QuantSnapshot, SourceCoverage)


def _record():
    pts = [FisherPoint(number=n, title=f"Punkt {n}", rating=4, confidence="🟢",
                       reasoning="Begründung.", sources=["20-F §5"])
           for n in range(1, 16)]
    return DeepDiveRecord(
        ticker="NOVO-B.CO", adr_ticker="NVO", cik="0000353278",
        form_type="20-F", filing_sections={"20-F_item5": "x"},
        section_flags={}, synthesis=pts,
        quant_snapshot=QuantSnapshot(point_in_time=PointInTimeQuant(
            ticker="NOVO-B.CO", name="Novo Nordisk")),
        source_coverage=SourceCoverage(edgar="20-F via ADR"))


def test_writes_file_with_date_name(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    assert p.parent.name == "Watchlist"
    assert p.name.startswith("NOVO-B.CO_")
    assert p.name.endswith(".md")


def test_frontmatter_and_15_miniblocks(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    post = frontmatter.loads(p.read_text(encoding="utf-8"))
    assert post["ticker"] == "NOVO-B.CO"
    assert post["form_type"] == "20-F"
    body = post.content
    for n in range(1, 16):
        assert f"### Punkt {n} —" in body
    assert "| # | Punkt |" not in body  # NOT a table
    assert "## Source Coverage" in body
    assert "20-F via ADR" in body
    assert "Stef's Notizen" in body


def test_each_point_renders_a_source_marker(tmp_path):
    p = generate_dossier(_record(), tmp_path)
    body = frontmatter.loads(p.read_text(encoding="utf-8")).content
    assert body.count("[20-F §5]") == 15
