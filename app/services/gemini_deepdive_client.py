from __future__ import annotations

import json
import logging
from typing import Any, Protocol

from google import genai as _genai
from google.genai import types as _types
from google.genai.errors import ClientError, ServerError
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app.errors import GeminiError

logger = logging.getLogger(__name__)


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


class DeepDiveSynthesizer(Protocol):
    def synthesize(
        self, system_prompt: str, user_prompt: str, max_input_tokens: int
    ) -> dict[str, Any]: ...


class GeminiDeepDiveClient:
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise GeminiError(
                "Gemini API key not set — configure FISHERSCREEN_GEMINI_API_KEY"
            )
        self._client = _genai.Client(api_key=api_key)
        self._model = model

    def synthesize(
        self, system_prompt: str, user_prompt: str, max_input_tokens: int
    ) -> dict[str, Any]:
        full = f"{system_prompt}\n\n{user_prompt}"
        try:
            tok = self._count_tokens(full)
        except Exception as exc:
            raise GeminiError(f"token count failed: {exc}") from exc
        if tok.total_tokens > max_input_tokens:
            logger.warning(
                "deepdive prompt too large: %d > %d tokens",
                tok.total_tokens, max_input_tokens,
            )
            raise GeminiError(
                f"prompt too large: {tok.total_tokens} > {max_input_tokens} tokens"
            )
        if tok.total_tokens > max_input_tokens * 0.8:
            logger.warning(
                "deepdive prompt at %d/%d tokens (>80%% of cap)",
                tok.total_tokens, max_input_tokens,
            )
        try:
            resp = self._generate(system_prompt, user_prompt)
        except Exception as exc:
            raise GeminiError(f"Gemini API call failed: {exc}") from exc
        text = getattr(resp, "text", None)
        if not text:
            raise GeminiError("Gemini returned empty response (safety-filtered?)")
        try:
            return json.loads(text)
        except (json.JSONDecodeError, ValueError) as exc:
            raise GeminiError(f"Gemini returned invalid JSON: {exc}") from exc

    @retry(**_RETRY)
    def _count_tokens(self, prompt: str) -> Any:
        return self._client.models.count_tokens(model=self._model, contents=prompt)

    @retry(**_RETRY)
    def _generate(self, system_prompt: str, user_prompt: str) -> Any:
        return self._client.models.generate_content(
            model=self._model,
            contents=user_prompt,
            config=_types.GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            ),
        )
