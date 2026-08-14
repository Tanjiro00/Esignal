from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from apps.api import main as api_main
from apps.api.database import get_db
from apps.api.demo import DEMO_WORKSPACE_ID
from apps.api.main import app
from apps.api.models import (
    Base,
    CommentTopicRelevance,
    CommentTopicRelevanceEvent,
    DemandCluster,
    DiscoveryQueryRecord,
    DiscoveryRun,
    ProductEvent,
    ProviderFetch,
    QuerySuggestion,
    SignalReview,
    Topic,
    TopicContentGap,
    TopicContentPattern,
    TopicSnapshot,
    TopicSnapshotBucket,
    VideoSnapshot,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.api.seed import seed_demo
from apps.api.snapshot_buckets import backfill_snapshot_buckets


@pytest.fixture
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as session:
        seed_demo(session)
    return factory


@pytest.fixture
def client(session_factory: sessionmaker[Session]) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_readiness_checks_database_and_worker_state(client: TestClient) -> None:
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "ready"
    assert response.json()["stale_topic_runs"] == 0


def test_demo_seed_matches_slice_one_inventory(
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as session:
        assert session.scalar(select(func.count(Topic.id))) == 5
        assert session.scalar(select(func.count(YoutubeChannel.id))) == 50
        assert session.scalar(select(func.count(YoutubeVideo.id))) == 300
        assert session.scalar(select(func.count(VideoSnapshot.id))) == 1200
        assert session.scalar(select(func.count(DemandCluster.id))) == 5
        assert session.scalar(select(func.count(ProviderFetch.id))) == 4
        assert session.scalar(select(func.count(TopicContentPattern.id))) == 15
        assert session.scalar(select(func.count(TopicContentGap.id))) == 15


def test_microtopic_content_gap_contract_is_feature_gated(
    client: TestClient,
    monkeypatch,
) -> None:
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    signal_id = feed.json()["items"][0]["id"]
    disabled = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}")
    assert disabled.status_code == 200
    assert disabled.json()["content_gap_map"] is None

    monkeypatch.setattr(api_main.settings, "feature_microtopic_content_gap", True)
    enabled = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}")
    assert enabled.status_code == 200
    body = enabled.json()
    assert body["topic"]["clustering_version"] == "demo-microtopic-v5"
    assert body["topic"]["specificity_score"] >= 70
    assert body["topic"]["thesis_support_ratio"] >= 0.8
    assert body["content_gap_map"]["pattern_version"] == "topic-content-pattern-v1"
    assert body["content_gap_map"]["gap_version"] == "content-gap-v4"
    assert body["content_gap_map"]["ranking_version"] == "opportunity-ranking-v5"
    assert len(body["content_gap_map"]["patterns"]) == 3
    assert len(body["content_gap_map"]["gaps"]) == 3
    primary = body["content_angles"][0]
    assert primary["occupied_pattern"]
    assert primary["open_gap"]["is_open"] is True
    assert primary["differentiation"]
    assert primary["why_primary"]


def test_decision_feedback_and_point_in_time_evaluation_contract(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_feedback_evaluation", True)
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()
    signal = feed["items"][0]
    detail = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal['id']}").json()
    opportunity_id = detail["content_angles"][0]["opportunity_id"]

    feedback = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal['id']}/actions",
        json={
            "action": "act",
            "reason": "clear_angle",
            "comment": "Works if the original test stays inside one production day.",
            "opportunity_id": opportunity_id,
        },
    )
    assert feedback.status_code == 201
    assert feedback.json()["reason"] == "clear_angle"
    assert feedback.json()["comment"].startswith("Works if")
    assert feedback.json()["opportunity_id"] == opportunity_id
    assert feedback.json()["feedback_version"] == "decision-feedback-v1"

    invalid = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal['id']}/actions",
        json={"action": "act", "reason": "not_relevant"},
    )
    assert invalid.status_code == 422

    candidates = client.get("/api/v1/admin/evaluation/candidates?source=demo&limit=100")
    assert candidates.status_code == 200
    candidate_body = candidates.json()
    assert candidate_body["total"] == 5
    assert len(candidate_body["items"]) == 5
    topic_id = candidate_body["items"][0]["topic_id"]

    label = client.post(
        f"/api/v1/admin/evaluation/topics/{topic_id}/label",
        json={
            "workspace_id": DEMO_WORKSPACE_ID,
            "label": "true_early_signal",
            "additional_labels": [
                "demand_relevant",
                "opportunity_actionable",
                "fit_correct",
            ],
            "notes": "Independent evidence and the open content cell are actionable.",
        },
    )
    assert label.status_code == 200
    label_body = label.json()
    assert label_body["label_version"] == "manual-topic-evaluation-v1"
    assert label_body["evidence_snapshot"]["point_in_time"] is True
    assert label_body["evidence_snapshot"]["future_measurements_included"] is False
    assert label_body["evidence_snapshot"]["signal_rank"] <= 5

    repeated = client.post(
        f"/api/v1/admin/evaluation/topics/{topic_id}/label",
        json={
            "workspace_id": DEMO_WORKSPACE_ID,
            "label": "true_but_late",
            "additional_labels": ["opportunity_generic"],
            "notes": "Updated expert judgment without changing the frozen snapshot.",
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == label_body["id"]
    assert repeated.json()["evidence_snapshot"]["as_of"] == label_body["evidence_snapshot"]["as_of"]

    report = client.get(f"/api/v1/admin/evaluation/report?workspace_id={DEMO_WORKSPACE_ID}")
    assert report.status_code == 200
    assert report.json()["reviewed_topics"] == 1
    assert report.json()["production_weights_changed"] is False
    assert report.json()["decision_feedback"]["action_counts"]["act"] >= 1

    jsonl = client.get(
        f"/api/v1/admin/evaluation/export?format=jsonl&workspace_id={DEMO_WORKSPACE_ID}"
    )
    csv_feedback = client.get(
        f"/api/v1/admin/evaluation/feedback/export?format=csv&workspace_id={DEMO_WORKSPACE_ID}"
    )
    assert jsonl.status_code == 200
    assert '"label": "true_but_late"' in jsonl.text
    assert csv_feedback.status_code == 200
    assert "clear_angle" in csv_feedback.text


def test_snapshot_bucket_backfill_preserves_raw_measurements(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    with session_factory() as session:
        raw_count = session.scalar(select(func.count(TopicSnapshot.id)))
        result = backfill_snapshot_buckets(
            session,
            captured_at=datetime.now(tz=UTC),
            source_kind="demo",
        )
        session.commit()
        assert result["topics"] == 5
        assert result["buckets"] >= 5
        assert session.scalar(select(func.count(TopicSnapshot.id))) == raw_count
        assert session.scalar(select(func.count(TopicSnapshotBucket.id))) == result["buckets"]

    monkeypatch.setattr(api_main.settings, "feature_topic_snapshot_buckets", True)
    signal_id = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()["items"][0][
        "id"
    ]
    detail = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}")
    assert detail.status_code == 200
    assert detail.json()["timeline"]


def test_channel_feasibility_v2_uses_absolute_publish_by_and_blocks_act(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_decision_experience", True)
    monkeypatch.setattr(
        api_main.settings,
        "feature_channel_profile_feasibility_v2",
        True,
    )
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()
    details = [
        client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{item['id']}").json()
        for item in feed["items"]
    ]

    assert all(item["decision_card"]["recommended_publish_by"] for item in details)
    assert all(
        item["decision_card"]["recommended_publish_by_label"]
        in item["decision_card"]["publishing_window"]["label"]
        for item in details
    )
    infeasible = [item for item in details if item["decision_card"]["feasibility"] == "Infeasible"]
    assert infeasible
    assert all(item["decision_card"]["decision"] != "Act" for item in infeasible)
    assert all(item["decision_card"]["infeasibility_reasons"] for item in infeasible)
    assert all(
        item["decision_card"]["decay_version"] == "creator-specific-opportunity-decay-v1"
        for item in details
    )


def test_demo_response_keeps_fixed_seed_windows_current_without_mutating_seed(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_decision_experience", True)
    monkeypatch.setattr(api_main.settings, "feature_channel_profile_feasibility_v2", True)

    items = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()["items"]
    open_items = [
        item
        for item in items
        if item["decision_card"]["release_ready"]
        and item["decision_card"]["decision"] != "Skip"
        and item["current_action"] is None
    ]

    assert open_items
    assert all(
        datetime.fromisoformat(item["opportunity_window"]["end"].replace("Z", "+00:00"))
        > datetime.now(tz=UTC)
        for item in open_items
    )
    assert all(
        datetime.fromisoformat(
            item["decision_card"]["recommended_publish_by"].replace("Z", "+00:00")
        )
        > datetime.now(tz=UTC)
        for item in open_items
    )


def test_signal_to_brief_to_outcome_loop(client: TestClient) -> None:
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    assert feed.status_code == 200
    items = feed.json()["items"]
    assert len(items) == 5
    assert feed.json()["data_mode"] == "demo"
    assert feed.json()["available_modes"] == ["demo"]
    signal_id = items[0]["id"]

    detail = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}")
    assert detail.status_code == 200
    body = detail.json()
    assert body["evidence_videos"]
    assert body["transcript_evidence"]
    assert body["transcript_evidence"][0]["segments"]
    assert len(body["transcript_evidence"][0]["segments"][0]["text"]) <= 280
    assert "full_text" not in str(body)
    assert body["demand_clusters"][0]["snippets"]
    assert body["demand_clusters"][0]["evidence_strength"] == "Strong"
    assert body["demand_clusters"][0]["snippets"][0]["video_title"]
    assert body["score_components"]["momentum"] <= 100
    assert body["provenance"][0]["provider"] == "mock_metadata"
    fit_components = body["channel_fit_detail"]
    assert {
        "topical_relevance",
        "audience_overlap",
        "format_compatibility",
        "authority_or_credibility",
        "production_feasibility",
        "historical_performance_similarity",
        "timing_feasibility",
        "cannibalization_penalty",
        "brand_risk_penalty",
    }.issubset(fit_components)
    opportunity = body["content_angles"][1]
    assert opportunity["opportunity_id"]
    assert opportunity["best_publish_window"]["label"]
    assert opportunity["production_time_days"]["max"] >= 1

    action = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/actions",
        json={"action": "save", "reason": "strong_fit"},
    )
    assert action.status_code == 201
    assert action.json()["action"] == "save"

    brief = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/briefs",
        json={
            "angle_index": 1,
            "opportunity_id": opportunity["opportunity_id"],
        },
    )
    assert brief.status_code == 201
    brief_body = brief.json()
    assert brief_body["brief_json"]["evidence"]
    assert brief_body["opportunity_id"] == opportunity["opportunity_id"]
    assert brief_body["evidence_version"].endswith(":channel-fit-v1")

    same_brief = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/briefs",
        json={
            "angle_index": 1,
            "opportunity_id": opportunity["opportunity_id"],
        },
    )
    assert same_brief.status_code == 201
    assert same_brief.json()["id"] == brief_body["id"]

    outcome = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes",
        json={
            "signal_id": signal_id,
            "content_brief_id": brief_body["id"],
            "youtube_video_id": "demo-published-123",
            "published_at": "2026-07-27T12:00:00Z",
            "baseline_definition": "Median seven-day views across 12 uploads",
            "performance_json": {},
            "success_status": "pending",
            "user_notes": "Integration test",
        },
    )
    assert outcome.status_code == 201
    assert outcome.json()["content_brief_id"] == brief_body["id"]


def test_seeded_outcome_exposes_comparator_methodology(client: TestClient) -> None:
    outcomes = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes")

    assert outcomes.status_code == 200
    seeded = next(item for item in outcomes.json() if item["youtube_video_id"] == "esoutcome001")
    comparator = seeded["performance_json"]["comparator"]
    assert seeded["metrics_version"] == "outcome-metrics-v2"
    assert seeded["performance_json"]["views_24h"] == 284_000
    assert seeded["performance_json"]["baseline_views_24h"] == 142_000
    assert comparator["sample_size_24h"] == 8
    assert comparator["minimum_stable_sample_size"] == 5
    assert comparator["stability_24h"] == "stable"
    assert comparator["filters"]["upload_period_days"] == 180


def test_outcome_suggestion_confirm_and_unlink_are_auditable(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_outcome_suggestions", True)
    suggestions = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes/suggestions")
    assert suggestions.status_code == 200
    suggestion = suggestions.json()[0]
    assert suggestion["status"] == "suggested"
    assert suggestion["match_confidence"] > 0.8
    assert suggestion["baseline"]["sample_size"] >= 3

    confirmed = client.post(
        (f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes/suggestions/{suggestion['id']}/confirm"),
        json={},
    )
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "confirmed"
    outcome_id = confirmed.json()["outcome_id"]
    assert outcome_id

    outcomes_response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes")
    linked = next(item for item in outcomes_response.json() if item["id"] == outcome_id)
    assert linked["performance_json"]["interpretation"] == "associated_uplift_not_causal"
    assert linked["performance_json"]["comparator"]["filters"]["upload_period_days"] == 180
    assert linked["metrics_version"] == "outcome-metrics-v2"
    assert linked["link_status"] == "active"

    unlinked = client.post(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes/{outcome_id}/unlink")
    assert unlinked.status_code == 200
    assert unlinked.json()["link_status"] == "unlinked"
    active_ids = {
        item["id"] for item in client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes").json()
    }
    assert outcome_id not in active_ids


def test_outcome_suggestion_can_be_rejected_in_one_click(
    client: TestClient,
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_outcome_suggestions", True)
    suggestion = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes/suggestions").json()[
        0
    ]
    response = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/outcomes/suggestions/{suggestion['id']}/reject"
    )
    assert response.status_code == 200
    assert response.json()["status"] == "rejected"


def test_packaging_is_created_only_for_selected_opportunity_and_tracks_copy(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_signal_packaging", True)
    briefs = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/briefs").json()
    brief = next(item for item in briefs if item["opportunity_id"])
    route = (
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{brief['signal_id']}/packaging"
        f"?opportunity_id={brief['opportunity_id']}"
    )

    packaging = client.get(route)
    assert packaging.status_code == 200
    body = packaging.json()
    assert body["content_brief_id"] == brief["id"]
    assert len(body["packaging"]["title_directions"]) == 10
    assert len({item["strategy"] for item in body["packaging"]["title_directions"]}) == 10
    assert body["packaging"]["full_script_generated"] is False
    original_hooks = body["packaging"]["hook_directions"]

    regenerated = client.post(
        route.replace("/packaging?", "/packaging/regenerate?"),
        json={"section": "title_directions"},
    )
    assert regenerated.status_code == 200
    assert regenerated.json()["packaging"]["hook_directions"] == original_hooks
    assert regenerated.json()["regeneration_counts"]["title_directions"] == 1

    copied = client.post(
        route.replace("/packaging?", "/packaging/copy?"),
        json={"section": "title_directions", "item_index": 0},
    )
    assert copied.status_code == 204
    with session_factory() as session:
        assert (
            session.scalar(
                select(func.count(ProductEvent.id)).where(
                    ProductEvent.event_type == "packaging_copy"
                )
            )
            == 1
        )


def test_earlyness_history_api_is_feature_gated_and_evidence_backed(
    client: TestClient,
    monkeypatch,
) -> None:
    feed_without_flag = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    assert feed_without_flag.status_code == 200
    assert all(item["earlyness"] is None for item in feed_without_flag.json()["items"])
    signal_id = feed_without_flag.json()["items"][0]["id"]
    disabled = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/earlyness")
    assert disabled.status_code == 404

    monkeypatch.setattr(api_main.settings, "feature_earlyness_timeline", True)
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    first = feed.json()["items"][0]
    assert first["earlyness"]["claim_kind"] in {"early", "pending", "late"}
    assert first["earlyness"]["headline"]

    response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{first['id']}/earlyness")
    assert response.status_code == 200
    body = response.json()
    assert body["data_mode"] == "demo"
    assert body["large_channel_threshold_subscribers"] == 100_000
    assert body["transitions"]
    assert body["milestones"][0]["label"] == "First detected"
    assert all(item["evidence_id"] for item in body["milestones"] if item["occurred_at"])

    detail = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{first['id']}")
    assert detail.status_code == 200
    assert detail.json()["earlyness"]["headline"] == body["headline"]


def test_human_review_queue_gates_visibility_and_preserves_audit(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    queue_path = f"/api/v1/admin/review/signals?workspace_id={DEMO_WORKSPACE_ID}"
    assert client.get(queue_path).status_code == 404
    assert len(client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()["items"]) == 5

    monkeypatch.setattr(api_main.settings, "feature_signal_review_queue", True)
    queue = client.get(f"{queue_path}&source=demo")
    assert queue.status_code == 200
    queue_body = queue.json()
    assert queue_body["total"] == 5
    assert queue_body["metrics"]["status_counts"]["approved"] == 5
    assert queue_body["metrics"]["approval_rate"] == 100
    assert "needs_review" in queue_body["filters"]["statuses"]
    assert "false_topic_merge" in queue_body["filters"]["reasons"]
    assert queue_body["filters"]["sources"] == ["demo"]
    first_id = queue_body["items"][0]["signal_id"]
    second_id = queue_body["items"][1]["signal_id"]

    with session_factory() as session:
        review = session.scalar(
            select(SignalReview).where(
                SignalReview.workspace_id == DEMO_WORKSPACE_ID,
                SignalReview.signal_id == first_id,
            )
        )
        assert review is not None
        review.status = "needs_review"
        review.reviewer_id = None
        review.primary_reason = None
        review.reason_codes_json = []
        review.first_reviewed_at = None
        review.decided_at = None
        session.commit()

    gated_feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    assert gated_feed.status_code == 200
    assert len(gated_feed.json()["items"]) == 4
    assert (
        client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{first_id}").status_code == 404
    )

    review_detail_path = f"/api/v1/admin/review/signals/{first_id}?workspace_id={DEMO_WORKSPACE_ID}"
    review_detail = client.get(review_detail_path)
    assert review_detail.status_code == 200
    detail_body = review_detail.json()
    assert detail_body["review"]["status"] == "needs_review"
    assert detail_body["signal"]["evidence_videos"]
    assert detail_body["decision_card_preview"]["topic_label"]
    assert detail_body["audit_history"][0]["event_type"] == "auto_approved_demo"

    action_path = (
        f"/api/v1/admin/review/signals/{first_id}/actions?workspace_id={DEMO_WORKSPACE_ID}"
    )
    edited_thesis = "Reviewer-confirmed thesis grounded in the selected stored evidence."
    edit = client.post(
        action_path,
        json={
            "action": "edit_thesis",
            "thesis": edited_thesis,
            "note": "Clarified the decision claim.",
            "idempotency_key": "review-edit-thesis-integration",
        },
    )
    assert edit.status_code == 200
    assert edit.json()["to_status"] == "needs_review"
    assert edit.json()["changes"]["thesis"] == edited_thesis

    approval_payload = {
        "action": "approve",
        "reason_codes": ["other"],
        "note": "Independent evidence and demand checked.",
        "idempotency_key": "review-approve-integration",
    }
    approved = client.post(action_path, json=approval_payload)
    repeated = client.post(action_path, json=approval_payload)
    assert approved.status_code == 200
    assert repeated.status_code == 200
    assert approved.json()["id"] == repeated.json()["id"]
    assert approved.json()["to_status"] == "approved"
    assert approved.json()["reviewer_name"] == "Avery Chen"

    visible_feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    assert len(visible_feed.json()["items"]) == 5
    visible_item = next(item for item in visible_feed.json()["items"] if item["id"] == first_id)
    assert visible_item["thesis"] == edited_thesis
    visible_detail = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{first_id}")
    assert visible_detail.status_code == 200
    assert visible_detail.json()["thesis"] == edited_thesis

    reject_path = (
        f"/api/v1/admin/review/signals/{second_id}/actions?workspace_id={DEMO_WORKSPACE_ID}"
    )
    missing_reason = client.post(
        reject_path,
        json={
            "action": "reject",
            "idempotency_key": "review-reject-without-reason",
        },
    )
    assert missing_reason.status_code == 422
    rejected = client.post(
        reject_path,
        json={
            "action": "reject",
            "reason_codes": ["too_broad"],
            "note": "The stored evidence combines distinct jobs to be done.",
            "idempotency_key": "review-reject-integration",
        },
    )
    assert rejected.status_code == 200
    assert rejected.json()["to_status"] == "rejected"
    assert len(client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()["items"]) == 4

    updated_queue = client.get(queue_path).json()
    assert updated_queue["metrics"]["status_counts"]["rejected"] == 1
    assert updated_queue["metrics"]["rejection_reasons"]["too_broad"] == 1
    assert updated_queue["metrics"]["approval_rate"] == 80
    history = client.get(review_detail_path).json()["audit_history"]
    assert [event["event_type"] for event in history[:2]] == ["approve", "edit_thesis"]

    # There is intentionally no bulk-approval contract.
    assert client.post(
        f"/api/v1/admin/review/signals/bulk-approve?workspace_id={DEMO_WORKSPACE_ID}",
        json={},
    ).status_code in {404, 405}


def test_comment_relevance_admin_override_is_feature_gated_and_audited(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()
    signal_id = feed["items"][0]["id"]
    review_path = f"/api/v1/admin/review/signals/{signal_id}?workspace_id={DEMO_WORKSPACE_ID}"
    assert (
        client.post(
            "/api/v1/admin/demand/reclassify",
            json={},
        ).status_code
        == 404
    )

    monkeypatch.setattr(api_main.settings, "feature_signal_review_queue", True)
    monkeypatch.setattr(api_main.settings, "feature_comment_topic_relevance", True)
    detail = client.get(review_path)
    assert detail.status_code == 200
    relevance_rows = detail.json()["comment_relevance"]
    assert len(relevance_rows) == 3
    first = relevance_rows[0]
    assert first["effective_relevant"] is True
    assert first["video_url"].startswith("https://")
    assert first["model_version"] == "comment-topic-relevance-v1"

    override_path = (
        f"/api/v1/admin/demand/relevance/{first['id']}/override?workspace_id={DEMO_WORKSPACE_ID}"
    )
    payload = {
        "decision": False,
        "reason": "The comment asks about a different claim.",
        "idempotency_key": "comment-relevance-override-integration",
    }
    overridden = client.post(override_path, json=payload)
    repeated = client.post(override_path, json=payload)
    assert overridden.status_code == 200
    assert repeated.status_code == 200
    assert overridden.json()["effective_relevant"] is False
    assert overridden.json()["override_decision"] is False

    with session_factory() as session:
        row = session.get(CommentTopicRelevance, first["id"])
        assert row is not None
        assert row.override_decision is False
        assert (
            session.scalar(
                select(func.count(CommentTopicRelevanceEvent.id)).where(
                    CommentTopicRelevanceEvent.relevance_id == first["id"],
                    CommentTopicRelevanceEvent.event_type == "manual_override",
                )
            )
            == 1
        )


def test_channel_profile_can_be_reviewed_and_updated(
    client: TestClient,
    monkeypatch,
) -> None:
    path = f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/channel-profile"
    profile = client.get(path)
    assert profile.status_code == 200
    body = profile.json()
    assert body["channel_title"] == "Atlas Labs"
    assert body["profile_source"] == "demo"
    assert body["topic_keywords"]
    assert body["profile_version"] == "channel-profile-v4-quality"
    assert body["core_topics"]
    assert body["preferred_formats"]
    assert isinstance(body["successful_formats"], list)
    assert "http" not in " ".join(body["core_topics"]).lower()

    def fail_follow_up_refresh(*_args, **_kwargs):
        raise RuntimeError("simulated topic refresh failure")

    monkeypatch.setattr(
        api_main.TopicIntelligenceService,
        "run",
        fail_follow_up_refresh,
    )
    updated = client.put(
        path,
        json={
            "audience_description": "Builders choosing practical AI tools.",
            "geography": "US",
            "language": "en",
            "topic_keywords": ["AI agents", "local AI", "automation"],
            "preferred_formats": ["Hands-on test", "Structured comparison"],
            "creator_expertise": ["AI tools", "software testing"],
            "production_capabilities": ["screen recording", "benchmarking"],
            "exclusions": ["unverified medical advice"],
            "strategic_goals": ["publish original evidence"],
            "normal_duration_min_seconds": 600,
            "normal_duration_max_seconds": 1800,
            "production_days_min": 2,
            "production_days_max": 6,
            "core_topics": ["AI agents", "local AI"],
            "adjacent_topics": ["creator automation"],
            "audience_sophistication": "advanced",
            "creator_authority": "expert",
            "risk_tolerance": "conservative",
            "team_size": 2,
            "research_capacity_hours": 12,
            "filming_required": False,
            "external_guests_required": False,
            "editing_complexity": "high",
            "access_to_products": ["AI software"],
            "experiment_level": "balanced",
            "evergreen_trend_balance": 0.4,
            "weekday_publish_only": True,
            "content_calendar": [{"date": "2026-08-04", "status": "blocked"}],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["profile_source"] == "user"
    assert updated.json()["production_days_min"] == 2
    assert updated.json()["topic_keywords"] == [
        "AI agents",
        "local AI",
        "automation",
    ]
    assert updated.json()["core_topics"] == ["AI agents", "local AI"]
    assert updated.json()["team_size"] == 2
    assert updated.json()["editing_complexity"] == "high"
    assert updated.json()["explicit_overrides"]["core_topics"] == [
        "AI agents",
        "local AI",
    ]


def test_youtube_oauth_is_optional_and_reports_unconfigured_status(
    client: TestClient,
) -> None:
    status = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/oauth/youtube")
    assert status.status_code == 200
    assert status.json()["connected"] is False
    assert status.json()["configured"] is False
    assert status.json()["analytics_video_count"] == 0


def test_query_expansion_requires_review_tracks_precision_and_is_bounded(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_query_expansion", True)
    first_run = client.post("/api/v1/admin/query-expansion/run")
    assert first_run.status_code == 200
    assert 1 <= first_run.json()["suggestions_created"] <= 10
    assert first_run.json()["pending_suggestions"] <= 50

    suggestions = client.get("/api/v1/admin/query-suggestions").json()
    assert suggestions
    assert all(item["source_entity"] for item in suggestions)
    assert all(item["source_topic_id"] for item in suggestions)
    assert all(item["source_evidence_ids"] for item in suggestions)
    assert all(item["rationale"] for item in suggestions)
    assert all(item["anchor_terms"] for item in suggestions)
    assert all(item["status"] == "suggested" for item in suggestions)

    suggestion = suggestions[0]
    approved = client.post(
        f"/api/v1/admin/query-suggestions/{suggestion['id']}/actions",
        json={"action": "approve"},
    )
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    query_id = approved.json()["discovery_query_id"]
    with session_factory() as session:
        query_row = session.get(DiscoveryQueryRecord, query_id)
        assert query_row is not None
        assert query_row.active is False

    activated = client.post(
        f"/api/v1/admin/query-suggestions/{suggestion['id']}/actions",
        json={"action": "activate"},
    )
    assert activated.status_code == 200
    assert activated.json()["status"] == "active"

    with session_factory() as session:
        query_row = session.get(DiscoveryQueryRecord, query_id)
        assert query_row is not None and query_row.active is True
        now = datetime.now(tz=UTC)
        session.add(
            DiscoveryRun(
                id="query-expansion-low-value-run",
                query_id=query_id,
                channel_id=None,
                provider="test",
                idempotency_key="query-expansion-low-value-run",
                started_at=now,
                completed_at=now,
                status="success",
                result_count=100,
                unique_video_count=100,
                retained_video_count=5,
                estimated_cost=0,
                error_code=None,
                error_message=None,
            )
        )
        session.commit()

    precision_run = client.post("/api/v1/admin/query-expansion/run")
    assert precision_run.status_code == 200
    assert precision_run.json()["low_value_queries_demoted"] >= 1
    with session_factory() as session:
        query_row = session.get(DiscoveryQueryRecord, query_id)
        suggestion_row = session.get(QuerySuggestion, suggestion["id"])
        assert query_row is not None and suggestion_row is not None
        assert query_row.active is False
        assert query_row.quality_status == "low_value"
        assert query_row.precision_score == 5
        assert suggestion_row.status == "low_value"

    repeated = client.post("/api/v1/admin/query-expansion/run")
    assert repeated.status_code == 200
    all_suggestions = client.get("/api/v1/admin/query-suggestions").json()
    assert len(all_suggestions) <= 20
    assert len({item["normalized_query"] for item in all_suggestions}) == len(all_suggestions)


def test_provider_payload_can_be_inspected_and_replayed(client: TestClient) -> None:
    providers = client.get("/api/v1/admin/providers")
    assert providers.status_code == 200
    assert all(row["demo"] for row in providers.json())
    assert all("spent_today_usd" in row for row in providers.json())
    assert all("fallback_rate" in row for row in providers.json())

    fetches = client.get("/api/v1/admin/provider-fetches")
    fetch_id = fetches.json()[0]["id"]
    detail = client.get(f"/api/v1/admin/provider-fetches/{fetch_id}")
    assert detail.status_code == 200
    assert detail.json()["raw_payload"]["demo"] is True

    replay = client.post(f"/api/v1/admin/provider-fetches/{fetch_id}/replay")
    assert replay.status_code == 201
    assert replay.json()["raw_payload_hash"] == detail.json()["raw_payload_hash"]
    assert replay.json()["actual_cost"] == 0


def test_provider_controls_and_routing_metrics_are_exposed(client: TestClient) -> None:
    providers = client.get("/api/v1/admin/providers").json()
    target = providers[0]
    path = f"/api/v1/admin/providers/{target['provider']}/{target['capability']}"

    disabled = client.patch(path, json={"enabled": False})
    assert disabled.status_code == 200
    assert disabled.json()["status"] == "Disabled"
    assert disabled.json()["disabled_reason"] == "Disabled by administrator"

    enabled = client.patch(path, json={"enabled": True, "priority": 3})
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True
    assert enabled.json()["priority"] == 3

    metrics = client.get("/api/v1/admin/provider-routing/metrics")
    assert metrics.status_code == 200
    assert metrics.json()["fallback_rate"] == 0


def test_video_intelligence_metrics_are_available_in_demo_mode(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/admin/video-intelligence/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["live_videos"] == 0
    assert body["snapshot_coverage_percent"] == 0
    assert body["snapshot_lag_seconds"] == 0


def test_onboarding_digest_and_product_analytics_contracts(
    client: TestClient,
) -> None:
    context = client.get("/api/v1/context")
    assert context.status_code == 200
    assert context.json()["workspace_id"] == DEMO_WORKSPACE_ID

    onboarding = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/onboarding")
    assert onboarding.status_code == 200
    onboarding_body = onboarding.json()
    assert onboarding_body["status"] == "completed"
    assert onboarding_body["progress_percent"] == 100
    assert onboarding_body["owned_channel"]["title"] == "Atlas Labs"
    assert onboarding_body["owned_channel"]["profile_confirmed"] is True
    assert "channel_profile" in onboarding_body["completed_steps"]
    assert all(item["complete"] for item in onboarding_body["readiness"])

    channels = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/channels")
    assert channels.status_code == 200
    assert any(item["relationship"] == "owned" for item in channels.json())
    assert any(item["relationship"] in {"competitor", "reference"} for item in channels.json())

    digest = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/digest/latest")
    assert digest.status_code == 200
    digest_body = digest.json()
    assert digest_body["status"] == "delivered"
    assert len(digest_body["content"]["items"]) == 3
    assert all(item["evidence_videos"] for item in digest_body["content"]["items"])
    assert all(len(item["demand"]["question"]) <= 220 for item in digest_body["content"]["items"])
    assert all(
        item["suggested_decision"] in {"Act", "Watch", "Skip"}
        for item in digest_body["content"]["items"]
    )

    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()
    signal_id = feed["items"][0]["id"]
    event_payload = {
        "event_type": "signal_open",
        "event_key": "integration-signal-open-contract",
        "signal_id": signal_id,
        "metadata": {"surface": "integration_test"},
    }
    first_event = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/analytics/events",
        json=event_payload,
    )
    repeated_event = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/analytics/events",
        json=event_payload,
    )
    assert first_event.status_code == 201
    assert repeated_event.status_code == 201
    assert repeated_event.json()["id"] == first_event.json()["id"]

    analytics = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/analytics/summary")
    assert analytics.status_code == 200
    analytics_body = analytics.json()
    assert analytics_body["period_days"] == 30
    assert analytics_body["north_star"]["value"] >= 1
    assert {item["key"] for item in analytics_body["funnel"]} == {
        "impressions",
        "opened",
        "saved",
        "dismissed",
        "briefs",
        "published",
        "successful",
    }
    assert any(item["event_type"] == "signal_open" for item in analytics_body["recent_activity"])


def test_ux_simplification_contracts_are_additive_and_persist_actions(
    client: TestClient,
    session_factory: sessionmaker[Session],
) -> None:
    context_response = client.get("/api/v1/context")
    assert context_response.status_code == 200
    context = context_response.json()
    assert context["role"] == "owner"
    assert context["is_admin"] is True
    assert set(context["features"]) >= {
        "ux_today_home_v1",
        "ux_decision_card_v1",
        "ux_simple_scores_v1",
        "ux_simplified_navigation_v1",
        "ux_onboarding_v2",
        "ux_opportunity_detail_v2",
        "ux_brief_v2",
        "ux_results_v2",
    }

    feed = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals").json()
    signal_id = feed["items"][0]["id"]
    decision = client.get(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/opportunities/{signal_id}/decision-card"
    )
    assert decision.status_code == 200
    assert decision.json()["decision"] in {"Act", "Watch", "Skip"}
    assert decision.json()["recommended_video"]
    assert decision.json()["release_ready"] is True
    assert decision.json()["insight_status"] == "evidence_backed"
    assert decision.json()["insight_statement"]
    assert decision.json()["main_risk"]

    for index, event_type in enumerate(
        (
            "today_opened",
            "opportunity_card_viewed",
            "opportunity_opened",
            "why_recommended_opened",
            "evidence_opened",
            "technical_details_opened",
            "act_clicked",
            "decision_reason_selected",
            "brief_shared",
            "result_opened",
            "onboarding_started",
            "onboarding_step_completed",
        )
    ):
        response = client.post(
            f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/analytics/events",
            json={
                "event_type": event_type,
                "event_key": f"ux-contract-{index:02d}",
                "signal_id": signal_id,
                "metadata": {"surface": "integration_test"},
            },
        )
        assert response.status_code == 201

    action = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/actions",
        json={
            "action": "act",
            "reason": "clear_angle",
            "production_days": 4,
            "target_publish_date": "2026-08-01T12:00:00Z",
        },
    )
    assert action.status_code == 201
    brief = client.post(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal_id}/briefs",
        json={"angle_index": 0},
    )
    assert brief.status_code == 201
    production = client.patch(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/briefs/{brief.json()['id']}",
        json={"status": "in_production"},
    )
    assert production.status_code == 200
    assert production.json()["status"] == "in_production"

    channels = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/channels").json()
    reference = next(item for item in channels if item["relationship"] != "owned")
    paused = client.patch(
        f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/channels/{reference['channel_id']}",
        json={"active": False},
    )
    assert paused.status_code == 200
    assert paused.json()["active"] is False

    analytics = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/analytics/summary")
    assert analytics.status_code == 200
    assert analytics.json()["ux"]["events"]["today_opened"] == 1
    assert analytics.json()["ux"]["events"]["production_started"] == 1

    with session_factory() as session:
        action_event = next(
            (
                event
                for event in session.scalars(
                    select(ProductEvent).where(ProductEvent.event_type == "signal_act")
                )
                if event.metadata_json.get("production_days") == 4
            ),
            None,
        )
        assert action_event is not None
        assert action_event.metadata_json["production_days"] == 4
        assert action_event.metadata_json["target_publish_date"].startswith("2026-08-01")


def test_decision_experience_contract_and_actions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_decision_experience", True)

    feed_response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals")
    assert feed_response.status_code == 200
    feed = feed_response.json()
    assert feed["items"]
    signal = feed["items"][0]
    card = signal["decision_card"]
    assert card["decision"] in {"Act", "Watch", "Skip"}
    assert card["decision_label"] in {"ACT NOW", "WATCH", "SKIP"}
    assert card["signal_strength"]["label"] in {
        "Low",
        "Moderate",
        "High",
        "Very high",
    }
    assert card["signal_strength"]["reason_codes"]
    assert card["recommended_video"]
    assert card["release_ready"] is True
    assert card["insight_status"] == "evidence_backed"
    assert card["insight_reason_codes"]
    assert card["main_risk"]
    assert "/100" not in card["why_this_channel"]

    detail_response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal['id']}")
    assert detail_response.status_code == 200
    detail = detail_response.json()
    assert detail["decision_card"]["decision_version"] == "signal-decision-v1"
    assert detail["decision_card"]["evidence_strength"]["version"] == ("score-to-user-bucket-v1")

    for action in ("act", "watch", "skip"):
        action_response = client.post(
            f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/signals/{signal['id']}/actions",
            json={"action": action, "reason": f"integration_{action}"},
        )
        assert action_response.status_code == 201
        assert action_response.json()["action"] == action

    digest_response = client.get(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/digest/latest")
    assert digest_response.status_code == 200
    digest = digest_response.json()
    assert digest["content"]["version"] == "evidence-digest-v4-insight-gate"
    assert all(item["decision_card"] for item in digest["content"]["items"])
    assert all(item["decision_card"]["release_ready"] for item in digest["content"]["items"])


def test_digest_suppresses_topics_without_an_evidence_backed_insight(
    client: TestClient,
    session_factory: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(api_main.settings, "feature_decision_experience", True)
    with session_factory() as session:
        for score in session.scalars(select(WorkspaceSignalScore)):
            score.recommended_angle_json = [
                {
                    **angle,
                    "release_ready": False,
                    "insight_status": "candidate",
                    "insight_statement": (
                        "The stored evidence does not yet establish a non-obvious insight."
                    ),
                }
                for angle in score.recommended_angle_json
            ]
        session.commit()

    response = client.post(f"/api/v1/workspaces/{DEMO_WORKSPACE_ID}/digest/generate")

    assert response.status_code == 201
    assert response.json()["content"]["items"] == []


def test_private_beta_workspace_setup_and_operations_readiness(
    client: TestClient,
) -> None:
    created = client.post(
        "/api/v1/admin/workspaces",
        json={
            "workspace_name": "North Star Studio",
            "timezone": "Europe/Moscow",
            "owner_email": "founder@north-star.example",
            "owner_name": "Founder",
        },
    )
    assert created.status_code == 201
    setup = created.json()
    assert setup["onboarding_url"].endswith(f"/onboarding?workspace={setup['workspace_id']}")

    onboarding = client.get(f"/api/v1/workspaces/{setup['workspace_id']}/onboarding")
    assert onboarding.status_code == 200
    assert onboarding.json()["status"] == "in_progress"
    assert onboarding.json()["owned_channel"] is None

    operations = client.get("/api/v1/admin/operations/readiness")
    assert operations.status_code == 200
    body = operations.json()
    assert body["status"] in {"ready", "degraded", "critical"}
    assert set(body["pipeline"]) == {
        "discovery",
        "topic",
        "demand",
        "transcript",
    }
    assert "checksum_present" in body["backup"]
