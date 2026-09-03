"""Data model for a parsed Tool-B dossier.

Read side of `app/deepdive/dossier_generator.py`. Deliberately permissive:
the generator's output format changed twice already (Gen 1 without insider
block, Gen 2 without insider frontmatter, Gen 3 with both), and older
dossiers stay on disk forever. Therefore every content field is optional or
defaults to an empty container — a field that could not be parsed is None,
never a fabricated value (honest-label principle).
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

MIN_RATING = 1
MAX_RATING = 5


class ParsedPoint(BaseModel):
    """One of Fisher's 15 points as rendered in a dossier.

    `number` is the only guaranteed field: the parser emits a placeholder
    point for every number the dossier does not contain, so consumers can
    always iterate 1..15 without branching.
    """

    number: int
    title: str | None = None
    rating: int | None = Field(default=None, ge=MIN_RATING, le=MAX_RATING)
    confidence: str | None = None
    reasoning: str | None = None
    sources: list[str] = Field(default_factory=list)
    is_placeholder: bool = False


class Dossier(BaseModel):
    """A single parsed dossier file.

    Frontmatter fields keep the generator's names 1:1 so a mismatch is easy
    to spot. Body-derived fields carry the raw strings; no number is
    re-derived here — the dossier is the source of truth.
    """

    # --- frontmatter ---
    ticker: str
    form_type: str
    generated_at: datetime
    adr_ticker: str | None = None
    cik: str | None = None
    filing_date: date | None = None
    quant_date: date | None = None
    days_since_filing: int | None = None
    section_flags: dict[str, str] = Field(default_factory=dict)
    peer_tickers: list[str] = Field(default_factory=list)
    peer_rationale: str | None = None
    insider_coverage_state: str | None = None
    insider_n_filings: int | None = None
    insider_significant_count: int | None = None
    insider_net_buy: float | None = None
    insider_net_sell: float | None = None

    # --- body ---
    company_name: str | None = None
    executive_summary: str | None = None
    headline_metrics: dict[str, str] = Field(default_factory=dict)
    metrics: dict[str, dict[str, str]] = Field(default_factory=dict)
    raw_metric_lines: dict[str, str] = Field(default_factory=dict)
    metric_extras: dict[str, list[str]] = Field(default_factory=dict)
    peer_table: list[list[str]] = Field(default_factory=list)
    points: list[ParsedPoint] = Field(default_factory=list)
    insider_summary_line: str | None = None
    insider_detail_lines: list[str] = Field(default_factory=list)
    source_coverage: dict[str, str] = Field(default_factory=dict)
    notes: str | None = None

    # --- provenance ---
    source_path: Path

    @field_validator("cik", "adr_ticker", mode="before")
    @classmethod
    def _coerce_to_string(cls, value: object) -> object:
        """YAML types the CIK as int when the generator wrote it unquoted."""
        if value is None or isinstance(value, str):
            return value
        return str(value)
