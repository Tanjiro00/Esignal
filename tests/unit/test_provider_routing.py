import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    Base,
    ProviderBudget,
    ProviderHealth,
    ProviderRoutingDecision,
)
from apps.api.provider_operations import SqlAlchemyProviderRoutingPolicy
from packages.domain import DiscoveredVideo, DiscoveryQuery
from packages.provider_sdk.router import (
    ProviderRouter,
    RouteAttempt,
    SkippedProvider,
)


class FixtureProvider:
    def __init__(
        self,
        name: str,
        *,
        failures: Sequence[str] = (),
    ) -> None:
        self.name = name
        self.failures = list(failures)
        self.calls = 0

    async def search(self, query: DiscoveryQuery) -> list[DiscoveredVideo]:
        self.calls += 1
        if self.failures:
            reason = self.failures.pop(0)

            class FixtureError(RuntimeError):
                pass

            error = FixtureError(reason)
            error.reason = reason  # type: ignore[attr-defined]
            raise error
        return [
            DiscoveredVideo(
                video_id=f"{self.name}-video",
                title=query.query,
                channel_id=f"{self.name}-channel",
                channel_title=self.name,
                published_at=datetime.now(tz=UTC),
                position=1,
                query=query.query,
                raw_ref=f"fixture://{self.name}",
            )
        ]


class CapturingPolicy:
    def __init__(self) -> None:
        self.decision: dict[str, Any] | None = None

    def rank(self, capability: str, providers: Sequence[str]) -> Any:
        from packages.provider_sdk.router import RoutePlan

        assert capability == "discovery"
        return RoutePlan(tuple(providers))

    def record_decision(self, **kwargs: Any) -> None:
        self.decision = kwargs


def test_router_retries_transient_failure_then_falls_back() -> None:
    async def run() -> None:
        preferred = FixtureProvider(
            "preferred",
            failures=("network_error", "network_error"),
        )
        fallback = FixtureProvider("fallback")
        policy = CapturingPolicy()

        async def no_sleep(delay: float) -> None:
            assert delay >= 0

        router = ProviderRouter(
            discovery=[preferred, fallback],
            metadata=[],
            comments=[],
            transcripts=[],
            policy=policy,
            retry_attempts=2,
            sleep=no_sleep,
            jitter=lambda: 0,
        )
        result = await router.discover(DiscoveryQuery(query="AI agent benchmark"))

        assert result[0].video_id == "fallback-video"
        assert preferred.calls == 2
        assert fallback.calls == 1
        assert policy.decision is not None
        assert policy.decision["selected_provider"] == "fallback"
        assert policy.decision["reason"] == "fallback_success"

    asyncio.run(run())


def _health(
    provider: str,
    *,
    priority: int,
    enabled: bool = True,
    circuit_state: str = "closed",
    opened_at: datetime | None = None,
) -> ProviderHealth:
    now = datetime.now(tz=UTC)
    return ProviderHealth(
        provider=provider,
        capability="discovery",
        enabled=enabled,
        priority=priority,
        window_started_at=now,
        request_count=0,
        success_count=0,
        error_count=0,
        p50_latency_ms=0,
        p95_latency_ms=0,
        estimated_cost=0,
        circuit_state=circuit_state,
        consecutive_failures=0,
        circuit_opened_at=opened_at,
        half_open_probe_at=None,
        manual_disabled_at=None,
        disabled_reason=None,
        last_error=None,
        updated_at=now,
    )


def _budget(provider: str, *, spent: float = 0) -> ProviderBudget:
    now = datetime.now(tz=UTC)
    return ProviderBudget(
        provider=provider,
        capability="discovery",
        daily_limit_usd=10,
        monthly_limit_usd=100,
        spent_today_usd=spent,
        spent_month_usd=spent,
        day_started_at=now,
        month_started_at=now,
        updated_at=now,
    )


def test_sql_policy_skips_disabled_open_circuit_and_exhausted_budget() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        now = datetime.now(tz=UTC)
        session.add_all(
            [
                _health("disabled", priority=1, enabled=False),
                _health(
                    "open",
                    priority=2,
                    circuit_state="open",
                    opened_at=now,
                ),
                _health("exhausted", priority=3),
                _health("fallback", priority=4),
                _budget("disabled"),
                _budget("open"),
                _budget("exhausted", spent=10),
                _budget("fallback"),
            ]
        )
        session.commit()
        policy = SqlAlchemyProviderRoutingPolicy(
            session,
            Settings(provider_circuit_cooldown_seconds=300),
        )

        plan = policy.rank(
            "discovery",
            ("disabled", "open", "exhausted", "fallback"),
        )

        assert plan.providers == ("fallback",)
        assert {(item.provider, item.reason) for item in plan.skipped} == {
            ("disabled", "manual_disabled"),
            ("open", "circuit_open"),
            ("exhausted", "daily_budget_exhausted"),
        }

        policy.record_decision(
            capability="discovery",
            operation_key="search:fixture",
            selected_provider="fallback",
            attempts=(RouteAttempt("fallback", 1, "success", "ok", 12),),
            skipped=(SkippedProvider("disabled", "manual_disabled"),),
            status="success",
            reason="ok",
        )
        decision = session.scalar(select(ProviderRoutingDecision))
        assert decision is not None
        assert decision.fallback_used is True


def test_open_circuit_becomes_half_open_after_cooldown() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            _health(
                "probe",
                priority=1,
                circuit_state="open",
                opened_at=datetime.now(tz=UTC) - timedelta(minutes=10),
            )
        )
        session.add(_budget("probe"))
        session.commit()

        plan = SqlAlchemyProviderRoutingPolicy(
            session,
            Settings(provider_circuit_cooldown_seconds=60),
        ).rank("discovery", ("probe",))

        assert plan.providers == ("probe",)
        health = session.get(ProviderHealth, ("probe", "discovery"))
        assert health is not None
        assert health.circuit_state == "half_open"
