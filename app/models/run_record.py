from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

COST_PER_1M_INPUT_USD = 0.10
COST_PER_1M_OUTPUT_USD = 0.40


class RunRecord(BaseModel):
    run_id: str
    tickers_processed: int = 0
    tickers_skipped: int = 0
    tokens_in_total: int = 0
    tokens_out_total: int = 0
    estimated_cost_usd: float = 0.0
    status: str = "success"  # "success" | "partial" | "aborted"
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def compute_cost(self) -> float:
        return (
            (self.tokens_in_total / 1_000_000 * COST_PER_1M_INPUT_USD)
            + (self.tokens_out_total / 1_000_000 * COST_PER_1M_OUTPUT_USD)
        )
