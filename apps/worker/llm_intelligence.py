from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import TypeVar, cast
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import LLMIntelligenceRun
from packages.llm_intelligence import (
    ChannelDiscoveryPlan,
    ContentGapSynthesis,
    EvidenceInsight,
    EvidenceInsightSynthesis,
    EvidenceItem,
    GroundingAudit,
    InsightReleaseAudit,
    LLMProvider,
    LLMProviderError,
    OpenAIResponsesProvider,
    ShadowEvidenceDossier,
    ShadowTrendAudit,
    ShadowTrendTaxonomy,
    TopicCandidate,
    TopicReconciliation,
    TopicSynthesis,
)

RECONCILIATION_PROMPT_VERSION = "topic-reconciliation-v3-neutral-labels"
TOPIC_SYNTHESIS_PROMPT_VERSION = "topic-evidence-synthesis-v2-neutral-labels"
CONTENT_GAP_PROMPT_VERSION = "content-gap-evidence-synthesis-v2-format-neutral"
EVIDENCE_INSIGHT_PROMPT_VERSION = "evidence-insight-v1-subject-neutral"
GROUNDING_AUDIT_PROMPT_VERSION = "grounding-audit-v1"
INSIGHT_RELEASE_AUDIT_PROMPT_VERSION = "insight-release-audit-v1"
SHADOW_EVIDENCE_ANALYSIS_PROMPT_VERSION = "shadow-evidence-analysis-v1"
SHADOW_TREND_TAXONOMY_PROMPT_VERSION = "shadow-trend-taxonomy-v1"
SHADOW_TREND_AUDIT_PROMPT_VERSION = "shadow-trend-skeptic-audit-v1"
CHANNEL_DISCOVERY_PROMPT_VERSION = "channel-discovery-plan-v1"
LLM_POLICY_VERSION = "evidence-decision-graph-v1"

_GENERIC_LABELS = {
    "ai agents",
    "ai models",
    "ai tools",
    "ai trends",
    "new ai",
    "new ai models",
    "new ai tools",
    "technology trends",
}

_FORMAT_BIASED_PHRASES = (
    "tutorial",
    "how to",
    "how-to",
    "explainer",
    "breakdown",
    "deep dive",
    "reaction video",
    "video essay",
    "documentary",
    "podcast episode",
    "i tested",
    "i audited",
    "we tested",
)

_FORMAT_DIRECTIVE_PREFIXES = (
    "audit ",
    "compare ",
    "explain ",
    "review ",
    "test ",
    "walk through ",
)

T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class StoredLLMResult:
    value: BaseModel
    run_id: str
    provider: str
    model: str
    prompt_version: str
    cached: bool


def _canonical_payload(value: dict[str, object]) -> tuple[str, str]:
    rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return rendered, sha256(rendered.encode()).hexdigest()


def _clean_label(value: str) -> str:
    return " ".join(value.strip().split())


def _label_errors(label: str) -> list[str]:
    normalized = _clean_label(label)
    words = normalized.split()
    errors: list[str] = []
    if normalized.lower() in _GENERIC_LABELS:
        errors.append("generic_label")
    if len(words) < 3:
        errors.append("label_too_short")
    if len(words) > 16:
        errors.append("label_too_long")
    if any(phrase in normalized.lower() for phrase in _FORMAT_BIASED_PHRASES):
        errors.append("format_biased_label")
    return errors


def _format_bias_errors(value: str, *, target: str) -> list[str]:
    normalized = _clean_label(value).lower()
    biased = any(phrase in normalized for phrase in _FORMAT_BIASED_PHRASES) or any(
        normalized.startswith(prefix) for prefix in _FORMAT_DIRECTIVE_PREFIXES
    )
    return [f"format_biased_{target}"] if biased else []


def _reference_errors(references: list[str], allowed: set[str]) -> list[str]:
    invalid = sorted(set(references) - allowed)
    return [f"unknown_evidence_ref:{reference}" for reference in invalid]


def _independent_reference_errors(
    references: list[str],
    evidence_metadata: dict[str, dict[str, str]],
) -> list[str]:
    unique = set(references)
    channels = {
        evidence_metadata[reference].get("channel_id", "")
        for reference in unique
        if reference in evidence_metadata
    }
    families = {
        evidence_metadata[reference].get("title_family", "")
        for reference in unique
        if reference in evidence_metadata
    }
    errors: list[str] = []
    if len(unique) < 2:
        errors.append("requires_multiple_evidence_refs")
    if len(channels - {""}) < 2:
        errors.append("requires_independent_channels")
    if len(families - {""}) < 2:
        errors.append("requires_independent_title_families")
    return errors


class LLMIntelligenceService:
    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        provider: LLMProvider | None = None,
        auditor_provider: LLMProvider | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        configured_key = settings.openai_api_key.get_secret_value()
        self._provider = provider
        if (
            self._provider is None
            and settings.feature_llm_intelligence
            and settings.llm_provider == "openai"
            and configured_key
        ):
            self._provider = OpenAIResponsesProvider(
                api_key=configured_key,
                model=settings.openai_model,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.openai_request_timeout_seconds,
                reasoning_effort=settings.openai_reasoning_effort,
                max_output_tokens=settings.openai_max_output_tokens,
                retry_attempts=settings.openai_retry_attempts,
            )
        self._auditor_provider = auditor_provider
        if self._auditor_provider is None and provider is not None:
            self._auditor_provider = provider
        if (
            self._auditor_provider is None
            and settings.feature_llm_intelligence
            and settings.llm_require_grounding_audit
            and settings.llm_provider == "openai"
            and configured_key
        ):
            self._auditor_provider = OpenAIResponsesProvider(
                api_key=configured_key,
                model=settings.openai_auditor_model,
                base_url=settings.openai_base_url,
                timeout_seconds=settings.openai_request_timeout_seconds,
                reasoning_effort=settings.openai_auditor_reasoning_effort,
                max_output_tokens=settings.openai_max_output_tokens,
                retry_attempts=settings.openai_retry_attempts,
            )
        self._enabled = settings.feature_llm_intelligence and self._provider is not None
        self._calls = 0
        self._task_calls: Counter[str] = Counter()
        self._consecutive_failures = 0
        self._trace_id: str | None = None
        self._trace_events: list[dict[str, object]] = []
        self._stale_runs_reconciled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def configured(self) -> bool:
        return self._provider is not None

    @property
    def audit_configured(self) -> bool:
        return self._auditor_provider is not None

    def start_trace(self, workflow_run_id: str) -> None:
        self._trace_id = workflow_run_id
        self._trace_events = []
        self._calls = 0
        self._task_calls = Counter()
        self._consecutive_failures = 0

    def record_gate(
        self,
        *,
        stage: str,
        scope_id: str,
        decision: str,
        reason: str,
        parent_run_id: str | None = None,
    ) -> None:
        self._trace_events.append(
            {
                "kind": "gate",
                "stage": stage,
                "scope_id": scope_id,
                "decision": decision,
                "reason": reason,
                "parent_run_id": parent_run_id,
            }
        )

    def trace_summary(self) -> dict[str, object]:
        decisions = Counter(
            str(event.get("decision", event.get("status", "unknown")))
            for event in self._trace_events
        )
        return {
            "policy_version": LLM_POLICY_VERSION,
            "workflow_run_id": self._trace_id,
            "enabled": self.enabled,
            "audit_required": self._settings.llm_require_grounding_audit,
            "provider_calls": self._calls,
            "task_calls": dict(self._task_calls),
            "decisions": dict(decisions),
            "circuit_open": (
                self._consecutive_failures >= self._settings.llm_circuit_failure_threshold
            ),
            "events": list(self._trace_events),
        }

    def _task_limit(self, task: str) -> int | None:
        if task == "topic-reconciliation":
            return self._settings.llm_max_reconciliations_per_run
        if task in {
            "topic-synthesis",
            "shadow-evidence-analysis",
            "shadow-trend-taxonomy",
        }:
            return self._settings.llm_max_topic_syntheses_per_run
        if task in {"content-gap-synthesis", "evidence-insight-synthesis"}:
            return self._settings.llm_max_content_gap_syntheses_per_run
        if self._is_audit_task(task):
            return self._settings.llm_max_audits_per_run
        return None

    def _task_budget_used(self, task: str) -> int:
        if task == "grounding-audit" or self._is_audit_task(task):
            return sum(
                count
                for task_name, count in self._task_calls.items()
                if self._is_audit_task(task_name)
            )
        return self._task_calls[task]

    @staticmethod
    def _is_audit_task(task: str) -> bool:
        return task.endswith(("-grounding-audit", "-skeptic-audit"))

    @staticmethod
    def _workspace_scope(scope_kind: str, scope_id: str) -> str | None:
        if scope_kind == "workspace":
            return scope_id
        if scope_kind == "workspace-topic":
            return scope_id.split(":", 1)[0]
        return None

    @staticmethod
    def _daily_task_group(task: str) -> frozenset[str] | None:
        if task == "topic-reconciliation":
            return frozenset({"topic-reconciliation"})
        if task in {
            "topic-synthesis",
            "topic-grounding-audit",
            "shadow-evidence-analysis",
            "shadow-trend-taxonomy",
            "shadow-trend-skeptic-audit",
        }:
            return frozenset(
                {
                    "topic-synthesis",
                    "topic-grounding-audit",
                    "shadow-evidence-analysis",
                    "shadow-trend-taxonomy",
                    "shadow-trend-skeptic-audit",
                }
            )
        if task in {"content-gap-synthesis", "content-gap-grounding-audit"}:
            return frozenset({"content-gap-synthesis", "content-gap-grounding-audit"})
        return None

    def _daily_task_token_limit(self, task: str) -> int | None:
        if task == "topic-reconciliation":
            share = self._settings.llm_reconciliation_daily_token_share
        elif task in {
            "topic-synthesis",
            "topic-grounding-audit",
            "shadow-evidence-analysis",
            "shadow-trend-taxonomy",
            "shadow-trend-skeptic-audit",
        }:
            share = self._settings.llm_topic_synthesis_daily_token_share
        elif task in {"content-gap-synthesis", "content-gap-grounding-audit"}:
            share = self._settings.llm_content_gap_daily_token_share
        else:
            return None
        return max(0, round(self._settings.llm_daily_token_budget * share))

    def _daily_tokens_used(
        self,
        *,
        workspace_id: str | None = None,
        tasks: frozenset[str] | None = None,
    ) -> int:
        cutoff = datetime.now(tz=UTC) - timedelta(hours=24)
        query = select(LLMIntelligenceRun).where(
            LLMIntelligenceRun.created_at >= cutoff,
            LLMIntelligenceRun.status.in_(("success", "rejected")),
        )
        if workspace_id is not None:
            query = query.where(
                LLMIntelligenceRun.scope_kind.in_(("workspace", "workspace-topic")),
                (
                    (LLMIntelligenceRun.scope_id == workspace_id)
                    | LLMIntelligenceRun.scope_id.like(f"{workspace_id}:%")
                ),
            )
        if tasks is not None:
            query = query.where(LLMIntelligenceRun.task.in_(tasks))
        return sum(
            int(row.usage_json.get("total_tokens", 0) or 0) for row in self._session.scalars(query)
        )

    def reconcile_stale_runs(self, *, now: datetime | None = None) -> int:
        checked_at = now or datetime.now(tz=UTC)
        cutoff = checked_at - timedelta(minutes=max(1, self._settings.llm_stale_run_minutes))
        rows = list(
            self._session.scalars(
                select(LLMIntelligenceRun).where(
                    LLMIntelligenceRun.status == "running",
                    LLMIntelligenceRun.created_at < cutoff,
                )
            )
        )
        for row in rows:
            row.status = "failed"
            row.completed_at = checked_at
            row.error_code = "stale_run_recovered"
            row.error_message = (
                "The worker stopped before the provider call completed; the stale "
                "run was recovered automatically."
            )
        if rows:
            self._session.flush()
        self._stale_runs_reconciled = True
        return len(rows)

    def _release_path_budget_available(self, *, required_calls: int = 2) -> bool:
        if not self._settings.llm_require_grounding_audit:
            return True
        return (
            self._calls + required_calls <= self._settings.llm_max_calls_per_run
            and self._task_budget_used("grounding-audit") < self._settings.llm_max_audits_per_run
        )

    def _record_reserved_audit_budget_skip(
        self,
        *,
        task: str,
        role: str,
        scope_id: str,
    ) -> None:
        self._record_model_event(
            task=task,
            role=role,
            scope_id=scope_id,
            status="skipped_reserved_audit_budget",
            model=self._provider.model if self._provider is not None else "",
        )

    def _record_model_event(
        self,
        *,
        task: str,
        role: str,
        scope_id: str,
        status: str,
        model: str,
        run_id: str | None = None,
        cached: bool = False,
        parent_run_id: str | None = None,
        errors: list[str] | None = None,
    ) -> None:
        event: dict[str, object] = {
            "kind": "model_step",
            "task": task,
            "role": role,
            "scope_id": scope_id,
            "status": status,
            "model": model,
            "cached": cached,
        }
        if run_id is not None:
            event["run_id"] = run_id
        if parent_run_id is not None:
            event["parent_run_id"] = parent_run_id
        if errors:
            event["errors"] = errors
        self._trace_events.append(event)

    def _invoke(
        self,
        *,
        task: str,
        scope_kind: str,
        scope_id: str,
        prompt_version: str,
        developer_prompt: str,
        input_data: dict[str, object],
        evidence_refs: list[str],
        response_model: type[T],
        validate: Callable[[T], list[str]],
        role: str,
        provider: LLMProvider | None = None,
        parent_run_id: str | None = None,
    ) -> StoredLLMResult | None:
        selected_provider = provider or self._provider
        if not self._enabled or selected_provider is None:
            return None
        if not self._stale_runs_reconciled:
            self.reconcile_stale_runs()
        payload, input_hash = _canonical_payload(input_data)
        row = self._session.scalar(
            select(LLMIntelligenceRun)
            .where(
                LLMIntelligenceRun.task == task,
                LLMIntelligenceRun.scope_kind == scope_kind,
                LLMIntelligenceRun.scope_id == scope_id,
                LLMIntelligenceRun.input_hash == input_hash,
                LLMIntelligenceRun.prompt_version == prompt_version,
                LLMIntelligenceRun.model == selected_provider.model,
            )
            .order_by(desc(LLMIntelligenceRun.created_at))
            .limit(1)
        )
        if row is not None and row.status == "success":
            try:
                cached_value = response_model.model_validate(row.output_json)
            except ValueError:
                row.status = "rejected"
                row.validation_json = {"errors": ["cached_schema_validation"]}
            else:
                errors = validate(cached_value)
                if not errors:
                    self._record_model_event(
                        task=task,
                        role=role,
                        scope_id=scope_id,
                        status="success",
                        model=row.model,
                        run_id=row.id,
                        cached=True,
                        parent_run_id=parent_run_id,
                    )
                    return StoredLLMResult(
                        value=cached_value,
                        run_id=row.id,
                        provider=row.provider,
                        model=row.model,
                        prompt_version=row.prompt_version,
                        cached=True,
                    )
                row.status = "rejected"
                row.validation_json = {"errors": errors}
        task_limit = self._task_limit(task)
        if self._daily_tokens_used() >= self._settings.llm_daily_token_budget:
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_daily_token_budget",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        task_group = self._daily_task_group(task)
        task_token_limit = self._daily_task_token_limit(task)
        if (
            task_group is not None
            and task_token_limit is not None
            and self._daily_tokens_used(tasks=task_group) >= task_token_limit
        ):
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_task_daily_token_budget",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        workspace_id = self._workspace_scope(scope_kind, scope_id)
        if (
            workspace_id is not None
            and self._daily_tokens_used(workspace_id=workspace_id)
            >= self._settings.llm_workspace_daily_token_budget
        ):
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_workspace_daily_token_budget",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        if self._calls >= self._settings.llm_max_calls_per_run:
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_budget",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        if task_limit is not None and self._task_budget_used(task) >= task_limit:
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_task_budget",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        if self._consecutive_failures >= self._settings.llm_circuit_failure_threshold:
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="skipped_circuit_open",
                model=selected_provider.model,
                parent_run_id=parent_run_id,
            )
            return None
        now = datetime.now(tz=UTC)
        if row is None:
            row = LLMIntelligenceRun(
                id=str(uuid4()),
                task=task,
                scope_kind=scope_kind,
                scope_id=scope_id,
                input_hash=input_hash,
                provider=selected_provider.name,
                model=selected_provider.model,
                prompt_version=prompt_version,
                status="running",
                evidence_refs_json=list(dict.fromkeys(evidence_refs)),
                output_json={},
                validation_json={},
                usage_json={},
                provider_response_id=None,
                latency_ms=None,
                error_code=None,
                error_message=None,
                created_at=now,
                completed_at=None,
            )
            self._session.add(row)
        else:
            row.provider = selected_provider.name
            row.model = selected_provider.model
            row.status = "running"
            row.evidence_refs_json = list(dict.fromkeys(evidence_refs))
            row.output_json = {}
            row.validation_json = {}
            row.usage_json = {}
            row.provider_response_id = None
            row.latency_ms = None
            row.error_code = None
            row.error_message = None
            row.completed_at = None
        self._session.flush()
        self._calls += 1
        self._task_calls[task] += 1
        try:
            provider_result = selected_provider.generate_structured(
                task=task,
                developer_prompt=developer_prompt,
                payload=payload,
                response_model=response_model,
            )
            typed_value = cast(T, provider_result.output)
            validation_errors = validate(typed_value)
            row.output_json = typed_value.model_dump(mode="json")
            row.validation_json = {"errors": validation_errors}
            row.usage_json = {
                **provider_result.usage,
                "response_model": provider_result.model,
            }
            row.provider_response_id = provider_result.response_id
            row.latency_ms = provider_result.latency_ms
            row.completed_at = datetime.now(tz=UTC)
            if validation_errors:
                row.status = "rejected"
                self._consecutive_failures += 1
                self._session.flush()
                self._record_model_event(
                    task=task,
                    role=role,
                    scope_id=scope_id,
                    status="rejected",
                    model=row.model,
                    run_id=row.id,
                    parent_run_id=parent_run_id,
                    errors=validation_errors,
                )
                return None
            row.status = "success"
            self._consecutive_failures = 0
            self._session.flush()
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="success",
                model=row.model,
                run_id=row.id,
                parent_run_id=parent_run_id,
            )
            return StoredLLMResult(
                value=typed_value,
                run_id=row.id,
                provider=row.provider,
                model=row.model,
                prompt_version=row.prompt_version,
                cached=False,
            )
        except LLMProviderError as error:
            row.status = "failed"
            row.error_code = error.code[:80]
            row.error_message = str(error)[:500]
            row.completed_at = datetime.now(tz=UTC)
            self._consecutive_failures += 1
            self._session.flush()
            self._record_model_event(
                task=task,
                role=role,
                scope_id=scope_id,
                status="failed",
                model=row.model,
                run_id=row.id,
                parent_run_id=parent_run_id,
                errors=[error.code],
            )
            return None

    def reconcile_topics(
        self,
        *,
        scope_id: str,
        candidates: list[TopicCandidate],
        evidence: list[EvidenceItem],
    ) -> StoredLLMResult | None:
        if len(candidates) < 2:
            return None
        allowed_refs = {item.ref for item in evidence}
        candidate_keys = {candidate.key for candidate in candidates}

        def validate(value: TopicReconciliation) -> list[str]:
            errors: list[str] = []
            flattened = [key for topic in value.topics for key in topic.member_keys]
            if len(flattened) != len(set(flattened)):
                errors.append("duplicate_candidate_assignment")
            if set(flattened) != candidate_keys:
                errors.append("candidate_partition_mismatch")
            for topic in value.topics:
                errors.extend(_label_errors(topic.canonical_label))
                errors.extend(_reference_errors(topic.evidence_refs, allowed_refs))
            return sorted(set(errors))

        return self._invoke(
            task="topic-reconciliation",
            scope_kind="topic-pipeline",
            scope_id=scope_id,
            prompt_version=RECONCILIATION_PROMPT_VERSION,
            developer_prompt=(
                "Role: evidence-bound taxonomy editor for English YouTube AI/technology trends.\n"
                "Goal: partition the supplied deterministic topic candidates into precise "
                "microtrends. Merge only candidates that describe the same product, change, "
                "audience problem, and workflow. Keep different products, release waves, "
                "comparisons, or use cases separate.\n"
                "Success criteria: every candidate key appears exactly once; labels name the "
                "concrete product/change/use case; aliases preserve real alternate wording; "
                "every decision cites only supplied evidence refs.\n"
                "Naming policy: a trend label describes the observed subject or change only. "
                "Never encode a video format, creator stance, or editorial treatment such as "
                "tutorial, explainer, breakdown, deep dive, reaction, or test into the label.\n"
                "Key handling: copy candidate keys byte-for-byte from "
                "`required_candidate_keys`; never shorten, normalize, translate, or recreate "
                "them. Before returning, verify that flattening all `member_keys` is an exact "
                "partition of that list.\n"
                "Constraints: do not invent facts, products, metrics, or evidence refs. Do not "
                "score or rank trends. Prefer keeping candidates separate when evidence is "
                "ambiguous. Return English output matching the schema."
            ),
            input_data={
                "required_candidate_keys": sorted(candidate_keys),
                "candidates": [item.model_dump(mode="json") for item in candidates],
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=TopicReconciliation,
            validate=validate,
            role="taxonomy-adjudicator",
        )

    def plan_channel_discovery(
        self,
        *,
        workspace_id: str,
        channel_title: str,
        current_profile: dict[str, object],
        evidence: list[EvidenceItem],
    ) -> StoredLLMResult | None:
        """Translate stored channel evidence into narrow discovery lanes."""

        allowed_refs = {item.ref for item in evidence}

        def validate(value: ChannelDiscoveryPlan) -> list[str]:
            errors: list[str] = []
            normalized_queries: list[str] = []
            for item in value.queries:
                normalized = " ".join(item.query.lower().split())
                words = normalized.split()
                normalized_queries.append(normalized)
                if len(words) < 3:
                    errors.append("query_too_short")
                if len(words) > 10:
                    errors.append("query_too_long")
                if normalized in _GENERIC_LABELS:
                    errors.append("generic_query")
                if not all(character.isascii() for character in normalized):
                    errors.append("query_must_be_english")
                errors.extend(_reference_errors(item.evidence_refs, allowed_refs))
            if len(normalized_queries) != len(set(normalized_queries)):
                errors.append("duplicate_query")
            return sorted(set(errors))

        return self._invoke(
            task="channel-discovery-plan",
            scope_kind="workspace",
            scope_id=workspace_id,
            prompt_version=CHANNEL_DISCOVERY_PROMPT_VERSION,
            developer_prompt=(
                "Role: Creator Strategist for an English-language YouTube AI/technology "
                "trend intelligence product.\n"
                "Infer the creator's audience and content territory only from the supplied "
                "stored channel evidence. The source channel may be in another language; "
                "write the profile and all search queries in English.\n"
                "Create 10-20 distinct, narrow YouTube search lanes. Cover the channel's "
                "core territory plus useful adjacent AI/technology territory. Every query "
                "must be 3-10 words and name a concrete product, workflow, audience problem, "
                "release type, benchmark, failure, or adoption pattern. Mix release, "
                "workflow, comparison, failure, business-impact, and practitioner lanes. "
                "Do not output broad phrases such as 'AI tools' or 'AI trends'. Do not turn "
                "video titles into long search sentences. Do not invent channel facts or "
                "evidence references. Do not score trends. Each query must cite supplied "
                "evidence refs. Return only schema-valid structured output."
            ),
            input_data={
                "channel_title": channel_title,
                "current_profile": current_profile,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=[item.ref for item in evidence],
            response_model=ChannelDiscoveryPlan,
            validate=validate,
            role="creator-strategist",
        )

    def synthesize_topic(
        self,
        *,
        topic_id: str,
        candidate: TopicCandidate,
        evidence: list[EvidenceItem],
        deterministic_metrics: dict[str, object],
    ) -> StoredLLMResult | None:
        if not self._release_path_budget_available():
            self._record_reserved_audit_budget_skip(
                task="topic-synthesis",
                role="signal-analyst",
                scope_id=topic_id,
            )
            return None
        allowed_refs = {item.ref for item in evidence}

        def validate(value: TopicSynthesis) -> list[str]:
            errors = _label_errors(value.canonical_label)
            for claim in value.why_growing:
                errors.extend(_reference_errors(claim.evidence_refs, allowed_refs))
            if not any(claim.evidence_refs for claim in value.why_growing):
                errors.append("missing_grounded_claims")
            return sorted(set(errors))

        return self._invoke(
            task="topic-synthesis",
            scope_kind="topic",
            scope_id=topic_id,
            prompt_version=TOPIC_SYNTHESIS_PROMPT_VERSION,
            developer_prompt=(
                "Role: evidence-bound trend analyst for English YouTube AI/technology content.\n"
                "Goal: produce the most concrete useful microtrend name, a concise thesis, and "
                "two to five reasons why it is growing now.\n"
                "Success criteria: the label identifies a product/change/use case rather than "
                "a broad category; each growth claim is supported by exact supplied evidence "
                "refs; the thesis distinguishes the trend from generic AI coverage.\n"
                "Naming policy: the canonical label must remain neutral about video format and "
                "editorial stance. Name what is changing, not how a creator should cover it. "
                "Do not use tutorial, explainer, breakdown, deep dive, reaction, or test framing.\n"
                "Constraints: treat deterministic metrics as read-only. Never create or modify "
                "a score. Do not infer facts beyond supplied evidence. Use only supplied refs. "
                "If evidence is weak, narrow the wording instead of overstating it. Return "
                "English output matching the schema."
            ),
            input_data={
                "candidate": candidate.model_dump(mode="json"),
                "deterministic_metrics": deterministic_metrics,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=TopicSynthesis,
            validate=validate,
            role="signal-analyst",
        )

    def analyze_shadow_evidence(
        self,
        *,
        topic_key: str,
        candidate_rank: int,
        diagnostic_title: str,
        pre_audit: dict[str, object],
        evidence: list[EvidenceItem],
        evidence_metadata: dict[str, dict[str, str]],
    ) -> StoredLLMResult | None:
        """Build an evidence dossier without naming, scoring, or releasing a trend."""

        if not self._release_path_budget_available(required_calls=3):
            self._record_reserved_audit_budget_skip(
                task="shadow-evidence-analysis",
                role="evidence-analyst",
                scope_id=topic_key,
            )
            return None
        allowed_refs = {item.ref for item in evidence}

        def validate(value: ShadowEvidenceDossier) -> list[str]:
            errors: list[str] = []
            supporting_refs: list[str] = []
            for claim in [*value.supporting_families, *value.contradictions]:
                errors.extend(_reference_errors(claim.evidence_refs, allowed_refs))
            for claim in value.supporting_families:
                supporting_refs.extend(claim.evidence_refs)
            errors.extend(_independent_reference_errors(supporting_refs, evidence_metadata))
            return sorted(set(errors))

        return self._invoke(
            task="shadow-evidence-analysis",
            scope_kind="shadow-topic",
            scope_id=topic_key,
            prompt_version=SHADOW_EVIDENCE_ANALYSIS_PROMPT_VERSION,
            developer_prompt=(
                "Role: Evidence Analyst for a prospective English YouTube AI/technology "
                "trend study.\n"
                "Goal: assemble a compact factual dossier from the supplied frozen evidence. "
                "Describe the observed common pattern, at least two independently worded "
                "supporting evidence families, any contradiction or scope mismatch, and the "
                "remaining uncertainty.\n"
                "Evidence discipline: cite only supplied refs. Independent support requires "
                "different channels and different title families. Treat copied headlines as "
                "one family. Do not infer causality, future success, audience demand, or facts "
                "not present in the evidence.\n"
                "Boundary: do not name, score, rank, recommend, or release the trend. Do not "
                "suggest a video format. The deterministic rank and pre-audit are read-only. "
                "Return English schema-valid output."
            ),
            input_data={
                "candidate_rank": candidate_rank,
                "diagnostic_title": diagnostic_title,
                "deterministic_pre_audit": pre_audit,
                "evidence_metadata": evidence_metadata,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=ShadowEvidenceDossier,
            validate=validate,
            role="evidence-analyst",
        )

    def taxonomize_shadow_trend(
        self,
        *,
        topic_key: str,
        dossier: ShadowEvidenceDossier,
        evidence: list[EvidenceItem],
        evidence_metadata: dict[str, dict[str, str]],
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        """Name only the narrow subject supported by an independent dossier."""

        if not self._release_path_budget_available(required_calls=2):
            self._record_reserved_audit_budget_skip(
                task="shadow-trend-taxonomy",
                role="trend-taxonomist",
                scope_id=topic_key,
            )
            return None
        allowed_refs = {item.ref for item in evidence}

        def validate(value: ShadowTrendTaxonomy) -> list[str]:
            errors = _label_errors(value.neutral_label)
            errors.extend(_format_bias_errors(value.neutral_label, target="shadow_trend_label"))
            errors.extend(_reference_errors(value.evidence_refs, allowed_refs))
            errors.extend(_independent_reference_errors(value.evidence_refs, evidence_metadata))
            return sorted(set(errors))

        return self._invoke(
            task="shadow-trend-taxonomy",
            scope_kind="shadow-topic",
            scope_id=topic_key,
            prompt_version=SHADOW_TREND_TAXONOMY_PROMPT_VERSION,
            developer_prompt=(
                "Role: Trend Taxonomist for a prospective English YouTube AI/technology "
                "trend study.\n"
                "Goal: assign one stable, precise, neutral label to the phenomenon directly "
                "supported by the Evidence Analyst dossier. The label must identify a named "
                "product, mechanism, technical property, audience problem, market change, or "
                "specific workflow; never a broad category.\n"
                "Keep products and use cases separate when the evidence does not establish "
                "one identity. Do not encode a tutorial, review, comparison, reaction, test, "
                "news update, or creator stance. Cite at least two supplied refs from "
                "different channels and title families.\n"
                "Boundary: do not score, rank, predict, recommend, or add facts. If evidence "
                "is broad, choose the narrowest defensible wording for the Skeptic to audit. "
                "Return English schema-valid output."
            ),
            input_data={
                "dossier": dossier.model_dump(mode="json"),
                "evidence_metadata": evidence_metadata,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=ShadowTrendTaxonomy,
            validate=validate,
            role="trend-taxonomist",
            parent_run_id=parent_run_id,
        )

    def audit_shadow_trend(
        self,
        *,
        topic_key: str,
        dossier: ShadowEvidenceDossier,
        taxonomy: ShadowTrendTaxonomy,
        evidence: list[EvidenceItem],
        evidence_metadata: dict[str, dict[str, str]],
        analysis_run_id: str,
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        """Independently decide whether a candidate stays in the shadow queue."""

        if self._auditor_provider is None:
            self._record_model_event(
                task="shadow-trend-skeptic-audit",
                role="skeptic-auditor",
                scope_id=topic_key,
                status="skipped_not_configured",
                model="",
                parent_run_id=parent_run_id,
            )
            return None
        allowed_refs = {item.ref for item in evidence}

        def validate(value: ShadowTrendAudit) -> list[str]:
            errors = _reference_errors(value.evidence_refs, allowed_refs)
            independent_errors = _independent_reference_errors(
                value.evidence_refs,
                evidence_metadata,
            )
            if value.decision == "accept_to_shadow":
                errors.extend(independent_errors)
                if value.specificity != "narrow_subject":
                    errors.append("accepted_shadow_trend_must_be_narrow")
                if not value.independent_support:
                    errors.append("accepted_shadow_trend_requires_independent_support")
                if value.copy_wave_risk != "low":
                    errors.append("accepted_shadow_trend_has_copy_wave_risk")
                if value.language_scope != "english":
                    errors.append("accepted_shadow_trend_must_be_english")
                if not value.format_neutral:
                    errors.append("accepted_shadow_trend_must_be_format_neutral")
            return sorted(set(errors))

        return self._invoke(
            task="shadow-trend-skeptic-audit",
            scope_kind="shadow-topic",
            scope_id=topic_key,
            prompt_version=SHADOW_TREND_AUDIT_PROMPT_VERSION,
            developer_prompt=(
                "Role: independent Skeptic/Auditor for a prospective English YouTube "
                "AI/technology trend study.\n"
                "Goal: decide whether the proposed taxonomy represents one narrow, "
                "independently supported phenomenon worth retaining in the internal shadow "
                "queue. You may accept_to_shadow, watch, or reject. You may not rewrite it.\n"
                "Reject broad categories, roundup/comparison formats masquerading as trends, "
                "copied headline waves, non-English evidence, mixed products or use cases, "
                "unsupported causality, and labels derived only from hype or offer language. "
                "Use watch when the phenomenon is plausible but evidence diversity or scope "
                "is still borderline.\n"
                "Accept only a narrow subject with low copy-wave risk, English evidence, a "
                "format-neutral label, and direct support from at least two different channels "
                "and title families. Cite only supplied refs. Do not score, predict, recommend, "
                "or inspect future outcomes. Return English schema-valid output."
            ),
            input_data={
                "analysis_run_id": analysis_run_id,
                "dossier": dossier.model_dump(mode="json"),
                "taxonomy": taxonomy.model_dump(mode="json"),
                "evidence_metadata": evidence_metadata,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=ShadowTrendAudit,
            validate=validate,
            role="skeptic-auditor",
            provider=self._auditor_provider,
            parent_run_id=parent_run_id,
        )

    def synthesize_content_gaps(
        self,
        *,
        workspace_id: str,
        topic_id: str,
        topic_label: str,
        channel_profile: dict[str, object],
        gaps: list[dict[str, object]],
        evidence: list[EvidenceItem],
    ) -> StoredLLMResult | None:
        scope_id = f"{workspace_id}:{topic_id}"
        if not self._release_path_budget_available():
            self._record_reserved_audit_budget_skip(
                task="content-gap-synthesis",
                role="channel-strategist",
                scope_id=scope_id,
            )
            return None
        allowed_refs = {item.ref for item in evidence}
        expected_keys = {
            str(gap.get("gap_key", "")) for gap in gaps if isinstance(gap.get("gap_key"), str)
        }

        def validate(value: ContentGapSynthesis) -> list[str]:
            errors: list[str] = []
            returned_keys = [item.gap_key for item in value.gaps]
            if len(returned_keys) != len(set(returned_keys)):
                errors.append("duplicate_gap_key")
            if set(returned_keys) != expected_keys:
                errors.append("gap_key_mismatch")
            for gap in value.gaps:
                errors.extend(_reference_errors(gap.evidence_refs, allowed_refs))
                errors.extend(_format_bias_errors(gap.title, target="gap_title"))
                for direction in gap.title_directions:
                    errors.extend(_format_bias_errors(direction, target="title_direction"))
            return sorted(set(errors))

        return self._invoke(
            task="content-gap-synthesis",
            scope_kind="workspace-topic",
            scope_id=scope_id,
            prompt_version=CONTENT_GAP_PROMPT_VERSION,
            developer_prompt=(
                "Role: evidence-bound YouTube content strategist.\n"
                "Goal: rewrite each supplied deterministic gap candidate into a specific, "
                "publishable angle for the supplied channel profile.\n"
                "Success criteria: keep every gap_key; title and promise are materially "
                "different from occupied coverage; why_now and differentiation cite only "
                "supplied evidence; title directions are concrete rather than generic.\n"
                "Neutrality policy: describe what the creator can cover, not the video format "
                "or editorial stance. Do not prescribe tutorials, explainers, breakdowns, "
                "deep dives, reactions, tests, reviews, or documentaries. The creator chooses "
                "the format. Titles must remain factual questions or subject statements.\n"
                "Constraints: do not change rank, score components, timing, feasibility, or "
                "open/occupied classification. Do not invent tests already performed, audience "
                "demand, results, or evidence. Use only supplied refs. Return English output "
                "matching the schema."
            ),
            input_data={
                "topic_label": topic_label,
                "channel_profile": channel_profile,
                "deterministic_gap_candidates": gaps,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=ContentGapSynthesis,
            validate=validate,
            role="channel-strategist",
        )

    def synthesize_evidence_insight(
        self,
        *,
        workspace_id: str,
        topic_id: str,
        topic_label: str,
        channel_profile: dict[str, object],
        deterministic_metrics: dict[str, object],
        evidence: list[EvidenceItem],
    ) -> StoredLLMResult | None:
        """Extract a content insight, not a presentation recommendation."""

        scope_id = f"{workspace_id}:{topic_id}"
        if not self._release_path_budget_available():
            self._record_reserved_audit_budget_skip(
                task="evidence-insight-synthesis",
                role="evidence-analyst",
                scope_id=scope_id,
            )
            return None
        allowed_refs = {item.ref for item in evidence}

        def validate(value: EvidenceInsightSynthesis) -> list[str]:
            errors: list[str] = []
            if value.insight is None:
                if len(value.no_insight_reason.strip()) < 12:
                    errors.append("missing_no_insight_reason")
                return errors
            insight = value.insight
            errors.extend(_reference_errors(insight.evidence_refs, allowed_refs))
            errors.extend(_format_bias_errors(insight.topic, target="insight_topic"))
            errors.extend(
                _format_bias_errors(
                    insight.creator_question,
                    target="creator_question",
                )
            )
            if len(set(insight.evidence_refs)) < 2:
                errors.append("insight_requires_multiple_evidence_refs")
            if insight.topic.strip().lower() == topic_label.strip().lower():
                errors.append("insight_topic_repeats_parent_topic")
            return sorted(set(errors))

        return self._invoke(
            task="evidence-insight-synthesis",
            scope_kind="workspace-topic",
            scope_id=scope_id,
            prompt_version=EVIDENCE_INSIGHT_PROMPT_VERSION,
            developer_prompt=(
                "Role: Evidence Analyst for English-language YouTube AI/technology "
                "trend intelligence.\n"
                "Goal: return one genuinely non-obvious, concrete subject insight for the "
                "creator, or explicitly return no insight. A useful insight identifies a "
                "supported contradiction, behavior shift, constraint, adoption pattern, or "
                "market-structure change that a viewer would not get from the broad topic "
                "name alone.\n"
                "Evidence floor: the statement must be directly supported by at least two "
                "supplied evidence references representing independent videos or sources. "
                "Use stored metrics only as context; never create or change a score. Do not "
                "infer causality from correlation.\n"
                "Neutrality policy: topic and creator_question describe what is changing or "
                "unresolved. Never prescribe a tutorial, explainer, breakdown, deep dive, "
                "reaction, comparison video, test, review, documentary, hook, emotion, or "
                "other presentation format. High-performing packaging is not a subject "
                "insight.\n"
                "Reject as obvious: the topic is popular, AI is useful, creators are talking "
                "about it, a format is missing, or the creator could cover the broad topic. "
                "Reject unsupported content gaps and generic advice. If the supplied "
                "evidence cannot clear this bar, set insight to null and explain why in "
                "no_insight_reason. Return English output matching the schema."
            ),
            input_data={
                "parent_topic": topic_label,
                "channel_profile": channel_profile,
                "deterministic_metrics": deterministic_metrics,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=EvidenceInsightSynthesis,
            validate=validate,
            role="evidence-analyst",
        )

    def audit_topic_synthesis(
        self,
        *,
        topic_id: str,
        candidate: TopicCandidate,
        synthesis: TopicSynthesis,
        evidence: list[EvidenceItem],
        deterministic_metrics: dict[str, object],
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        expected_targets = [
            "canonical_label",
            "thesis",
            *[f"why_growing[{index}]" for index, _claim in enumerate(synthesis.why_growing)],
        ]
        return self._audit_artifact(
            task="topic-grounding-audit",
            scope_kind="topic",
            scope_id=topic_id,
            artifact_kind="topic_synthesis",
            artifact={
                "candidate": candidate.model_dump(mode="json"),
                "synthesis": synthesis.model_dump(mode="json"),
                "deterministic_metrics": deterministic_metrics,
            },
            expected_targets=expected_targets,
            evidence=evidence,
            parent_run_id=parent_run_id,
        )

    def audit_content_gap_synthesis(
        self,
        *,
        workspace_id: str,
        topic_id: str,
        topic_label: str,
        synthesis: ContentGapSynthesis,
        deterministic_gaps: list[dict[str, object]],
        evidence: list[EvidenceItem],
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        expected_targets = [
            f"gap:{gap.gap_key}:{field}"
            for gap in synthesis.gaps
            for field in (
                "title",
                "audience_promise",
                "why_now",
                "differentiation",
            )
        ]
        return self._audit_artifact(
            task="content-gap-grounding-audit",
            scope_kind="workspace-topic",
            scope_id=f"{workspace_id}:{topic_id}",
            artifact_kind="content_gap_synthesis",
            artifact={
                "topic_label": topic_label,
                "deterministic_gap_candidates": deterministic_gaps,
                "synthesis": synthesis.model_dump(mode="json"),
            },
            expected_targets=expected_targets,
            evidence=evidence,
            parent_run_id=parent_run_id,
        )

    def audit_evidence_insight(
        self,
        *,
        workspace_id: str,
        topic_id: str,
        topic_label: str,
        insight: EvidenceInsight,
        deterministic_metrics: dict[str, object],
        evidence: list[EvidenceItem],
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        if self._auditor_provider is None:
            self._record_model_event(
                task="evidence-insight-grounding-audit",
                role="skeptic-auditor",
                scope_id=f"{workspace_id}:{topic_id}",
                status="skipped_not_configured",
                model="",
                parent_run_id=parent_run_id,
            )
            return None
        expected_targets = [
            "insight.topic",
            "insight.statement",
            "insight.why_non_obvious",
        ]
        allowed_refs = {item.ref for item in evidence}
        expected = set(expected_targets)

        def validate(value: InsightReleaseAudit) -> list[str]:
            errors: list[str] = []
            targets = [check.target for check in value.checks]
            if len(targets) != len(set(targets)):
                errors.append("duplicate_audit_target")
            if set(targets) != expected:
                errors.append("audit_target_mismatch")
            for check in value.checks:
                errors.extend(_reference_errors(check.evidence_refs, allowed_refs))
            errors.extend(_reference_errors(value.evidence_refs, allowed_refs))
            quality_passed = (
                all(check.verdict == "supported" for check in value.checks)
                and value.non_obviousness == "strong"
                and value.decision_value == "changes_creator_decision"
                and value.specificity == "specific_mechanism"
                and not value.generic_restatement
                and len(set(value.evidence_refs)) >= 2
            )
            if value.decision == "accept" and not quality_passed:
                errors.append("invalid_insight_release_accept")
            if value.decision == "reject" and quality_passed:
                errors.append("invalid_insight_release_reject")
            return sorted(set(errors))

        return self._invoke(
            task="evidence-insight-grounding-audit",
            scope_kind="workspace-topic",
            scope_id=f"{workspace_id}:{topic_id}",
            prompt_version=INSIGHT_RELEASE_AUDIT_PROMPT_VERSION,
            developer_prompt=(
                "Role: independent Skeptic/Auditor for English YouTube AI/technology "
                "trend intelligence.\n"
                "Goal: protect a creator from grounded but obvious filler. Audit both "
                "evidence grounding and editorial insight quality. You may accept or "
                "reject; you may not rewrite the candidate, alter metrics, or add facts.\n"
                "Grounding: return exactly one check for every expected target. Supported "
                "means the cited stored evidence directly entails the wording. Reject "
                "overstatement, causality inferred from correlation, and scope mismatch.\n"
                "Non-obviousness: accept only a concrete mechanism, boundary condition, "
                "second-order effect, behavior change, contradiction, or market-structure "
                "change that could not reasonably be produced from the broad parent topic "
                "without examining the supplied evidence.\n"
                "Decision value: the insight must change a creator decision by identifying "
                "which audience assumption to challenge, which condition changes the "
                "outcome, or which timing/order dynamic matters. Merely adding context is "
                "not enough.\n"
                "Always reject generic restatements such as: AI is useful but needs human "
                "judgment; adoption needs validation, training, best practices, or clear "
                "goals; AI changes jobs rather than simply eliminating them; the topic is "
                "popular; creators are covering it; or a format is missing. Reject a "
                "summary assembled from source titles without a new supported relationship.\n"
                "Accept only when every grounding check is supported, non_obviousness is "
                "strong, decision_value changes_creator_decision, specificity is "
                "specific_mechanism, generic_restatement is false, and at least two "
                "independent supplied refs support the release. Return English output "
                "matching the schema."
            ),
            input_data={
                "artifact_kind": "evidence_insight",
                "artifact": {
                    "parent_topic": topic_label,
                    "insight": insight.model_dump(mode="json"),
                    "deterministic_metrics": deterministic_metrics,
                },
                "expected_targets": expected_targets,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=InsightReleaseAudit,
            validate=validate,
            role="skeptic-auditor",
            provider=self._auditor_provider,
            parent_run_id=parent_run_id,
        )

    def _audit_artifact(
        self,
        *,
        task: str,
        scope_kind: str,
        scope_id: str,
        artifact_kind: str,
        artifact: dict[str, object],
        expected_targets: list[str],
        evidence: list[EvidenceItem],
        parent_run_id: str,
    ) -> StoredLLMResult | None:
        if self._auditor_provider is None:
            self._record_model_event(
                task=task,
                role="grounding-verifier",
                scope_id=scope_id,
                status="skipped_not_configured",
                model="",
                parent_run_id=parent_run_id,
            )
            return None
        allowed_refs = {item.ref for item in evidence}
        expected = set(expected_targets)

        def validate(value: GroundingAudit) -> list[str]:
            errors: list[str] = []
            targets = [check.target for check in value.checks]
            if len(targets) != len(set(targets)):
                errors.append("duplicate_audit_target")
            if set(targets) != expected:
                errors.append("audit_target_mismatch")
            for check in value.checks:
                errors.extend(_reference_errors(check.evidence_refs, allowed_refs))
            all_supported = all(check.verdict == "supported" for check in value.checks)
            if value.decision == "accept" and not all_supported:
                errors.append("invalid_accept_decision")
            if value.decision == "reject" and all_supported:
                errors.append("invalid_reject_decision")
            return sorted(set(errors))

        return self._invoke(
            task=task,
            scope_kind=scope_kind,
            scope_id=scope_id,
            prompt_version=GROUNDING_AUDIT_PROMPT_VERSION,
            developer_prompt=(
                "Role: independent evidence grounding verifier for English YouTube "
                "AI/technology trend intelligence.\n"
                "Goal: verify every expected target in the proposed artifact against the "
                "supplied stored evidence. You may accept or reject; you may not rewrite the "
                "artifact, change deterministic metrics, or add facts.\n"
                "Success criteria: return exactly one check for every expected target; mark "
                "supported only when the cited evidence directly entails the wording; mark "
                "overstated when the direction is plausible but stronger than evidence; mark "
                "unsupported when evidence does not establish it; mark scope_mismatch when "
                "different products, releases, audiences, or workflows were conflated.\n"
                "Constraints: cite only supplied evidence refs. Absence of contradiction is "
                "not support. Correlation is not a causal explanation. Accept only if every "
                "target is supported. Return English output matching the schema."
            ),
            input_data={
                "artifact_kind": artifact_kind,
                "artifact": artifact,
                "expected_targets": expected_targets,
                "evidence": [item.model_dump(mode="json") for item in evidence],
            },
            evidence_refs=sorted(allowed_refs),
            response_model=GroundingAudit,
            validate=validate,
            role="grounding-verifier",
            provider=self._auditor_provider,
            parent_run_id=parent_run_id,
        )

    def operational_metrics(self) -> dict[str, object]:
        now = datetime.now(tz=UTC)
        total = int(self._session.scalar(select(func.count(LLMIntelligenceRun.id))) or 0)
        successful = int(
            self._session.scalar(
                select(func.count(LLMIntelligenceRun.id)).where(
                    LLMIntelligenceRun.status == "success"
                )
            )
            or 0
        )
        failed = int(
            self._session.scalar(
                select(func.count(LLMIntelligenceRun.id)).where(
                    LLMIntelligenceRun.status.in_(("failed", "rejected"))
                )
            )
            or 0
        )
        latest = self._session.scalar(
            select(LLMIntelligenceRun).order_by(desc(LLMIntelligenceRun.created_at)).limit(1)
        )
        audit_outputs = list(
            self._session.scalars(
                select(LLMIntelligenceRun.output_json).where(
                    LLMIntelligenceRun.task.in_(
                        (
                            "topic-grounding-audit",
                            "content-gap-grounding-audit",
                            "evidence-insight-grounding-audit",
                        )
                    ),
                    LLMIntelligenceRun.status == "success",
                )
            )
        )
        audit_accepts = sum(
            output.get("decision") == "accept"
            for output in audit_outputs
            if isinstance(output, dict)
        )
        stale_runs = int(
            self._session.scalar(
                select(func.count(LLMIntelligenceRun.id)).where(
                    LLMIntelligenceRun.status == "running",
                    LLMIntelligenceRun.created_at
                    < now - timedelta(minutes=max(1, self._settings.llm_stale_run_minutes)),
                )
            )
            or 0
        )
        return {
            "feature_enabled": self._settings.feature_llm_intelligence,
            "configured": self.configured,
            "provider": self._provider.name if self._provider is not None else None,
            "model": self._provider.model if self._provider is not None else None,
            "auditor_model": (
                self._auditor_provider.model if self._auditor_provider is not None else None
            ),
            "policy_version": LLM_POLICY_VERSION,
            "audit_required": self._settings.llm_require_grounding_audit,
            "audit_run_count": len(audit_outputs),
            "audit_acceptance_rate": round(
                audit_accepts / max(len(audit_outputs), 1),
                4,
            ),
            "circuit_open": (
                self._consecutive_failures >= self._settings.llm_circuit_failure_threshold
            ),
            "run_count": total,
            "successful_runs": successful,
            "failed_or_rejected_runs": failed,
            "daily_tokens_used": self._daily_tokens_used(),
            "daily_token_budget": self._settings.llm_daily_token_budget,
            "stale_runs": stale_runs,
            "latest_status": latest.status if latest is not None else None,
            "latest_run_at": latest.created_at if latest is not None else None,
        }
