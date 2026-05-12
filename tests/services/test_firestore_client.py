from unittest.mock import MagicMock, patch

import pytest

from app.errors import DataSourceError


@patch("app.services.firestore_client.firestore")
def test_get_returns_dict_when_document_exists(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_doc = MagicMock()
    mock_doc.exists = True
    mock_doc.to_dict.return_value = {"ticker": "AAPL", "marketCap": 3e12}
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    result = client.get("dev_ticker_cache", "AAPL")

    assert result == {"ticker": "AAPL", "marketCap": 3e12}


@patch("app.services.firestore_client.firestore")
def test_get_returns_none_when_document_missing(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_doc = MagicMock()
    mock_doc.exists = False
    mock_db.collection.return_value.document.return_value.get.return_value = mock_doc

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    result = client.get("dev_ticker_cache", "UNKNOWN")

    assert result is None


@patch("app.services.firestore_client.firestore")
def test_set_calls_firestore_set(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    client.set("dev_ticker_cache", "AAPL", {"marketCap": 3e12})

    mock_db.collection.return_value.document.return_value.set.assert_called_once_with(
        {"marketCap": 3e12}
    )


@patch("app.services.firestore_client.firestore")
def test_delete_calls_firestore_delete(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")
    client.delete("dev_ticker_cache", "AAPL")

    mock_db.collection.return_value.document.return_value.delete.assert_called_once()


@patch("app.services.firestore_client.firestore")
def test_get_raises_data_source_error_on_failure(mock_firestore_module):
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_db.collection.return_value.document.return_value.get.side_effect = Exception(
        "network error"
    )

    from app.services.firestore_client import FirestoreClientImpl
    client = FirestoreClientImpl(project_id="test-project")

    with pytest.raises(DataSourceError, match="Firestore get failed"):
        client.get("dev_ticker_cache", "AAPL")


@patch("app.services.firestore_client.firestore")
def test_init_raises_data_source_error_when_adc_missing(mock_firestore_module):
    # The smoke call next(self._db.collections(), None) forces credential validation.
    # Simulate ADC failure by making collections() raise on the smoke call.
    mock_db = MagicMock()
    mock_firestore_module.Client.return_value = mock_db
    mock_db.collections.side_effect = Exception("ADC not found")

    from app.services.firestore_client import FirestoreClientImpl

    with pytest.raises(DataSourceError, match="ADC not configured"):
        FirestoreClientImpl(project_id="test-project")
