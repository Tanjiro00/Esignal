from datetime import UTC, datetime, timedelta

from packages.production_feasibility import assess_production_feasibility


def test_feasibility_uses_absolute_timezone_publish_by_and_constraints() -> None:
    observed = datetime(2026, 8, 1, 12, tzinfo=UTC)
    result = assess_production_feasibility(
        observed_at=observed,
        opportunity_end=observed + timedelta(days=12),
        workspace_timezone="America/Los_Angeles",
        lifecycle_stage="Emerging",
        adoption_rate=65,
        large_channel_entry=False,
        production_days_min=2,
        production_days_max=4,
        team_size=3,
        research_capacity_hours=12,
        filming_required=False,
        external_guests_required=False,
        editing_complexity="medium",
        has_product_access=True,
        requires_product_access=True,
        weekday_publish_only=True,
        content_calendar=[{"date": "2026-08-04", "status": "blocked"}],
    )

    assert result.recommended_publish_by.tzinfo is not None
    assert result.recommended_publish_by_label == "August 9"
    assert result.timezone == "America/Los_Angeles"
    assert result.feasible_for_act is True
    assert "weekday_publish_constraint" in result.reason_codes
    assert "content_calendar_constraint" in result.reason_codes


def test_production_longer_than_window_is_never_feasible_for_act() -> None:
    observed = datetime(2026, 8, 1, 12, tzinfo=UTC)
    result = assess_production_feasibility(
        observed_at=observed,
        opportunity_end=observed + timedelta(days=4),
        workspace_timezone="Europe/Moscow",
        lifecycle_stage="Breakout",
        adoption_rate=90,
        large_channel_entry=True,
        production_days_min=7,
        production_days_max=12,
        team_size=1,
        research_capacity_hours=2,
        filming_required=True,
        external_guests_required=True,
        editing_complexity="high",
        has_product_access=False,
        requires_product_access=True,
        weekday_publish_only=False,
        content_calendar=[],
    )

    assert result.feasibility == "Infeasible"
    assert result.feasible_for_act is False
    assert "minimum_production_exceeds_publish_by" in result.reason_codes
    assert "missing_product_access" in result.reason_codes
