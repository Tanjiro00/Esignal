import { describe, expect, it } from "vitest";

import {
  BRIEF_DOCUMENT_VERSION,
  DEFAULT_FULL_OUTLINE,
  DEFAULT_SUGGESTED_OPENING,
  briefDocumentFromEditor,
  briefEditorState,
  outlineDurationMinutes,
  timelineIsContinuous,
  validateBriefEditor,
} from "@/lib/brief-document";
import type { Brief, SignalPackaging } from "@/lib/types";

function brief(): Brief {
  return {
    id: "brief-1",
    workspace_id: "workspace-1",
    signal_id: "signal-1",
    channel_id: "channel-1",
    opportunity_id: "opportunity-1",
    evidence_version: "evidence-v1",
    status: "draft",
    title: "Working title",
    brief_json: {
      title: "Stored angle",
      audience_promise: "Stored audience promise",
      why_now: "Stored why now",
      evidence: ["video:1"],
      unanswered_question: "Stored question?",
      format: "Creator choice",
      effort: "Medium",
      timing_risk: "Ship inside the window.",
      title_directions: [],
      avoid: "Avoid unsupported claims.",
      recommended_publish_by: "2026-08-03T10:00:00Z",
    },
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
  };
}

function packaging(): SignalPackaging {
  return {
    id: "packaging-1",
    workspace_id: "workspace-1",
    signal_id: "signal-1",
    opportunity_id: "opportunity-1",
    content_brief_id: "brief-1",
    packaging: {
      audience_promise: "Packaging audience promise",
      core_tension: "Stored tension",
      hook_directions: [],
      title_directions: [],
      thumbnail_directions: [],
      proof_requirements: ["Real artifact", "Measured result"],
      clickbait_mismatch_risks: [],
      opening_structure: [
        "0:00–0:20 — unresolved tension",
        "0:20–0:45 — test definition",
        "0:45–1:20 — stakes and evidence",
        "1:20 onward — full proof",
      ],
      claims_policy: { allowed: [], requires_new_proof: [] },
      full_script_generated: false,
      revision: 0,
      version: "signal-packaging-v1",
    },
    evidence_ids: ["video:1"],
    regeneration_counts: {},
    packaging_version: "signal-packaging-v1",
    created_at: "2026-07-29T00:00:00Z",
    updated_at: "2026-07-29T00:00:00Z",
  };
}

describe("producer brief document", () => {
  it("creates a three-step opening and a continuous 23-minute outline", () => {
    const editor = briefEditorState(brief(), packaging(), "Avery Chen");

    expect(editor.suggestedOpening).toHaveLength(3);
    expect(editor.suggestedOpening.at(-1)?.end).toBe("1:20");
    expect(editor.fullOutline).toHaveLength(7);
    expect(outlineDurationMinutes(editor.fullOutline)).toBe(23);
    expect(timelineIsContinuous(editor.fullOutline)).toBe(true);
  });

  it("defaults the editable producer fields from stored data", () => {
    const editor = briefEditorState(brief(), packaging(), "Avery Chen");

    expect(editor.owner).toBe("Avery Chen");
    expect(editor.targetPublishDate).toBe("2026-08-03");
    expect(editor.audienceTakeaway).toBe("Packaging audience promise");
    expect(editor.proofChecklist.map((item) => item.text)).toEqual([
      "Real artifact",
      "Measured result",
    ]);
    expect(validateBriefEditor(editor)).toEqual([]);
  });

  it("merges edits without dropping the evidence-grounded angle", () => {
    const source = brief();
    const editor = briefEditorState(source, packaging(), "Avery Chen");
    editor.owner = "Producer";
    editor.proofChecklist[0].completed = true;

    const document = briefDocumentFromEditor(source.brief_json, editor);

    expect(document.evidence).toEqual(["video:1"]);
    expect(document.owner).toBe("Producer");
    expect(document.required_proof_checklist?.[0].completed).toBe(true);
    expect(document.brief_document_version).toBe(BRIEF_DOCUMENT_VERSION);
  });

  it("keeps exported defaults immutable across editors", () => {
    const first = briefEditorState(brief(), undefined, "Avery Chen");
    first.fullOutline[0].label = "Changed";
    first.suggestedOpening[0].label = "Changed";

    expect(DEFAULT_FULL_OUTLINE[0].label).toBe("Hook and setup");
    expect(DEFAULT_SUGGESTED_OPENING[0].label).toBe(
      "Unresolved tension and the audience decision",
    );
  });
});
