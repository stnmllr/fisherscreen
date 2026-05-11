from typing import Protocol


class GeminiClient(Protocol):
    def complete(self, prompt: str, model: str, max_tokens: int) -> str: ...
