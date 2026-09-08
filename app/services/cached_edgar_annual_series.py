"""Firestore-Cache für die EDGAR-Jahresreihen, geschlüsselt nach CIK.

Warum überhaupt: ein kalter Durchlauf über die US-Titel dauert gemessen 6,8
Minuten und liegt damit auf einem ~23-Minuten-Monatslauf gegen eine harte
1800-s-Scheduler-Deadline (Spec §9.3). Jahresdaten ändern sich einmal im Jahr —
im Regelfall soll ein Monatslauf **keinen einzigen** companyfacts-Request
machen.

Drei Entscheidungen, die hier drinstecken:

**Schlüssel ist die CIK, nicht der Ticker.** GOOG und GOOGL sind derselbe
Emittent; über den Ticker geschlüsselt läge dieselbe Reihe zweimal im Speicher
und würde zweimal geladen.

**Die Ablaufzeit wird beim Schreiben gewürfelt und mitgespeichert**, nicht bei
jedem Lesen neu. Ein Backfill schreibt alle Einträge an einem Tag; ohne Jitter
laufen sie auch an einem Tag ab, und genau ein Monatslauf trägt dann die vollen
sieben Minuten Nachladen. ±60 Tage verteilen das über ein Vierteljahr. Bei
jedem Lesen neu zu würfeln wäre schlimmer als kein Jitter: derselbe Eintrag
wäre mal frisch und mal abgelaufen.

**Negativergebnisse werden gecacht, aber kürzer und ohne Jitter.** Ohne das
laden rund 90 Titel jeden Monat ihr mehrere MB großes Dokument, um erneut
festzustellen, dass nichts Verwertbares drinsteht. Kürzer, weil ein
Negativergebnis eine Aussage über heute ist, nicht über das Unternehmen — ein
Emittent kann anfangen, ein Konzept zu taggen. Ohne Jitter, weil eine
60-Tage-TTL mit ±60 Tagen Streuung auf null fallen könnte.

Ein **transienter** Fehler wird nicht gecacht und nicht verschluckt: er ist eine
Aussage über die API, nicht über den Titel, und fliegt weiter.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from app.errors import DataSourceError
from app.services.edgar_annual_series_client import (
    EXTRACTION_SCHEMA,
    NO_CONCEPT,
    AnnualSeriesRecord,
    record_from_dict,
    record_to_dict,
)

if TYPE_CHECKING:
    from app.services.edgar_annual_series_client import EdgarAnnualSeriesClient
    from app.services.firestore_client import FirestoreClient

_EXPIRES_AT = "_expires_at"


class CachedEdgarAnnualSeries:
    def __init__(
        self,
        client: "EdgarAnnualSeriesClient",
        firestore: "FirestoreClient",
        collection: str,
        *,
        ttl_days: int = 400,
        ttl_jitter_days: int = 60,
        negative_ttl_days: int = 60,
        rng: random.Random | None = None,
        now: Any = None,
    ) -> None:
        self._client = client
        self._firestore = firestore
        self._collection = collection
        self._ttl_days = ttl_days
        self._jitter_days = ttl_jitter_days
        self._negative_ttl_days = negative_ttl_days
        self._rng = rng if rng is not None else random.Random()
        self._now = now if now is not None else (lambda: datetime.now(timezone.utc))

    def get_annual_series(self, cik: str) -> AnnualSeriesRecord:
        key = cik.zfill(10)
        cached = self._firestore.get(self._collection, key)
        if cached is not None and self._is_usable(cached):
            return record_from_dict(cached)

        try:
            record = self._client.get_annual_series(key)
        except DataSourceError as exc:
            if "404" not in str(exc):
                raise  # Aussage ueber die API, nicht ueber den Titel
            # Kein XBRL-Bestand bei diesem Emittenten -- das ist eine Aussage
            # ueber den Titel und wird als Negativergebnis gehalten.
            record = AnnualSeriesRecord(
                cik=key, entity="", concepts={}, reason=NO_CONCEPT
            )

        payload = record_to_dict(record)
        payload[_EXPIRES_AT] = self._expiry(record).isoformat()
        self._firestore.set(self._collection, key, payload)
        return record

    def _expiry(self, record: AnnualSeriesRecord) -> datetime:
        if not record.usable:
            return self._now() + timedelta(days=self._negative_ttl_days)
        offset = self._rng.uniform(-self._jitter_days, self._jitter_days)
        return self._now() + timedelta(days=self._ttl_days + offset)

    def _is_usable(self, cached: dict[str, Any]) -> bool:
        """Frisch UND von derselben Extraktion erzeugt.

        Die Schema-Pruefung ist der wichtigere der beiden Arme: ein Extrakt aus
        einer aelteren Extraktion sieht gueltig aus und traegt trotzdem falsche
        Reihen. Ein warmer Cache, der eine Verhaltensaenderung verdeckt, hat in
        diesem Projekt schon einmal eine Verifikation wertlos gemacht."""
        if cached.get("schema") != EXTRACTION_SCHEMA:
            return False
        raw = cached.get(_EXPIRES_AT)
        if not raw:
            return False
        try:
            expires = datetime.fromisoformat(str(raw))
        except ValueError:
            return False
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return self._now() < expires
