import type {
  DigestItem,
  SignalDecisionCard,
  SignalDetail,
  SignalListItem,
} from "@/lib/types";

function bucket(label: "Low" | "Moderate" | "High" | "Very high") {
  return {
    label,
    reason_codes: ["legacy_fallback"],
    version: "ux-fallback-v1",
  };
}

export function decisionCardFromDigest(item: DigestItem): SignalDecisionCard {
  if (item.decision_card) return item.decision_card;
  return {
    decision: item.suggested_decision,
    decision_label: item.suggested_decision.toUpperCase(),
    decision_reason_codes: [],
    decision_version: "ux-fallback-v1",
    topic: item.topic_label,
    thesis:
      item.why_emerging[0] ??
      "Stored evidence makes this topic worth a channel decision.",
    why_now:
      item.why_emerging[0] ??
      "Independent channels are beginning to move on the same specific topic.",
    why_this_channel:
      "The recommendation matches the saved channel profile and production limits.",
    open_angle: "No evidence-backed video angle yet.",
    recommended_video: "No evidence-backed video angle yet.",
    release_ready: false,
    insight_status: "candidate",
    insight_type: "legacy_fallback",
    insight_statement:
      "The stored evidence supports a trend, but not a non-obvious video insight yet.",
    insight_reason_codes: ["missing_insight_provenance"],
    publishing_window: item.opportunity_window,
    production_effort: item.recommended_angle.effort,
    production_days_min: item.recommended_angle.production_time_days?.min ?? 2,
    production_days_max: item.recommended_angle.production_time_days?.max ?? 5,
    signal_strength: bucket("Moderate"),
    channel_fit: bucket(item.channel_fit >= 70 ? "High" : "Moderate"),
    confidence: bucket(item.confidence === "High" ? "High" : "Moderate"),
    evidence_strength: bucket(
      item.evidence_videos.length >= 3 ? "High" : "Moderate",
    ),
    main_risk:
      item.saturation.analysis ||
      "The topic may accelerate before the recommended production window closes.",
  };
}

export function decisionCardFromSignal(
  signal: SignalListItem | SignalDetail,
): SignalDecisionCard {
  if (signal.decision_card) return signal.decision_card;
  const angle =
    "content_angles" in signal ? signal.content_angles[0] : undefined;
  const topic =
    "topic_label" in signal ? signal.topic_label : signal.topic.label;
  return {
    decision:
      signal.score >= 75 ? "Act" : signal.score >= 55 ? "Watch" : "Skip",
    decision_label:
      signal.score >= 75 ? "ACT NOW" : signal.score >= 55 ? "WATCH" : "SKIP",
    decision_reason_codes: [],
    decision_version: "ux-fallback-v1",
    topic,
    thesis: signal.thesis,
    why_now:
      "Recent independent evidence shows a meaningful change in this specific topic.",
    why_this_channel:
      "The recommendation uses the saved channel profile and production limits.",
    open_angle: "No evidence-backed video angle yet.",
    recommended_video: "No evidence-backed video angle yet.",
    release_ready: false,
    insight_status: "candidate",
    insight_type: "legacy_fallback",
    insight_statement:
      "The stored evidence supports a trend, but not a non-obvious video insight yet.",
    insight_reason_codes: ["missing_insight_provenance"],
    publishing_window: signal.opportunity_window,
    production_effort: angle?.effort ?? "Medium",
    production_days_min: angle?.production_time_days?.min ?? 2,
    production_days_max: angle?.production_time_days?.max ?? 5,
    signal_strength: bucket(signal.score >= 75 ? "High" : "Moderate"),
    channel_fit: bucket(signal.channel_fit >= 70 ? "High" : "Moderate"),
    confidence: bucket(signal.confidence === "High" ? "High" : "Moderate"),
    evidence_strength: bucket("Moderate"),
    main_risk:
      "The observed movement could slow before a differentiated video is ready.",
  };
}
