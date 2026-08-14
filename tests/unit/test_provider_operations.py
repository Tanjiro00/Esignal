from datetime import UTC, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import Base, ProviderFetch, RawPayloadLink
from apps.api.provider_operations import (
    SqlAlchemyProviderFetchRecorder,
    deterministic_request_fingerprint,
)
from packages.domain import ProviderRequest


def test_request_fingerprint_is_independent_of_parameter_order() -> None:
    first = ProviderRequest(
        provider="fixture",
        capability="discovery",
        endpoint="search",
        parameters={"query": "agents", "country": "US"},
        parser_version="v1",
    )
    second = ProviderRequest(
        provider="fixture",
        capability="discovery",
        endpoint="search",
        parameters={"country": "US", "query": "agents"},
        parser_version="v1",
    )
    assert deterministic_request_fingerprint(first) == deterministic_request_fingerprint(second)


def test_raw_payload_links_are_idempotent(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            ProviderFetch(
                id="fetch-1",
                provider="fixture",
                capability="metadata",
                endpoint="videos",
                request_fingerprint="f" * 64,
                started_at=now,
                completed_at=now,
                status="success",
                http_status=200,
                attempt_number=1,
                latency_ms=1,
                estimated_cost=0,
                actual_cost=0,
                raw_payload_uri="fixture.json",
                raw_payload_hash="h" * 64,
                parser_version="v1",
                error_code=None,
                error_message=None,
                linked_entity_ids=[],
            )
        )
        session.commit()
        recorder = SqlAlchemyProviderFetchRecorder(
            session,
            Settings(raw_payload_directory=str(tmp_path / "raw")),
        )
        recorder.link_entities(
            "fetch-1",
            entity_type="normalized_entity",
            entity_ids=["video-1", "video-1"],
        )
        assert session.scalar(select(func.count(RawPayloadLink.provider_fetch_id))) == 1
