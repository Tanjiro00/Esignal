from datetime import datetime
from typing import Any, Protocol

from packages.domain import ProviderRequest, RecordedPayload


class ProviderFetchRecorder(Protocol):
    """Persists provider evidence before an adapter normalizes it."""

    def record_success(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
    ) -> RecordedPayload: ...

    def record_failure(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
        error_code: str,
        error_message: str,
    ) -> RecordedPayload: ...

    def link_entities(
        self,
        fetch_id: str,
        *,
        entity_type: str,
        entity_ids: list[str],
    ) -> None: ...

    def mark_parse_failure(
        self,
        fetch_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None: ...
