from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from google import genai as _genai
from google.genai import types as _types

from app.errors import GeminiError

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)

DIMENSIONS = ["growth", "profitability", "management", "innovation", "resilience"]
_DEFAULT_MODEL = "gemini-2.0-flash-lite"


@dataclass
class GeminiScoreResult:
    dimensions: dict[str, int]
    summary: str
    tokens_in: int
    tokens_out: int


class GeminiClient(Protocol):
    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult: ...


class GeminiClientImpl:
    def __init__(self, api_key: str, model: str = _DEFAULT_MODEL) -> None:
        if not api_key:
            raise GeminiError("Gemini API key not set — configure FISHERSCREEN_GEMINI_API_KEY")
        self._client = _genai.Client(api_key=api_key)
        self._model = model

    def score_ticker(
        self,
        ticker: str,
        record: ScreenerRecord,
        max_input_tokens: int = 3000,
        max_output_tokens: int = 1000,
    ) -> GeminiScoreResult:
        prompt = _build_prompt(ticker, record)
        try:
            token_resp = self._client.models.count_tokens(model=self._model, contents=prompt)
        except Exception as exc:
            logger.warning("ticker=%s token count failed: %s", ticker, exc)
            raise GeminiError(f"Token count failed for {ticker}: {exc}") from exc
        if token_resp.total_tokens > max_input_tokens:
            logger.warning(
                "ticker=%s prompt too large: %d > %d tokens — skipping",
                ticker, token_resp.total_tokens, max_input_tokens,
            )
            raise GeminiError(
                f"ticker={ticker} prompt too large: {token_resp.total_tokens} > {max_input_tokens} tokens"
            )
        try:
            response = self._client.models.generate_content(
                model=self._model,
                contents=prompt,
                config=_types.GenerateContentConfig(
                    response_mime_type="application/json",
                    max_output_tokens=max_output_tokens,
                ),
            )
        except Exception as exc:
            logger.warning("ticker=%s Gemini API call failed: %s", ticker, exc)
            raise GeminiError(f"Gemini API call failed for {ticker}: {exc}") from exc
        return _parse_response(ticker, response)


def _build_prompt(ticker: str, record: ScreenerRecord) -> str:
    def fmt(val: float | None, pct: bool = False) -> str:
        if val is None:
            return "n/a"
        return f"{val:.1%}" if pct else f"{val:.2f}"

    market_cap_str = f"${record.market_cap:,.0f}" if record.market_cap is not None else "n/a"
    lines = [
        f"You are evaluating {record.name or ticker} ({ticker}), "
        f"a {record.gics_sector or 'unknown sector'} / "
        f"{record.gics_industry or 'unknown industry'} company, "
        "for alignment with Phil Fisher's investment principles.",
        "",
        "Available financial data:",
        f"- Market Cap: {market_cap_str}",
        f"- Revenue Growth (YoY): {fmt(record.revenue_growth_yoy, pct=True)}",
        f"- Operating Margin: {fmt(record.operating_margin, pct=True)}",
        f"- Return on Equity: {fmt(record.return_on_equity, pct=True)}",
        f"- Debt to Equity: {fmt(record.debt_to_equity)}",
        "",
        "Score each dimension from 1 (very weak) to 5 (very strong) "
        "based on the data above and your knowledge of this company.",
        "",
        "Return ONLY valid JSON:",
        '{"dimensions": {"growth": <1-5>, "profitability": <1-5>, '
        '"management": <1-5>, "innovation": <1-5>, "resilience": <1-5>}, '
        '"summary": "<1-2 sentences>"}',
    ]
    return "\n".join(lines)


def _parse_response(ticker: str, response: Any) -> GeminiScoreResult:
    try:
        data = json.loads(response.text)
    except (json.JSONDecodeError, AttributeError, ValueError) as exc:
        raise GeminiError(f"Gemini returned invalid JSON for {ticker}: {exc}") from exc
    raw = data.get("dimensions", {})
    dimensions: dict[str, int] = {}
    for dim in DIMENSIONS:
        val = raw.get(dim)
        if not isinstance(val, (int, float)):
            raise GeminiError(f"Missing or invalid dimension '{dim}' for {ticker}")
        dimensions[dim] = max(1, min(5, int(val)))
    usage = getattr(response, "usage_metadata", None)
    tokens_in = getattr(usage, "prompt_token_count", 0) or 0
    tokens_out = getattr(usage, "candidates_token_count", 0) or 0
    return GeminiScoreResult(
        dimensions=dimensions,
        summary=str(data.get("summary", "")),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
