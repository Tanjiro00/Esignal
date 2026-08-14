from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DECAY_VERSION = "creator-specific-opportunity-decay-v1"


@dataclass(frozen=True)
class FeasibilityAssessment:
    estimated_days_min: int
    estimated_days_max: int
    recommended_publish_by: datetime
    recommended_publish_by_label: str
    feasibility: str
    feasible_for_act: bool
    reason_codes: tuple[str, ...]
    decay_days: int
    timezone: str
    version: str = DECAY_VERSION


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _timezone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _next_available_day(
    value: datetime,
    *,
    weekday_only: bool,
    blocked_dates: set[date],
) -> datetime:
    candidate = value
    for _attempt in range(31):
        local_date = candidate.date()
        blocked_weekend = weekday_only and candidate.weekday() >= 5
        if not blocked_weekend and local_date not in blocked_dates:
            return candidate
        candidate += timedelta(days=1)
    return candidate


def assess_production_feasibility(
    *,
    observed_at: datetime,
    opportunity_end: datetime,
    workspace_timezone: str,
    lifecycle_stage: str,
    adoption_rate: float,
    large_channel_entry: bool,
    production_days_min: int,
    production_days_max: int,
    team_size: int,
    research_capacity_hours: float,
    filming_required: bool,
    external_guests_required: bool,
    editing_complexity: str,
    has_product_access: bool,
    requires_product_access: bool,
    weekday_publish_only: bool,
    content_calendar: list[dict[str, object]],
) -> FeasibilityAssessment:
    reasons: list[str] = []
    estimate_min = max(0, production_days_min)
    estimate_max = max(estimate_min, production_days_max)
    if research_capacity_hours < 4:
        estimate_min += 1
        estimate_max += 2
        reasons.append("limited_research_capacity")
    if filming_required:
        estimate_max += 1
        reasons.append("filming_required")
    if external_guests_required:
        estimate_min += 2
        estimate_max += 4
        reasons.append("external_guest_dependency")
    if editing_complexity == "high":
        estimate_min += 1
        estimate_max += 2
        reasons.append("high_editing_complexity")
    elif editing_complexity == "low":
        estimate_max = max(estimate_min, estimate_max - 1)
    if team_size >= 3:
        estimate_min = max(0, estimate_min - 1)
        estimate_max = max(estimate_min, estimate_max - 1)
        reasons.append("team_capacity_available")
    if requires_product_access and not has_product_access:
        estimate_min += 2
        estimate_max += 4
        reasons.append("missing_product_access")

    base_decay = {
        "Seed": 14,
        "Emerging": 10,
        "Breakout": 5,
        "Mass Market": 2,
        "Saturated": 0,
        "Declining": 0,
    }.get(lifecycle_stage, 7)
    velocity_penalty = 3 if adoption_rate >= 80 else 2 if adoption_rate >= 55 else 1
    decay_days = max(
        0,
        base_decay - velocity_penalty - (2 if large_channel_entry else 0),
    )
    if large_channel_entry:
        reasons.append("large_channel_entry_accelerates_decay")
    if adoption_rate >= 55:
        reasons.append("high_adoption_rate_accelerates_decay")

    tz = _timezone(workspace_timezone)
    observed_local = _aware(observed_at).astimezone(tz)
    end_local = _aware(opportunity_end).astimezone(tz)
    decay_end = observed_local + timedelta(days=decay_days)
    publish_by = min(end_local, decay_end)
    blocked_dates = {
        date.fromisoformat(str(item["date"]))
        for item in content_calendar
        if item.get("date") and str(item.get("status", "blocked")) != "available"
    }
    earliest_publish = _next_available_day(
        observed_local + timedelta(days=estimate_min),
        weekday_only=weekday_publish_only,
        blocked_dates=blocked_dates,
    )
    latest_publish = _next_available_day(
        observed_local + timedelta(days=estimate_max),
        weekday_only=weekday_publish_only,
        blocked_dates=blocked_dates,
    )
    if weekday_publish_only:
        reasons.append("weekday_publish_constraint")
    if blocked_dates:
        reasons.append("content_calendar_constraint")

    if earliest_publish > publish_by:
        feasibility = "Infeasible"
        feasible_for_act = False
        reasons.append("minimum_production_exceeds_publish_by")
    elif latest_publish > publish_by:
        feasibility = "Medium"
        feasible_for_act = True
        reasons.append("maximum_production_exceeds_publish_by")
    else:
        remaining_days = (publish_by - latest_publish).total_seconds() / 86_400
        feasibility = "High" if remaining_days >= 1 else "Medium"
        feasible_for_act = True
        reasons.append("production_fits_publish_window")
    if lifecycle_stage in {"Saturated", "Declining"}:
        feasibility = "Infeasible"
        feasible_for_act = False
        reasons.append("lifecycle_window_closed")

    return FeasibilityAssessment(
        estimated_days_min=estimate_min,
        estimated_days_max=estimate_max,
        recommended_publish_by=publish_by.astimezone(UTC),
        recommended_publish_by_label=publish_by.strftime("%B %-d"),
        feasibility=feasibility,
        feasible_for_act=feasible_for_act,
        reason_codes=tuple(dict.fromkeys(reasons)),
        decay_days=decay_days,
        timezone=getattr(tz, "key", "UTC"),
    )
