import pytest
from app.errors import DataSourceError, FilterConfigError, FisherScreenError, GeminiError


def test_all_subclass_base():
    assert issubclass(DataSourceError, FisherScreenError)
    assert issubclass(GeminiError, FisherScreenError)
    assert issubclass(FilterConfigError, FisherScreenError)


def test_base_subclasses_exception():
    assert issubclass(FisherScreenError, Exception)


def test_datasource_catchable_as_base():
    with pytest.raises(FisherScreenError):
        raise DataSourceError("yfinance timeout on AAPL")


def test_gemini_catchable_as_base():
    with pytest.raises(FisherScreenError):
        raise GeminiError("quota exceeded: 500000 tokens")


def test_filter_config_catchable_as_base():
    with pytest.raises(FisherScreenError):
        raise FilterConfigError("gross_margin_threshold must be > 0")


def test_errors_carry_message():
    err = DataSourceError("connection refused")
    assert str(err) == "connection refused"


def test_deepdive_subclass_base():
    from app.errors import DeepDiveError

    assert issubclass(DeepDiveError, FisherScreenError)


def test_deepdive_catchable_as_base():
    from app.errors import DeepDiveError

    with pytest.raises(FisherScreenError):
        raise DeepDiveError("ticker NOVO-B.CO not resolvable")
