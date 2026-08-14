from apps.api.services import _insight_release_ready


def test_unproven_release_flag_does_not_cross_the_product_gate() -> None:
    assert not _insight_release_ready(
        {
            "release_ready": True,
            "insight_status": "evidence_backed",
            "insight_type": "coverage_gap_candidate",
            "insight_reason_codes": ["coverage_gap_only"],
            "insight_evidence": ["video:1", "video:2"],
        }
    )


def test_audited_non_obvious_insight_crosses_the_product_gate() -> None:
    assert _insight_release_ready(
        {
            "release_ready": True,
            "insight_status": "evidence_backed",
            "insight_type": "audited_contradiction",
            "insight_reason_codes": [
                "llm_grounding_audit_passed",
                "llm_non_obviousness_audit_passed",
            ],
            "insight_evidence": ["video:1", "video:2"],
        }
    )


def test_confirmed_cross_video_demand_crosses_the_product_gate() -> None:
    assert _insight_release_ready(
        {
            "release_ready": True,
            "insight_status": "evidence_backed",
            "insight_type": "audience_demand",
            "insight_reason_codes": ["confirmed_cross_video_audience_demand"],
            "insight_evidence": ["comment:1", "comment:2"],
        }
    )
