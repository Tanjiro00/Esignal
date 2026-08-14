import type {
  Brief,
  BriefDocument,
  BriefOutlineStep,
  BriefProofItem,
  SignalPackaging,
} from "@/lib/types";

export const BRIEF_DOCUMENT_VERSION = "producer-brief-v2";

export const DEFAULT_SUGGESTED_OPENING: BriefOutlineStep[] = [
  {
    start: "0:00",
    end: "0:20",
    label: "Unresolved tension and the audience decision",
  },
  {
    start: "0:20",
    end: "0:45",
    label: "Test definition and failure condition",
  },
  {
    start: "0:45",
    end: "1:20",
    label: "Stakes, evidence context, and why now",
  },
];

export const DEFAULT_FULL_OUTLINE: BriefOutlineStep[] = [
  { start: "0:00", end: "1:20", label: "Hook and setup" },
  {
    start: "1:20",
    end: "3:00",
    label: "Evaluation criteria and constraints",
  },
  { start: "3:00", end: "10:00", label: "Real workflow test" },
  { start: "10:00", end: "14:00", label: "Failures and recovery" },
  {
    start: "14:00",
    end: "18:00",
    label: "Guardrails and trade-offs",
  },
  { start: "18:00", end: "21:00", label: "Results" },
  { start: "21:00", end: "23:00", label: "Recommendation" },
];

export type BriefStatus =
  "draft" | "approved" | "in_production" | "published" | "archived";

export type BriefEditorState = {
  workingTitle: string;
  owner: string;
  targetPublishDate: string;
  status: BriefStatus;
  audienceTakeaway: string;
  proofChecklist: BriefProofItem[];
  productionNotes: string;
  suggestedOpening: BriefOutlineStep[];
  fullOutline: BriefOutlineStep[];
};

function cloneSteps(steps: BriefOutlineStep[]) {
  return steps.map((step) => ({ ...step }));
}

function isOutline(value: unknown): value is BriefOutlineStep[] {
  return (
    Array.isArray(value) &&
    value.length > 0 &&
    value.every(
      (step) =>
        typeof step === "object" &&
        step !== null &&
        typeof (step as BriefOutlineStep).start === "string" &&
        typeof (step as BriefOutlineStep).end === "string" &&
        typeof (step as BriefOutlineStep).label === "string",
    )
  );
}

function parseOpeningStep(value: string): BriefOutlineStep | null {
  const match = value.match(
    /^(\d+:\d{2})[–-](\d+:\d{2})\s+[—-]\s+(.+?)(?:\.)?$/,
  );
  if (!match) return null;
  return { start: match[1], end: match[2], label: match[3] };
}

function suggestedOpening(packaging?: SignalPackaging) {
  const parsed = (packaging?.packaging.opening_structure ?? [])
    .slice(0, 3)
    .map(parseOpeningStep)
    .filter((step): step is BriefOutlineStep => step !== null);
  return parsed.length === 3 ? parsed : cloneSteps(DEFAULT_SUGGESTED_OPENING);
}

function dateOnly(value?: string) {
  if (!value) return "";
  const match = value.match(/^\d{4}-\d{2}-\d{2}/);
  return match?.[0] ?? "";
}

function status(value: string): BriefStatus {
  if (
    value === "approved" ||
    value === "in_production" ||
    value === "published" ||
    value === "archived"
  ) {
    return value;
  }
  return "draft";
}

function proofChecklist(document: BriefDocument, packaging?: SignalPackaging) {
  if (
    Array.isArray(document.required_proof_checklist) &&
    document.required_proof_checklist.length
  ) {
    return document.required_proof_checklist.map((item) => ({ ...item }));
  }
  return (
    packaging?.packaging.proof_requirements ?? [
      "Show the real workflow or artifact used for the recommendation.",
      "Define the evaluation criteria before making a result claim.",
      "Replace numeric claims with measured evidence from this production.",
    ]
  ).map((text, index) => ({
    id: `proof-${index + 1}`,
    text,
    completed: false,
  }));
}

export function briefEditorState(
  brief: Brief,
  packaging: SignalPackaging | undefined,
  defaultOwner: string,
): BriefEditorState {
  const document = brief.brief_json;
  return {
    workingTitle: brief.title,
    owner: document.owner?.trim() || defaultOwner,
    targetPublishDate:
      dateOnly(document.target_publish_date) ||
      dateOnly(document.recommended_publish_by) ||
      dateOnly(document.best_publish_window?.end),
    status: status(brief.status),
    audienceTakeaway:
      document.audience_takeaway?.trim() ||
      packaging?.packaging.audience_promise ||
      document.audience_promise,
    proofChecklist: proofChecklist(document, packaging),
    productionNotes:
      document.production_notes?.trim() ||
      [document.avoid, document.timing_risk].filter(Boolean).join("\n\n"),
    suggestedOpening: isOutline(document.suggested_opening)
      ? cloneSteps(document.suggested_opening)
      : suggestedOpening(packaging),
    fullOutline: isOutline(document.full_outline)
      ? cloneSteps(document.full_outline)
      : cloneSteps(DEFAULT_FULL_OUTLINE),
  };
}

export function briefDocumentFromEditor(
  current: BriefDocument,
  editor: BriefEditorState,
): BriefDocument {
  return {
    ...current,
    owner: editor.owner.trim(),
    target_publish_date: editor.targetPublishDate,
    audience_takeaway: editor.audienceTakeaway.trim(),
    required_proof_checklist: editor.proofChecklist.map((item) => ({
      ...item,
      text: item.text.trim(),
    })),
    production_notes: editor.productionNotes.trim(),
    suggested_opening: cloneSteps(editor.suggestedOpening),
    full_outline: cloneSteps(editor.fullOutline),
    brief_document_version: BRIEF_DOCUMENT_VERSION,
  };
}

export function timestampSeconds(value: string) {
  const match = value.match(/^(\d+):(\d{2})$/);
  if (!match) return Number.NaN;
  return Number(match[1]) * 60 + Number(match[2]);
}

export function timelineIsContinuous(steps: BriefOutlineStep[]) {
  if (!steps.length) return false;
  return steps.every((step, index) => {
    const start = timestampSeconds(step.start);
    const end = timestampSeconds(step.end);
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) {
      return false;
    }
    if (index === 0) return start === 0;
    return start === timestampSeconds(steps[index - 1].end);
  });
}

export function outlineDurationMinutes(steps: BriefOutlineStep[]) {
  if (!timelineIsContinuous(steps)) return null;
  return timestampSeconds(steps[steps.length - 1].end) / 60;
}

export function validateBriefEditor(editor: BriefEditorState) {
  const errors: string[] = [];
  if (editor.workingTitle.trim().length < 3) errors.push("working_title");
  if (!editor.owner.trim()) errors.push("owner");
  if (!editor.audienceTakeaway.trim()) errors.push("audience_takeaway");
  if (editor.proofChecklist.some((item) => !item.text.trim())) {
    errors.push("proof_checklist");
  }
  if (!timelineIsContinuous(editor.suggestedOpening)) {
    errors.push("suggested_opening");
  }
  if (!timelineIsContinuous(editor.fullOutline)) {
    errors.push("full_outline");
  }
  return errors;
}
