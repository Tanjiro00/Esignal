from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class SkippedProvider:
    provider: str
    reason: str


@dataclass(frozen=True)
class RoutePlan:
    providers: tuple[str, ...]
    skipped: tuple[SkippedProvider, ...] = ()


@dataclass(frozen=True)
class RouteAttempt:
    provider: str
    attempt: int
    status: str
    reason: str
    latency_ms: int


class ProviderRoutingPolicy(Protocol):
    """Persistence-aware policy boundary used by the provider-agnostic router."""

    def rank(self, capability: str, providers: Sequence[str]) -> RoutePlan: ...

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
    ) -> None: ...


class OrderedProviderRoutingPolicy:
    """Default policy for tests and callers that do not need persistence."""

    def rank(self, capability: str, providers: Sequence[str]) -> RoutePlan:
        del capability
        return RoutePlan(tuple(providers))

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
        del (
            capability,
            operation_key,
            selected_provider,
            attempts,
            skipped,
            status,
            reason,
        )
