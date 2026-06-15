from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from google import genai as _genai
from google.genai import types as _types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.errors import GeminiError
from app.screener.dimensions import DIMENSIONS

if TYPE_CHECKING:
    from app.models.screener_record import ScreenerRecord

logger = logging.getLogger(__name__)
_DEFAULT_MODEL = "gemini-2.5-flash-lite"


def _is_retryable(exc: BaseException) -> bool:
    return (isinstance(exc, ServerError) and exc.code == 503) or (
        isinstance(exc, ClientError) and exc.code == 429
    )


_RETRY = dict(
    retry=retry_if_exception(_is_retryable),
    stop=stop_after_attempt(4),
    wait=wait_exponential(multiplier=1, exp_base=4),
    reraise=True,
)


@dataclass
class GeminiScoreResult:
    dimensions: dict[str, int]
    evidence: dict[str, str]  # per-dimension evidence notes (v2.1 flat schema)
    weakest_dimension: str
    data_gaps: list[str]
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
            token_resp = self._count_tokens(prompt)
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
            response = self._generate(prompt, max_output_tokens)
        except Exception as exc:
            logger.warning("ticker=%s Gemini API call failed: %s", ticker, exc)
            raise GeminiError(f"Gemini API call failed for {ticker}: {exc}") from exc
        return _parse_response(ticker, response)

    @retry(**_RETRY)
    def _count_tokens(self, prompt: str) -> Any:
        return self._client.models.count_tokens(model=self._model, contents=prompt)

    @retry(**_RETRY)
    def _generate(self, prompt: str, max_output_tokens: int) -> Any:
        return self._client.models.generate_content(
            model=self._model,
            contents=prompt,
            config=_types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=_RESPONSE_SCHEMA,
                temperature=0,
                max_output_tokens=max_output_tokens,
            ),
        )


def _build_prompt(ticker: str, record: ScreenerRecord) -> str:
    def pct(val: float | None) -> str:
        return "n/a" if val is None else f"{val:.1%}"

    def num(val: float | None) -> str:
        return "n/a" if val is None else f"{val:.2f}"

    return _PROMPT_TEMPLATE.format(
        ticker=ticker,
        revenue_growth_yoy=pct(record.revenue_growth_yoy),
        operating_margin=pct(record.operating_margin),
        gross_margin=pct(record.gross_margin),
        return_on_equity=pct(record.return_on_equity),
        debt_to_equity=num(record.debt_to_equity),
    )


_PROMPT_TEMPLATE = """\
You are a skeptical, evidence-driven equity analyst applying Philip Fisher's
qualitative framework. You score ONE company on five dimensions, using ONLY the
DATA block below.

CRITICAL RULES
1. The DATA block is the ONLY source of truth. You have NO outside knowledge of
   this company. The ticker is given solely so the output can be keyed - it is NOT
   a knowledge cue. Disregard any familiarity with the ticker or company. A
   recognizable name earns no points.
2. Every score >= 4 MUST quote a specific figure from the DATA block in its
   evidence note. If you cannot cite a concrete figure that supports a 4+, the
   score cannot exceed 3.
3. Default to 3. A 3 means "average / unremarkable / nothing in the data stands
   out." Most dimensions land at 2-4.
4. Reserve 5 for top-decile evidence in the DATA. If a typical large company could
   plausibly show the same figure, it is a 4 or lower, not a 5.
5. Real businesses have weaknesses. It should be rare for growth, profitability AND
   resilience to all score 4-5 for the same company. Set weakest_dimension to
   whichever of growth, profitability, resilience scored lowest, and score it
   honestly - do not round it up.

SCORE ANCHORS (integers only)
5  Exceptional - top-decile figure in the DATA. Must cite it.
4  Clearly above average - a concrete figure supports it.
3  Average / unremarkable / insufficient data. (DEFAULT)
2  Below average - the DATA shows a soft or mixed picture.
1  Weak - the DATA shows a clear negative.
0  Red flag - the DATA shows a structural problem or deterioration.

DIMENSIONS - judge each ONLY from the listed inputs and cite figures:
- growth        <- revenue_growth_yoy. Trajectory of the top line.
- profitability <- operating_margin, return_on_equity. Level of margins and
                   returns on capital.
- resilience    <- debt_to_equity (leverage), gross_margin (margin cushion). Low
                   leverage + healthy margin floor = strong.
- management    <- no capital-allocation, insider, or governance data is provided
                   here; governance is screened upstream. Score exactly 3 and set
                   management_evidence to "insufficient data: governance screened
                   upstream". Do NOT infer from reputation, sector, or size.
- innovation    <- no R&D or reinvestment data is provided. Score exactly 3 and set
                   innovation_evidence to "insufficient data: no R&D data". Do NOT
                   infer from reputation, sector, or company size.

For every dimension output the integer score AND a one-sentence evidence note that
quotes at least one figure from the DATA. Where the DATA lacks the input for a
dimension, score 3 and write "insufficient data: <what is missing>".

OUTPUT FORMAT
Return ONLY one JSON object. No prose, no markdown, no code fences, nothing before
or after. The first character must be {{ and the last must be }}.

Schema (FLAT, exact keys):
{{"ticker":"<TICKER>","growth":<0-5>,"growth_evidence":"<...>","profitability":<0-5>,"profitability_evidence":"<...>","management":3,"management_evidence":"insufficient data: governance screened upstream","innovation":3,"innovation_evidence":"insufficient data: no R&D data","resilience":<0-5>,"resilience_evidence":"<...>","weakest_dimension":"<growth|profitability|resilience>","data_gaps":["<field>","..."]}}

DATA
ticker: {ticker}            # output key only - not a knowledge cue
revenue_growth_yoy: {revenue_growth_yoy}
operating_margin: {operating_margin}
gross_margin: {gross_margin}
return_on_equity: {return_on_equity}
debt_to_equity: {debt_to_equity}"""


def _build_response_schema() -> _types.Schema:
    """Flat JSON schema matching the v2.1 prompt output keys.

    Enforced server-side alongside response_mime_type=application/json. Tests mock
    the SDK, so this only matters at runtime."""
    string = _types.Schema(type=_types.Type.STRING)
    score = _types.Schema(type=_types.Type.INTEGER)
    properties: dict[str, _types.Schema] = {"ticker": string}
    for dim in DIMENSIONS:
        properties[dim] = score
        properties[f"{dim}_evidence"] = string
    properties["weakest_dimension"] = string
    properties["data_gaps"] = _types.Schema(
        type=_types.Type.ARRAY, items=_types.Schema(type=_types.Type.STRING)
    )
    return _types.Schema(type=_types.Type.OBJECT, properties=properties)


_RESPONSE_SCHEMA = _build_response_schema()


def _truncate_to_first_object(text: str) -> str | None:
    """Return the substring from the first '{' up to (and including) the '}' that
    balances it. Used to recover when the model appends prose after the JSON
    ("Extra data" decode failure). Returns None if no balanced object is found."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        char = text[i]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def _load_json(ticker: str, raw_text: str) -> dict[str, Any]:
    try:
        return json.loads(raw_text)
    except json.JSONDecodeError:
        truncated = _truncate_to_first_object(raw_text)
        if truncated is None:
            raise GeminiError(f"Gemini returned invalid JSON for {ticker}: no JSON object found")
        try:
            return json.loads(truncated)
        except json.JSONDecodeError as exc:
            raise GeminiError(f"Gemini returned invalid JSON for {ticker}: {exc}") from exc


def _parse_response(ticker: str, response: Any) -> GeminiScoreResult:
    try:
        raw_text = response.text
    except AttributeError as exc:
        raise GeminiError(f"Gemini returned invalid JSON for {ticker}: {exc}") from exc
    data = _load_json(ticker, raw_text)

    dimensions: dict[str, int] = {}
    evidence: dict[str, str] = {}
    for dim in DIMENSIONS:
        val = data.get(dim)
        if not isinstance(val, (int, float)):
            raise GeminiError(f"Missing or invalid dimension '{dim}' for {ticker}")
        dimensions[dim] = max(0, min(5, int(val)))  # 0 is a valid red-flag score
        evidence[dim] = str(data.get(f"{dim}_evidence", ""))

    raw_gaps = data.get("data_gaps", [])
    data_gaps = [str(g) for g in raw_gaps] if isinstance(raw_gaps, list) else []

    usage = getattr(response, "usage_metadata", None)
    tokens_in = getattr(usage, "prompt_token_count", 0) or 0
    tokens_out = getattr(usage, "candidates_token_count", 0) or 0
    return GeminiScoreResult(
        dimensions=dimensions,
        evidence=evidence,
        weakest_dimension=str(data.get("weakest_dimension", "")),
        data_gaps=data_gaps,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
    )
