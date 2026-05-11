from typing import Protocol


class MarketauxClient(Protocol):
    def get_news(self, ticker: str, days: int = 90) -> list[dict]: ...
