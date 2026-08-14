import type { Brief, SignalListItem } from "@/lib/types";

export const OPPORTUNITY_GROUPS = [
  {
    key: "needs_decision",
    label: "Inbox",
    description: "New evidence-backed ideas waiting for your choice.",
  },
  {
    key: "watching",
    label: "Tracking",
    description:
      "Ideas saved for later. Their sources and metrics update with the normal discovery refresh.",
  },
  {
    key: "in_production",
    label: "Video plans",
    description: "Ideas you chose to develop, from draft through publication.",
  },
  {
    key: "skipped",
    label: "Dismissed",
    description: "Ideas you removed from the active workflow.",
  },
  {
    key: "expired",
    label: "Closed",
    description: "Ideas whose evidence-backed publishing window has ended.",
  },
] as const;

export type OpportunityGroupKey = (typeof OPPORTUNITY_GROUPS)[number]["key"];

export function opportunityGroupFromParam(
  value: string | null | undefined,
): OpportunityGroupKey | null {
  return OPPORTUNITY_GROUPS.find((group) => group.key === value)?.key ?? null;
}

function timestamp(value: string) {
  const hasTimezone = /(?:Z|[+-]\d{2}:\d{2})$/.test(value);
  return new Date(hasTimezone ? value : `${value}Z`).getTime();
}

export function latestBriefBySignal(briefs: Brief[]) {
  const bySignal = new Map<string, Brief>();
  for (const brief of briefs) {
    if (brief.status === "archived") continue;
    const current = bySignal.get(brief.signal_id);
    if (
      !current ||
      timestamp(brief.updated_at) > timestamp(current.updated_at)
    ) {
      bySignal.set(brief.signal_id, brief);
    }
  }
  return bySignal;
}

export function opportunityGroup(
  signal: SignalListItem,
  brief: Brief | undefined,
  now = new Date(),
): OpportunityGroupKey {
  if (brief || signal.current_action === "act") return "in_production";
  if (signal.current_action === "watch") return "watching";
  if (signal.current_action === "skip") return "skipped";
  if (signal.decision_card && !signal.decision_card.release_ready)
    return "watching";

  const expiredByWindow =
    timestamp(signal.opportunity_window.end) < now.getTime();
  const expiredByStage = ["Saturated", "Declining"].includes(
    signal.lifecycle_stage,
  );
  if (expiredByWindow || expiredByStage) return "expired";
  return "needs_decision";
}

export function opportunityStatusLabel(
  group: OpportunityGroupKey,
  brief?: Brief,
) {
  if (group === "needs_decision") return "Open";
  if (group === "watching") return "Tracking";
  if (group === "skipped") return "Dismissed";
  if (group === "expired") return "Window closed";
  if (!brief) return "Video plan created";
  if (brief.status === "draft") return "Draft plan";
  if (brief.status === "approved") return "Approved";
  if (brief.status === "in_production") return "In production";
  if (brief.status === "published") return "Published";
  return "Video plan created";
}
