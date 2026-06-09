class FisherScreenError(Exception):
    """Base exception for all FisherScreen errors."""


class DataSourceError(FisherScreenError):
    """Raised when an external data source fails: yfinance, EDGAR, Apify, Marketaux."""


class DegradedDataError(DataSourceError):
    """Raised when yfinance returns a non-empty but degraded info dict (no
    identity, no marketCap). Subclass of DataSourceError so existing handlers
    still catch it; lets the resolution stage distinguish DEGRADED_DICT from
    generic unresolved attrition."""


class GeminiError(FisherScreenError):
    """Raised on Gemini API call failure (Flash Lite or Pro)."""


class FilterConfigError(FisherScreenError):
    """Raised when negative filter configuration is invalid or contradictory."""


class DeepDiveError(FisherScreenError):
    """Raised on Tool B deep-dive failures: unresolvable ticker, missing filing."""
