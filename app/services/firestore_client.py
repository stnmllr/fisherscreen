from typing import Any, Protocol

from google.cloud import firestore

from app.errors import DataSourceError


class FirestoreClient(Protocol):
    def get(self, collection: str, document_id: str) -> dict[str, Any] | None: ...
    def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None: ...
    def delete(self, collection: str, document_id: str) -> None: ...
    def get_latest(self, collection: str, order_by: str) -> dict[str, Any] | None: ...


class FirestoreClientImpl:
    def __init__(self, project_id: str) -> None:
        try:
            self._db = firestore.Client(project=project_id)
            next(
                self._db.collections(), None
            )  # force credential validation at init time
        except Exception as exc:
            raise DataSourceError(
                f"ADC not configured or Firestore unreachable: {exc}"
            ) from exc

    def get(self, collection: str, document_id: str) -> dict[str, Any] | None:
        try:
            doc = self._db.collection(collection).document(document_id).get()
            if not doc.exists:
                return None
            return doc.to_dict()
        except Exception as exc:
            raise DataSourceError(f"Firestore get failed: {exc}") from exc

    def set(self, collection: str, document_id: str, data: dict[str, Any]) -> None:
        try:
            self._db.collection(collection).document(document_id).set(data)
        except Exception as exc:
            raise DataSourceError(f"Firestore set failed: {exc}") from exc

    def delete(self, collection: str, document_id: str) -> None:
        try:
            self._db.collection(collection).document(document_id).delete()
        except Exception as exc:
            raise DataSourceError(f"Firestore delete failed: {exc}") from exc

    def get_latest(self, collection: str, order_by: str) -> dict[str, Any] | None:
        """Newest document by `order_by` (descending), or None for an empty collection."""
        try:
            query = (
                self._db.collection(collection)
                .order_by(order_by, direction=firestore.Query.DESCENDING)
                .limit(1)
            )
            for doc in query.stream():
                return doc.to_dict()
            return None
        except Exception as exc:
            raise DataSourceError(f"Firestore get_latest failed: {exc}") from exc
