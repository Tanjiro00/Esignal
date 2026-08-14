from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import cast

import httpx
from pydantic import BaseModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.models import Base, LLMIntelligenceRun
from apps.worker.llm_intelligence import LLMIntelligenceService
from apps.worker.topic_intelligence import TopicDefinition, TopicIntelligenceService
from packages.llm_intelligence import (
    EvidenceInsight,
    EvidenceItem,
    GroundingAudit,
    LLMProviderResult,
    OpenAIResponsesProvider,
    ShadowEvidenceDossier,
    ShadowTrendTaxonomy,
    TopicCandidate,
    TopicSynthesis,
)


def test_channel_discovery_plan_rejects_generic_or_ungrounded_queries() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "audience_description": "Software practitioners evaluating applied AI systems.",
            "core_topics": ["AI coding", "AI agents", "software teams"],
            "adjacent_topics": ["model releases", "security", "AI business"],
            "queries": [
                {
                    "query": "AI tools",
                    "category": "AI tools",
                    "rationale": "This is intentionally too broad for acceptance.",
                    "evidence_refs": ["video:1"],
                }
                for _ in range(10)
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=provider,
        )
        result = service.plan_channel_discovery(
            workspace_id="workspace-1",
            channel_title="Creator",
            current_profile={},
            evidence=_evidence(),
        )
        assert result is None
        run = session.scalar(select(LLMIntelligenceRun))
        assert run is not None
        assert run.status == "rejected"
        assert "generic_query" in run.validation_json["errors"]


def test_topic_synthesis_rejects_format_biased_trend_label() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "canonical_label": "How to build Claude Code workflows",
            "aliases": [],
            "thesis": (
                "Independent creators are covering the same concrete workflow change "
                "across multiple stored videos."
            ),
            "why_growing": [
                {
                    "text": "The stored video names the workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "text": "The stored snapshot shows relative momentum.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=provider,
        )
        result = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={},
        )
        assert result is None
        run = session.scalar(select(LLMIntelligenceRun))
        assert run is not None
        assert "format_biased_label" in run.validation_json["errors"]


def test_content_gap_synthesis_rejects_prescribed_video_format() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "gaps": [
                {
                    "gap_key": "gap-1",
                    "title": "A tutorial for Claude Code workflow adoption",
                    "audience_promise": "Clarify the unresolved adoption question.",
                    "why_now": "The supplied evidence shows repeated current coverage.",
                    "differentiation": "Focus on the unresolved decision in the evidence.",
                    "title_directions": [
                        "Claude Code adoption: observed changes",
                        "Claude Code adoption: open questions",
                    ],
                    "evidence_refs": ["video:1"],
                }
            ]
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=provider,
        )
        result = service.synthesize_content_gaps(
            workspace_id="workspace-1",
            topic_id="topic-1",
            topic_label="Claude Code workflow adoption",
            channel_profile={},
            gaps=[{"gap_key": "gap-1"}],
            evidence=_evidence(),
        )
        assert result is None
        run = session.scalar(select(LLMIntelligenceRun))
        assert run is not None
        assert "format_biased_gap_title" in run.validation_json["errors"]


def _shadow_metadata(*, same_channel: bool = False) -> dict[str, dict[str, str]]:
    return {
        "video:1": {"channel_id": "channel-a", "title_family": "family-a"},
        "video-snapshot:1": {
            "channel_id": "channel-a" if same_channel else "channel-b",
            "title_family": "family-b",
        },
    }


def _shadow_dossier() -> ShadowEvidenceDossier:
    return ShadowEvidenceDossier(
        observed_pattern=(
            "Independent evidence describes Claude Code handling recurring pull-request "
            "triage work."
        ),
        supporting_families=[
            {
                "text": "One stored video describes pull-request triage automation.",
                "evidence_refs": ["video:1"],
            },
            {
                "text": "A separate stored source records the same narrow workflow.",
                "evidence_refs": ["video-snapshot:1"],
            },
        ],
        contradictions=[],
        uncertainty="The evidence does not establish future adoption or creator performance.",
    )


def _shadow_taxonomy() -> ShadowTrendTaxonomy:
    return ShadowTrendTaxonomy(
        neutral_label="Claude Code pull-request triage adoption",
        rationale="Two independent evidence families describe the same narrow workflow.",
        evidence_refs=["video:1", "video-snapshot:1"],
    )


def test_shadow_agent_chain_accepts_only_after_three_stored_roles() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    analyst = FakeProvider(_shadow_dossier().model_dump(mode="json"))
    auditor = FakeProvider(
        {
            "decision": "accept_to_shadow",
            "summary": "The label is narrow and supported by independent evidence families.",
            "specificity": "narrow_subject",
            "independent_support": True,
            "copy_wave_risk": "low",
            "language_scope": "english",
            "format_neutral": True,
            "evidence_refs": ["video:1", "video-snapshot:1"],
            "reason_codes": ["narrow_identity", "independent_support"],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=analyst,
            auditor_provider=auditor,
        )
        analysis = service.analyze_shadow_evidence(
            topic_key="shadow-topic-1",
            candidate_rank=1,
            diagnostic_title="Claude Code pull-request triage",
            pre_audit={"pre_audit_passed": True},
            evidence=_evidence(),
            evidence_metadata=_shadow_metadata(),
        )
        assert analysis is not None
        analyst.output = _shadow_taxonomy().model_dump(mode="json")
        taxonomy = service.taxonomize_shadow_trend(
            topic_key="shadow-topic-1",
            dossier=cast(ShadowEvidenceDossier, analysis.value),
            evidence=_evidence(),
            evidence_metadata=_shadow_metadata(),
            parent_run_id=analysis.run_id,
        )
        assert taxonomy is not None
        audit = service.audit_shadow_trend(
            topic_key="shadow-topic-1",
            dossier=cast(ShadowEvidenceDossier, analysis.value),
            taxonomy=cast(ShadowTrendTaxonomy, taxonomy.value),
            evidence=_evidence(),
            evidence_metadata=_shadow_metadata(),
            analysis_run_id=analysis.run_id,
            parent_run_id=taxonomy.run_id,
        )

        assert audit is not None
        assert analyst.calls == 2
        assert auditor.calls == 1
        tasks = list(
            session.scalars(select(LLMIntelligenceRun.task).order_by(LLMIntelligenceRun.created_at))
        )
        assert tasks == [
            "shadow-evidence-analysis",
            "shadow-trend-taxonomy",
            "shadow-trend-skeptic-audit",
        ]


def test_shadow_skeptic_cannot_accept_same_channel_support() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    auditor = FakeProvider(
        {
            "decision": "accept_to_shadow",
            "summary": "The candidate incorrectly claims independent support.",
            "specificity": "narrow_subject",
            "independent_support": True,
            "copy_wave_risk": "low",
            "language_scope": "english",
            "format_neutral": True,
            "evidence_refs": ["video:1", "video-snapshot:1"],
            "reason_codes": ["claimed_independent_support"],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=auditor,
            auditor_provider=auditor,
        )
        result = service.audit_shadow_trend(
            topic_key="shadow-topic-1",
            dossier=_shadow_dossier(),
            taxonomy=_shadow_taxonomy(),
            evidence=_evidence(),
            evidence_metadata=_shadow_metadata(same_channel=True),
            analysis_run_id="analysis-1",
            parent_run_id="taxonomy-1",
        )

        assert result is None
        row = session.scalar(
            select(LLMIntelligenceRun).where(
                LLMIntelligenceRun.task == "shadow-trend-skeptic-audit"
            )
        )
        assert row is not None
        assert "requires_independent_channels" in row.validation_json["errors"]


class FakeProvider:
    name = "fake"
    model = "fake-evidence-model"

    def __init__(self, output: dict[str, object]) -> None:
        self.output = output
        self.calls = 0
        self.payloads: list[dict[str, object]] = []

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult:
        del task, developer_prompt
        self.payloads.append(cast(dict[str, object], json.loads(payload)))
        self.calls += 1
        return LLMProviderResult(
            output=response_model.model_validate(self.output),
            response_id=f"fake-response-{self.calls}",
            model=self.model,
            usage={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            latency_ms=12,
        )


class EchoPartitionProvider(FakeProvider):
    def __init__(self) -> None:
        super().__init__({})

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult:
        del task, developer_prompt
        parsed = cast(dict[str, object], json.loads(payload))
        self.payloads.append(parsed)
        self.calls += 1
        candidates = cast(list[dict[str, object]], parsed["candidates"])
        output = {
            "topics": [
                {
                    "member_keys": [str(candidate["key"])],
                    "canonical_label": str(candidate["current_label"]),
                    "aliases": [],
                    "rationale": "The stored evidence supports a distinct workflow.",
                    "evidence_refs": cast(list[str], candidate["evidence_refs"]),
                }
                for candidate in candidates
            ]
        }
        return LLMProviderResult(
            output=response_model.model_validate(output),
            response_id=f"echo-response-{self.calls}",
            model=self.model,
            usage={"input_tokens": 100, "output_tokens": 40, "total_tokens": 140},
            latency_ms=12,
        )


def _candidate() -> TopicCandidate:
    return TopicCandidate(
        key="candidate-1",
        current_label="Task-specific AI agents",
        aliases=["AI agent workflows"],
        facet="applied_workflows",
        domain="AI agents",
        primary_entity="Claude Code",
        audience="developers",
        user_problem="automate recurring software work",
        core_claim="complete the workflow end to end",
        evidence_refs=["video:1", "video-snapshot:1"],
    )


def _evidence() -> list[EvidenceItem]:
    return [
        EvidenceItem(
            ref="video:1",
            kind="video",
            title="Claude Code automates pull request triage",
            text="A practical walkthrough of recurring pull request triage.",
        ),
        EvidenceItem(
            ref="video-snapshot:1",
            kind="metric",
            title="Stored snapshot",
            text="The video is a 2.4x channel-relative outlier.",
        ),
    ]


def test_reconciliation_sends_exact_required_candidate_partition() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    candidates = [
        _candidate(),
        _candidate().model_copy(
            update={
                "key": "candidate/2:keep-exact",
                "current_label": "Cursor agent review workflows",
            }
        ),
    ]
    provider = FakeProvider(
        {
            "topics": [
                {
                    "member_keys": ["candidate-1"],
                    "canonical_label": "Claude Code pull-request triage workflows",
                    "aliases": [],
                    "rationale": "The evidence describes one concrete workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "member_keys": ["candidate/2:keep-exact"],
                    "canonical_label": "Cursor agent pull-request review workflows",
                    "aliases": [],
                    "rationale": "The product identity remains distinct.",
                    "evidence_refs": ["video:1"],
                },
            ]
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=provider,
        )
        result = service.reconcile_topics(
            scope_id="partition-test",
            candidates=candidates,
            evidence=_evidence(),
        )

    assert result is not None
    assert provider.payloads[0]["required_candidate_keys"] == [
        "candidate-1",
        "candidate/2:keep-exact",
    ]


def test_openai_provider_uses_responses_structured_output_without_storage() -> None:
    captured: dict[str, object] = {}
    output = {
        "canonical_label": "Claude Code pull-request triage workflows",
        "aliases": ["Automated PR triage with Claude Code"],
        "thesis": (
            "Independent creators are moving Claude Code from demos into repeatable "
            "pull-request review and triage workflows."
        ),
        "why_growing": [
            {"text": "Creators show the same workflow.", "evidence_refs": ["video:1"]},
            {
                "text": "The stored video is an outlier.",
                "evidence_refs": ["video-snapshot:1"],
            },
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(cast(dict[str, object], json.loads(request.content)))
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={
                "id": "resp_test",
                "model": "gpt-5.6-terra",
                "status": "completed",
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 55,
                    "total_tokens": 175,
                },
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(output),
                            }
                        ],
                    }
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAIResponsesProvider(
        api_key="test-key",
        model="gpt-5.6-terra",
        client=client,
    )
    result = provider.generate_structured(
        task="topic-synthesis",
        developer_prompt="Use stored evidence only.",
        payload='{"evidence":[]}',
        response_model=TopicSynthesis,
    )

    assert result.output == TopicSynthesis.model_validate(output)
    assert captured["store"] is False
    assert captured["model"] == "gpt-5.6-terra"
    text = cast(dict[str, object], captured["text"])
    response_format = cast(dict[str, object], text["format"])
    assert response_format["type"] == "json_schema"
    assert response_format["strict"] is True
    assert "test-key" not in json.dumps(captured)


def test_grounded_topic_synthesis_is_cached_and_audited() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "canonical_label": "Claude Code pull-request triage workflows",
            "aliases": ["Automated PR triage with Claude Code"],
            "thesis": (
                "Creators are applying Claude Code to repeatable pull-request triage "
                "rather than generic coding demos."
            ),
            "why_growing": [
                {
                    "text": "Multiple videos describe pull-request triage.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "text": "The stored upload is a channel-relative outlier.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(
                feature_llm_intelligence=True,
                llm_max_calls_per_run=1,
                llm_require_grounding_audit=False,
            ),
            provider=provider,
        )
        service.start_trace("pipeline-1")
        first = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
        )
        second = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
        )

        assert first is not None
        assert second is not None
        assert second.cached is True
        assert provider.calls == 1
        assert session.scalar(select(func.count(LLMIntelligenceRun.id))) == 1
        row = session.scalar(select(LLMIntelligenceRun))
        assert row is not None
        assert row.status == "success"
        assert row.evidence_refs_json == ["video-snapshot:1", "video:1"]
        assert row.usage_json["total_tokens"] == 140
        trace = service.trace_summary()
        assert trace["provider_calls"] == 1
        assert len(cast(list[object], trace["events"])) == 2


def test_global_daily_token_budget_stops_new_provider_calls() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "canonical_label": "Claude Code pull-request triage workflows",
            "aliases": ["Automated PR triage with Claude Code"],
            "thesis": (
                "Independent creators are applying Claude Code to repeatable pull-request triage."
            ),
            "why_growing": [
                {
                    "text": "The stored video names pull-request triage.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "text": "The stored snapshot shows relative momentum.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(
                feature_llm_intelligence=True,
                llm_require_grounding_audit=False,
                llm_daily_token_budget=140,
            ),
            provider=provider,
        )
        service.start_trace("budget-test")

        first = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={},
        )
        second = service.synthesize_topic(
            topic_id="topic-2",
            candidate=_candidate().model_copy(update={"key": "candidate-2"}),
            evidence=_evidence(),
            deterministic_metrics={},
        )

        assert first is not None
        assert second is None
        assert provider.calls == 1
        assert service.trace_summary()["decisions"]["skipped_daily_token_budget"] == 1


def test_low_priority_topic_budget_reserves_tokens_for_evidence_insights() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    topic_provider = FakeProvider(
        {
            "canonical_label": "Claude Code pull-request triage workflows",
            "aliases": [],
            "thesis": "Independent creators cover repeatable pull-request triage workflows.",
            "why_growing": [
                {"text": "A stored video names triage.", "evidence_refs": ["video:1"]},
                {
                    "text": "A stored snapshot records momentum.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    insight_provider = FakeProvider(
        {
            "insight": {
                "topic": "Pull-request triage is becoming a persistent agent task",
                "statement": (
                    "Independent evidence describes triage as recurring work rather than "
                    "a one-off coding demonstration."
                ),
                "why_non_obvious": (
                    "The repeated task boundary is narrower than generic Claude Code adoption."
                ),
                "creator_question": "Where does persistent triage outperform one-off coding?",
                "insight_kind": "adoption_pattern",
                "evidence_refs": ["video:1", "video-snapshot:1"],
            },
            "no_insight_reason": "",
        }
    )
    with Session(engine) as session:
        settings = Settings(
            feature_llm_intelligence=True,
            llm_require_grounding_audit=False,
            llm_daily_token_budget=1_000,
            llm_topic_synthesis_daily_token_share=0.1,
        )
        topic_service = LLMIntelligenceService(session, settings, provider=topic_provider)
        topic_service.start_trace("topic-budget")
        first = topic_service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={},
        )
        second = topic_service.synthesize_topic(
            topic_id="topic-2",
            candidate=_candidate().model_copy(update={"key": "candidate-2"}),
            evidence=_evidence(),
            deterministic_metrics={},
        )
        insight_service = LLMIntelligenceService(session, settings, provider=insight_provider)
        insight_service.start_trace("insight-budget")
        insight = insight_service.synthesize_evidence_insight(
            workspace_id="workspace-1",
            topic_id="topic-3",
            topic_label="Claude Code adoption",
            channel_profile={},
            deterministic_metrics={},
            evidence=_evidence(),
        )

        assert first is not None
        assert second is None
        assert insight is not None
        assert topic_service.trace_summary()["decisions"]["skipped_task_daily_token_budget"] == 1


def test_stale_llm_runs_are_recovered() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    with Session(engine) as session:
        session.add(
            LLMIntelligenceRun(
                id="stale-llm",
                task="topic-synthesis",
                scope_kind="topic",
                scope_id="topic-1",
                input_hash="hash",
                provider="fake",
                model="fake",
                prompt_version="test",
                status="running",
                evidence_refs_json=[],
                output_json={},
                validation_json={},
                usage_json={},
                provider_response_id=None,
                latency_ms=None,
                error_code=None,
                error_message=None,
                created_at=now - timedelta(hours=1),
                completed_at=None,
            )
        )
        session.commit()
        service = LLMIntelligenceService(
            session,
            Settings(
                feature_llm_intelligence=True,
                llm_stale_run_minutes=15,
            ),
            provider=FakeProvider({}),
        )

        recovered = service.reconcile_stale_runs(now=now)

        assert recovered == 1
        row = session.get(LLMIntelligenceRun, "stale-llm")
        assert row is not None
        assert row.status == "failed"
        assert row.error_code == "stale_run_recovered"


def test_unknown_evidence_reference_rejects_llm_output() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "canonical_label": "Claude Code pull-request triage workflows",
            "aliases": [],
            "thesis": (
                "Creators are applying Claude Code to repeatable pull-request triage "
                "rather than generic coding demos."
            ),
            "why_growing": [
                {"text": "Unsupported claim.", "evidence_refs": ["video:invented"]},
                {"text": "Another unsupported claim.", "evidence_refs": ["web:invented"]},
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=provider,
        )
        result = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
        )

        assert result is None
        row = session.scalar(select(LLMIntelligenceRun))
        assert row is not None
        assert row.status == "rejected"
        assert "unknown_evidence_ref:video:invented" in row.validation_json["errors"]


def test_independent_grounding_audit_can_reject_an_overstated_artifact() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    synthesis = TopicSynthesis(
        canonical_label="Claude Code pull-request triage workflows",
        aliases=["Automated PR triage with Claude Code"],
        thesis=("Every software team is replacing human pull-request triage with Claude Code."),
        why_growing=[
            {
                "text": "A stored video shows the workflow.",
                "evidence_refs": ["video:1"],
            },
            {
                "text": "The stored upload is a channel-relative outlier.",
                "evidence_refs": ["video-snapshot:1"],
            },
        ],
    )
    primary = FakeProvider({})
    auditor = FakeProvider(
        {
            "decision": "reject",
            "summary": "The thesis generalizes from one stored example to every team.",
            "checks": [
                {
                    "target": "canonical_label",
                    "verdict": "supported",
                    "rationale": "The video directly demonstrates this named workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "target": "thesis",
                    "verdict": "overstated",
                    "rationale": "One example cannot establish adoption by every team.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "target": "why_growing[0]",
                    "verdict": "supported",
                    "rationale": "The stored video shows the workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "target": "why_growing[1]",
                    "verdict": "supported",
                    "rationale": "The stored metric records relative performance.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=primary,
            auditor_provider=auditor,
        )
        service.start_trace("pipeline-audit")
        result = service.audit_topic_synthesis(
            topic_id="topic-1",
            candidate=_candidate(),
            synthesis=synthesis,
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
            parent_run_id="synthesis-run-1",
        )

        assert result is not None
        audit = cast(GroundingAudit, result.value)
        assert audit.decision == "reject"
        assert auditor.calls == 1
        assert primary.calls == 0
        trace = service.trace_summary()
        assert trace["task_calls"] == {"topic-grounding-audit": 1}
        event = cast(list[dict[str, object]], trace["events"])[0]
        assert event["role"] == "grounding-verifier"
        assert event["parent_run_id"] == "synthesis-run-1"


def test_grounding_audit_rejects_incomplete_check_coverage() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    synthesis = TopicSynthesis(
        canonical_label="Claude Code pull-request triage workflows",
        aliases=[],
        thesis="Creators demonstrate a repeatable pull-request triage workflow.",
        why_growing=[
            {
                "text": "A stored video shows the workflow.",
                "evidence_refs": ["video:1"],
            },
            {
                "text": "The upload is a stored outlier.",
                "evidence_refs": ["video-snapshot:1"],
            },
        ],
    )
    auditor = FakeProvider(
        {
            "decision": "accept",
            "summary": "The artifact is supported.",
            "checks": [
                {
                    "target": "canonical_label",
                    "verdict": "supported",
                    "rationale": "The video names this workflow.",
                    "evidence_refs": ["video:1"],
                }
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=auditor,
            auditor_provider=auditor,
        )
        result = service.audit_topic_synthesis(
            topic_id="topic-1",
            candidate=_candidate(),
            synthesis=synthesis,
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
            parent_run_id="synthesis-run-1",
        )

        assert result is None
        row = session.scalar(select(LLMIntelligenceRun))
        assert row is not None
        assert row.status == "rejected"
        assert "audit_target_mismatch" in row.validation_json["errors"]


def test_insight_release_audit_cannot_accept_grounded_but_obvious_claim() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    insight = EvidenceInsight(
        topic="AI coding assistants still require human validation",
        statement=(
            "AI coding assistants improve output only when experienced engineers "
            "validate their work."
        ),
        why_non_obvious=(
            "The tools automate code generation, but teams still need engineering judgment."
        ),
        creator_question="How should teams validate AI-generated code?",
        insight_kind="constraint",
        evidence_refs=["video:1", "video-snapshot:1"],
    )
    auditor = FakeProvider(
        {
            "decision": "accept",
            "summary": "The wording is grounded, but it is a generic restatement.",
            "checks": [
                {
                    "target": target,
                    "verdict": "supported",
                    "rationale": "The supplied evidence supports the wording.",
                    "evidence_refs": ["video:1"],
                }
                for target in (
                    "insight.topic",
                    "insight.statement",
                    "insight.why_non_obvious",
                )
            ],
            "non_obviousness": "obvious",
            "decision_value": "adds_context_only",
            "specificity": "broad_claim",
            "generic_restatement": True,
            "decision_change": "The candidate would not change a creator decision.",
            "evidence_refs": ["video:1", "video-snapshot:1"],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            provider=auditor,
            auditor_provider=auditor,
        )
        result = service.audit_evidence_insight(
            workspace_id="workspace-1",
            topic_id="topic-1",
            topic_label="AI coding assistant productivity",
            insight=insight,
            deterministic_metrics={},
            evidence=_evidence(),
            parent_run_id="insight-run-1",
        )

        assert result is None
        row = session.scalar(select(LLMIntelligenceRun))
        assert row is not None
        assert row.status == "rejected"
        assert "invalid_insight_release_accept" in row.validation_json["errors"]


def test_per_task_budget_skips_new_calls_and_records_the_route() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    provider = FakeProvider(
        {
            "canonical_label": "Claude Code pull-request triage workflows",
            "aliases": [],
            "thesis": "Creators demonstrate a repeatable pull-request triage workflow.",
            "why_growing": [
                {
                    "text": "A stored video shows the workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "text": "The upload is a stored outlier.",
                    "evidence_refs": ["video-snapshot:1"],
                },
            ],
        }
    )
    with Session(engine) as session:
        service = LLMIntelligenceService(
            session,
            Settings(
                feature_llm_intelligence=True,
                llm_max_topic_syntheses_per_run=0,
            ),
            provider=provider,
        )
        service.start_trace("pipeline-budget")
        result = service.synthesize_topic(
            topic_id="topic-1",
            candidate=_candidate(),
            evidence=_evidence(),
            deterministic_metrics={"video_count_72h": 3},
        )

        assert result is None
        assert provider.calls == 0
        trace = service.trace_summary()
        event = cast(list[dict[str, object]], trace["events"])[0]
        assert event["status"] == "skipped_task_budget"


def test_reconciliation_guard_never_merges_different_products() -> None:
    left = TopicDefinition(
        key="left",
        label="Claude Code production deployment",
        aliases=(),
        entities=("AI agents", "Claude Code"),
        specificity_score=84,
        facet="production_deployment",
        identity={"domain": "AI agents", "primary_entity": "Claude Code"},
    )
    right = TopicDefinition(
        key="right",
        label="Cursor production deployment",
        aliases=(),
        entities=("AI agents", "Cursor"),
        specificity_score=82,
        facet="production_deployment",
        identity={"domain": "AI agents", "primary_entity": "Cursor"},
    )

    assert TopicIntelligenceService._merge_is_compatible([left, right]) is False


def test_reconciliation_guard_never_merges_different_user_problems() -> None:
    shared_identity = {
        "domain": "AI agents",
        "primary_entity": "Claude Code",
        "audience": "software teams",
        "core_claim": "automate a repeatable workflow",
    }
    deployment = TopicDefinition(
        key="deployment",
        label="Claude Code deployment workflows",
        aliases=(),
        entities=("Claude Code",),
        specificity_score=84,
        facet="workflow",
        identity={**shared_identity, "user_problem": "deploy an application safely"},
    )
    review = TopicDefinition(
        key="review",
        label="Claude Code pull-request review workflows",
        aliases=(),
        entities=("Claude Code",),
        specificity_score=82,
        facet="workflow",
        identity={**shared_identity, "user_problem": "review pull requests consistently"},
    )

    assert TopicIntelligenceService._merge_is_compatible([deployment, review]) is False


def test_rejected_audit_can_release_only_a_supported_canonical_label() -> None:
    audit = GroundingAudit.model_validate(
        {
            "decision": "reject",
            "summary": "The label is supported, but the directional thesis is not.",
            "checks": [
                {
                    "target": "canonical_label",
                    "verdict": "supported",
                    "rationale": "Stored videos use this concrete product and workflow.",
                    "evidence_refs": ["video:1"],
                },
                {
                    "target": "thesis",
                    "verdict": "unsupported",
                    "rationale": "The evidence does not establish a directional shift.",
                    "evidence_refs": ["video:1"],
                },
            ],
        }
    )

    assert TopicIntelligenceService._audit_supports_target(audit, "canonical_label")
    assert not TopicIntelligenceService._audit_supports_target(audit, "thesis")


def test_topic_candidate_bounds_and_deduplicates_evidence_refs() -> None:
    definition = TopicDefinition(
        key="bounded-evidence",
        label="Claude Code workflow evidence",
        aliases=(),
        entities=("Claude Code",),
        specificity_score=80,
        facet="workflow",
    )
    refs = [f"video:{index}" for index in range(30)]
    refs.insert(4, "video:0")

    candidate = TopicIntelligenceService._topic_candidate(definition, refs)

    assert candidate.evidence_refs == [f"video:{index}" for index in range(24)]


def test_reconciliation_batches_compatible_candidates_to_contract_limit() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    provider = EchoPartitionProvider()
    raw_groups: dict[TopicDefinition, list[SimpleNamespace]] = {}
    for index in range(25):
        definition = TopicDefinition(
            key=f"candidate-{index:02d}",
            label=f"Claude Code workflow pattern {index}",
            aliases=(),
            entities=("Claude Code",),
            specificity_score=80,
            facet="workflow",
            identity={"domain": "AI agents", "primary_entity": "Claude Code"},
        )
        raw_groups[definition] = [
            SimpleNamespace(
                video=SimpleNamespace(
                    id=f"video-{index:02d}",
                    title=f"Claude Code workflow pattern {index}",
                    description="Stored workflow evidence.",
                ),
                feature=SimpleNamespace(view_velocity=100 - index),
            )
        ]

    with Session(engine) as session:
        service = TopicIntelligenceService(
            session,
            Settings(feature_llm_intelligence=True),
            llm_provider=provider,
        )
        reconciled = service._reconcile_topic_groups(cast(dict, raw_groups))

    assert len(reconciled) == 25
    assert provider.calls == 2
    assert all(
        len(cast(list[object], payload["required_candidate_keys"])) <= 12
        for payload in provider.payloads
    )


def test_topic_persistence_coalesces_duplicate_identity_and_video_membership() -> None:
    first = TopicDefinition(
        key="same-topic",
        label="First label",
        aliases=("First alias",),
        entities=("Claude Code",),
        specificity_score=80,
        facet="workflow",
    )
    duplicate_identity = TopicDefinition(
        key="same-topic",
        label="Second label",
        aliases=("Second alias",),
        entities=("coding agents",),
        specificity_score=78,
        facet="workflow",
    )
    lower_score = SimpleNamespace(
        video=SimpleNamespace(id="video-1"),
        feature=SimpleNamespace(view_velocity=100),
        assignment_score=0.7,
    )
    higher_score = SimpleNamespace(
        video=SimpleNamespace(id="video-1"),
        feature=SimpleNamespace(view_velocity=120),
        assignment_score=0.9,
    )
    second_video = SimpleNamespace(
        video=SimpleNamespace(id="video-2"),
        feature=SimpleNamespace(view_velocity=80),
        assignment_score=0.8,
    )

    coalesced = TopicIntelligenceService._coalesce_persistence_groups(
        {
            first: [lower_score],
            duplicate_identity: [higher_score, second_video],
        }
    )

    assert len(coalesced) == 1
    definition, videos = next(iter(coalesced.items()))
    assert definition.key == "same-topic"
    assert definition.aliases == ("First alias", "Second alias")
    assert {item.video.id for item in videos} == {"video-1", "video-2"}
    assert next(item for item in videos if item.video.id == "video-1") is higher_score
