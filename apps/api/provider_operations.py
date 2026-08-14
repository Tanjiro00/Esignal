from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import (
    ProviderBudget,
    ProviderFetch,
    ProviderHealth,
    ProviderOperationsEvent,
    ProviderRoutingDecision,
    RawPayloadLink,
)
from packages.domain import ProviderRequest, RecordedPayload
from packages.provider_sdk.router.policy import (
    ProviderRoutingPolicy,
    RouteAttempt,
    RoutePlan,
    SkippedProvider,
)
from packages.provider_sdk.storage import LocalRawPayloadStore

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def deterministic_request_fingerprint(request: ProviderRequest) -> str:
    canonical = json.dumps(
        {
            "provider": request.provider,
            "capability": request.capability,
            "endpoint": request.endpoint,
            "parameters": request.parameters,
            "parser_version": request.parser_version,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )
    return sha256(canonical.encode()).hexdigest()


class SqlAlchemyProviderFetchRecorder:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings
        self._store = LocalRawPayloadStore(
            repository_root=REPOSITORY_ROOT,
            storage_root=REPOSITORY_ROOT / settings.raw_payload_directory,
        )

    def record_success(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
    ) -> RecordedPayload:
        return self._record(
            request,
            payload=payload,
            started_at=started_at,
            completed_at=completed_at,
            http_status=http_status,
            status="success",
            error_code=None,
            error_message=None,
        )

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
    ) -> RecordedPayload:
        return self._record(
            request,
            payload=payload,
            started_at=started_at,
            completed_at=completed_at,
            http_status=http_status,
            status="failed",
            error_code=error_code,
            error_message=error_message[:1000],
        )

    def _record(
        self,
        request: ProviderRequest,
        *,
        payload: dict[str, Any],
        started_at: datetime,
        completed_at: datetime,
        http_status: int,
        status: str,
        error_code: str | None,
        error_message: str | None,
    ) -> RecordedPayload:
        stored = self._store.write(
            payload,
            provider=request.provider,
            capability=request.capability,
            observed_at=completed_at,
        )
        fetch_id = str(uuid4())
        latency_ms = max(0, round((completed_at - started_at).total_seconds() * 1000))
        row = ProviderFetch(
            id=fetch_id,
            provider=request.provider,
            capability=request.capability,
            endpoint=request.endpoint,
            request_fingerprint=deterministic_request_fingerprint(request),
            started_at=started_at,
            completed_at=completed_at,
            status=status,
            http_status=http_status,
            attempt_number=1,
            latency_ms=latency_ms,
            estimated_cost=request.estimated_cost,
            actual_cost=request.estimated_cost,
            raw_payload_uri=stored.uri,
            raw_payload_hash=stored.content_hash,
            parser_version=request.parser_version,
            error_code=error_code,
            error_message=error_message,
            linked_entity_ids=[],
        )
        self._session.add(row)
        self._session.flush()
        self._update_health(request, status=status, latency_ms=latency_ms, error=error_message)
        self._update_budget(request)
        # The evidence is durable before any adapter turns it into domain records.
        self._session.commit()
        return RecordedPayload(
            fetch_id=fetch_id,
            raw_ref=f"fetch://{fetch_id}",
            payload_hash=stored.content_hash,
        )

    def _update_health(
        self,
        request: ProviderRequest,
        *,
        status: str,
        latency_ms: int,
        error: str | None,
    ) -> None:
        now = datetime.now(tz=UTC)
        row = self._session.get(ProviderHealth, (request.provider, request.capability))
        if row is None:
            row = ProviderHealth(
                provider=request.provider,
                capability=request.capability,
                enabled=True,
                priority=1,
                window_started_at=now,
                request_count=0,
                success_count=0,
                error_count=0,
                p50_latency_ms=latency_ms,
                p95_latency_ms=latency_ms,
                estimated_cost=0,
                circuit_state="closed",
                consecutive_failures=0,
                circuit_opened_at=None,
                half_open_probe_at=None,
                manual_disabled_at=None,
                disabled_reason=None,
                last_error=None,
                updated_at=now,
            )
            self._session.add(row)
        row.request_count += 1
        if status == "success":
            row.success_count += 1
            row.consecutive_failures = 0
            if row.circuit_state == "half_open":
                row.circuit_state = "closed"
                row.circuit_opened_at = None
                row.half_open_probe_at = None
        else:
            row.error_count += 1
            row.consecutive_failures += 1
        row.p50_latency_ms = round((row.p50_latency_ms + latency_ms) / 2)
        row.p95_latency_ms = max(row.p95_latency_ms, latency_ms)
        row.estimated_cost += request.estimated_cost
        if error:
            row.last_error = error
        row.updated_at = now
        if status != "failed":
            return

        recent = list(
            self._session.scalars(
                select(ProviderFetch)
                .where(
                    ProviderFetch.provider == request.provider,
                    ProviderFetch.capability == request.capability,
                )
                .order_by(desc(ProviderFetch.completed_at))
                .limit(self._settings.provider_circuit_window_size)
            )
        )
        recent_failures = sum(item.status == "failed" for item in recent)
        enough_for_rate = len(recent) >= self._settings.provider_circuit_window_size
        failure_rate = recent_failures / len(recent) if recent else 0
        cutoff = now - timedelta(minutes=15)
        recent_latencies = sorted(
            item.latency_ms for item in recent if _aware(item.completed_at) >= cutoff
        )
        p95_index = max(0, round(0.95 * len(recent_latencies)) - 1)
        emergency_p95 = recent_latencies[p95_index] if recent_latencies else 0
        should_open = (
            row.consecutive_failures >= self._settings.provider_circuit_failure_threshold
            or (enough_for_rate and failure_rate >= self._settings.provider_circuit_failure_rate)
            or emergency_p95 >= self._settings.provider_emergency_latency_ms
        )
        if should_open and row.circuit_state != "open":
            row.circuit_state = "open"
            row.circuit_opened_at = now
            row.half_open_probe_at = None
            self._session.add(
                ProviderOperationsEvent(
                    id=str(uuid4()),
                    event_type="circuit_opened",
                    severity="warning",
                    capability=request.capability,
                    provider=request.provider,
                    message=f"Circuit opened for {request.provider}/{request.capability}",
                    context_json={
                        "consecutive_failures": row.consecutive_failures,
                        "window_size": len(recent),
                        "failure_rate": round(failure_rate, 4),
                        "p95_latency_ms_15m": emergency_p95,
                    },
                    created_at=now,
                )
            )

    def _update_budget(self, request: ProviderRequest) -> None:
        now = datetime.now(tz=UTC)
        row = self._session.get(ProviderBudget, (request.provider, request.capability))
        if row is None:
            row = ProviderBudget(
                provider=request.provider,
                capability=request.capability,
                daily_limit_usd=self._settings.provider_daily_budget_usd,
                monthly_limit_usd=self._settings.provider_monthly_budget_usd,
                spent_today_usd=0,
                spent_month_usd=0,
                day_started_at=now,
                month_started_at=now,
                updated_at=now,
            )
            self._session.add(row)
        if _aware(row.day_started_at).date() != now.date():
            row.spent_today_usd = 0
            row.day_started_at = now
        month_changed = (
            _aware(row.month_started_at).year,
            _aware(row.month_started_at).month,
        ) != (now.year, now.month)
        if month_changed:
            row.spent_month_usd = 0
            row.month_started_at = now
        row.spent_today_usd += request.estimated_cost
        row.spent_month_usd += request.estimated_cost
        row.updated_at = now

    def link_entities(
        self,
        fetch_id: str,
        *,
        entity_type: str,
        entity_ids: list[str],
    ) -> None:
        fetch = self._session.get(ProviderFetch, fetch_id)
        if fetch is None:
            raise RuntimeError(f"Unknown provider fetch: {fetch_id}")
        fetch.linked_entity_ids = sorted(set(fetch.linked_entity_ids + entity_ids))
        for entity_id in set(entity_ids):
            key = (fetch_id, entity_type, entity_id)
            if self._session.get(RawPayloadLink, key) is None:
                self._session.add(
                    RawPayloadLink(
                        provider_fetch_id=fetch_id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                    )
                )
        self._session.commit()

    def mark_parse_failure(
        self,
        fetch_id: str,
        *,
        error_code: str,
        error_message: str,
    ) -> None:
        fetch = self._session.get(ProviderFetch, fetch_id)
        if fetch is None:
            raise RuntimeError(f"Unknown provider fetch: {fetch_id}")
        fetch.status = "failed"
        fetch.error_code = error_code
        fetch.error_message = error_message[:1000]
        self._session.commit()


class SqlAlchemyProviderRoutingPolicy(ProviderRoutingPolicy):
    """Ranks configured adapters using persisted controls and operational state."""

    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._settings = settings

    def rank(self, capability: str, providers: Sequence[str]) -> RoutePlan:
        now = datetime.now(tz=UTC)
        ranked: list[tuple[int, int, str]] = []
        skipped: list[SkippedProvider] = []
        changed = False
        configured = tuple(dict.fromkeys(providers))
        existing_health = [
            self._session.get(ProviderHealth, (provider, capability)) for provider in configured
        ]
        if (
            len(existing_health) > 1
            and all(row is not None for row in existing_health)
            and len({row.priority for row in existing_health if row is not None}) == 1
        ):
            for configured_index, row in enumerate(existing_health):
                if row is not None:
                    row.priority = configured_index + 1
                    row.updated_at = now
            changed = True
        for configured_index, provider in enumerate(configured):
            health = self._session.get(ProviderHealth, (provider, capability))
            if health is None:
                health = ProviderHealth(
                    provider=provider,
                    capability=capability,
                    enabled=True,
                    priority=configured_index + 1,
                    window_started_at=now,
                    request_count=0,
                    success_count=0,
                    error_count=0,
                    p50_latency_ms=0,
                    p95_latency_ms=0,
                    estimated_cost=0,
                    circuit_state="closed",
                    consecutive_failures=0,
                    circuit_opened_at=None,
                    half_open_probe_at=None,
                    manual_disabled_at=None,
                    disabled_reason=None,
                    last_error=None,
                    updated_at=now,
                )
                self._session.add(health)
                changed = True
            budget = self._session.get(ProviderBudget, (provider, capability))
            if budget is None:
                budget = ProviderBudget(
                    provider=provider,
                    capability=capability,
                    daily_limit_usd=self._settings.provider_daily_budget_usd,
                    monthly_limit_usd=self._settings.provider_monthly_budget_usd,
                    spent_today_usd=0,
                    spent_month_usd=0,
                    day_started_at=now,
                    month_started_at=now,
                    updated_at=now,
                )
                self._session.add(budget)
                changed = True
            changed = self._reset_budget_periods(budget, now) or changed

            if not health.enabled:
                skipped.append(SkippedProvider(provider, "manual_disabled"))
                continue
            if health.circuit_state == "open":
                opened_at = _aware(health.circuit_opened_at or health.updated_at)
                if (now - opened_at).total_seconds() < (
                    self._settings.provider_circuit_cooldown_seconds
                ):
                    skipped.append(SkippedProvider(provider, "circuit_open"))
                    continue
                health.circuit_state = "half_open"
                health.half_open_probe_at = now
                health.updated_at = now
                changed = True
            elif health.circuit_state == "half_open":
                probe_at = _aware(health.half_open_probe_at or health.updated_at)
                if (now - probe_at).total_seconds() < (
                    self._settings.provider_circuit_cooldown_seconds
                ):
                    skipped.append(SkippedProvider(provider, "half_open_probe_in_progress"))
                    continue
                health.half_open_probe_at = now
                changed = True

            daily_exhausted = (
                budget.daily_limit_usd > 0 and budget.spent_today_usd >= budget.daily_limit_usd
            )
            monthly_exhausted = (
                budget.monthly_limit_usd > 0 and budget.spent_month_usd >= budget.monthly_limit_usd
            )
            if daily_exhausted or monthly_exhausted:
                skipped.append(
                    SkippedProvider(
                        provider,
                        "daily_budget_exhausted" if daily_exhausted else "monthly_budget_exhausted",
                    )
                )
                continue
            daily_ratio = (
                budget.spent_today_usd / budget.daily_limit_usd if budget.daily_limit_usd > 0 else 0
            )
            monthly_ratio = (
                budget.spent_month_usd / budget.monthly_limit_usd
                if budget.monthly_limit_usd > 0
                else 0
            )
            budget_penalty = 1000 if max(daily_ratio, monthly_ratio) >= 0.8 else 0
            ranked.append((health.priority + budget_penalty, configured_index, provider))
        if changed:
            self._session.commit()
        return RoutePlan(
            providers=tuple(item[2] for item in sorted(ranked)),
            skipped=tuple(skipped),
        )

    def record_decision(
        self,
        *,
        capability: str,
        operation_key: str,
        selected_provider: str | None,
        attempts: Sequence[RouteAttempt],
        skipped: Sequence[SkippedProvider],
        status: str,
        reason: str,
    ) -> None:
        attempted_providers = list(dict.fromkeys(attempt.provider for attempt in attempts))
        fallback_used = bool(
            selected_provider
            and (
                len(attempted_providers) > 1
                or (attempted_providers and selected_provider != attempted_providers[0])
                or bool(skipped)
            )
        )
        self._session.add(
            ProviderRoutingDecision(
                id=str(uuid4()),
                capability=capability,
                operation_key=operation_key,
                selected_provider=selected_provider,
                attempted_providers_json=[
                    {
                        "provider": attempt.provider,
                        "attempt": attempt.attempt,
                        "status": attempt.status,
                        "reason": attempt.reason,
                        "latency_ms": attempt.latency_ms,
                    }
                    for attempt in attempts
                ],
                skipped_providers_json=[
                    {"provider": item.provider, "reason": item.reason} for item in skipped
                ],
                fallback_used=fallback_used,
                status=status,
                reason=reason,
                estimated_cost=0,
                created_at=datetime.now(tz=UTC),
            )
        )
        if status == "failed":
            self._session.add(
                ProviderOperationsEvent(
                    id=str(uuid4()),
                    event_type="all_providers_failed",
                    severity="error",
                    capability=capability,
                    provider=None,
                    message=f"All eligible {capability} providers failed",
                    context_json={
                        "operation_key": operation_key,
                        "attempts": [
                            {
                                "provider": item.provider,
                                "attempt": item.attempt,
                                "reason": item.reason,
                            }
                            for item in attempts
                        ],
                        "skipped": [
                            {"provider": item.provider, "reason": item.reason} for item in skipped
                        ],
                    },
                    created_at=datetime.now(tz=UTC),
                )
            )
        self._session.commit()

    @staticmethod
    def _reset_budget_periods(row: ProviderBudget, now: datetime) -> bool:
        changed = False
        if _aware(row.day_started_at).date() != now.date():
            row.spent_today_usd = 0
            row.day_started_at = now
            changed = True
        month_changed = (
            _aware(row.month_started_at).year,
            _aware(row.month_started_at).month,
        ) != (now.year, now.month)
        if month_changed:
            row.spent_month_usd = 0
            row.month_started_at = now
            changed = True
        if changed:
            row.updated_at = now
        return changed
