"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckSquare,
  Clipboard,
  Download,
  ExternalLink,
  Pencil,
  Play,
  Save,
  Share2,
  Square,
  X,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui";
import { trackProductEvent, updateBrief } from "@/lib/api";
import {
  briefDocumentFromEditor,
  briefEditorState,
  outlineDurationMinutes,
  validateBriefEditor,
  type BriefEditorState,
  type BriefStatus,
} from "@/lib/brief-document";
import { createClientEventId } from "@/lib/client-id";
import { relativeTime } from "@/lib/format";
import type {
  Brief,
  BriefOutlineStep,
  DemoContext,
  SignalPackaging,
} from "@/lib/types";

const STATUS_OPTIONS: Array<{ value: BriefStatus; label: string }> = [
  { value: "draft", label: "Draft" },
  { value: "approved", label: "Approved" },
  { value: "in_production", label: "In production" },
  { value: "published", label: "Published" },
  { value: "archived", label: "Archived" },
];

const FIELD_CLASS =
  "min-h-11 w-full border border-[var(--line-strong)] bg-white px-3 text-[12px] outline-none focus:border-[var(--ink)]";
const TEXTAREA_CLASS = `${FIELD_CLASS} resize-y py-3 leading-6`;

function formatDate(value: string) {
  if (!value) return "Not scheduled";
  const date = new Date(`${value}T12:00:00`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(date);
}

function statusLabel(status: string) {
  return status.replaceAll("_", " ");
}

function filename(title: string) {
  return `${title
    .toLowerCase()
    .replaceAll(/[^a-z0-9]+/g, "-")
    .replaceAll(/(^-|-$)/g, "")}.md`;
}

function downloadMarkdown(name: string, markdown: string) {
  const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = name;
  anchor.click();
  URL.revokeObjectURL(url);
}

async function copyText(value: string) {
  try {
    await navigator.clipboard.writeText(value);
  } catch {
    const textarea = document.createElement("textarea");
    textarea.value = value;
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    document.body.appendChild(textarea);
    textarea.select();
    document.execCommand("copy");
    textarea.remove();
  }
}

function outlineMarkdown(steps: BriefOutlineStep[]) {
  return steps.map((step) => `- ${step.start}–${step.end} — ${step.label}`);
}

function briefAsMarkdown(
  brief: Brief,
  packaging: SignalPackaging | undefined,
  editor: BriefEditorState,
) {
  const angle = brief.brief_json;
  const kit = packaging?.packaging;
  return [
    `# ${editor.workingTitle}`,
    "",
    `Owner: ${editor.owner}`,
    `Status: ${statusLabel(editor.status)}`,
    `Target publish date: ${editor.targetPublishDate || "Not scheduled"}`,
    "",
    "## Core idea",
    angle.title,
    "",
    "## Audience takeaway",
    editor.audienceTakeaway,
    "",
    "## Why now",
    angle.why_now,
    "",
    "## What existing coverage misses",
    angle.unanswered_question,
    "",
    "## Suggested opening",
    ...outlineMarkdown(editor.suggestedOpening),
    "",
    "## Full video outline",
    ...outlineMarkdown(editor.fullOutline),
    "",
    "## Required proof checklist",
    ...editor.proofChecklist.map(
      (item) => `- [${item.completed ? "x" : " "}] ${item.text}`,
    ),
    "",
    "## Claims allowed",
    ...(kit?.claims_policy.allowed ?? angle.evidence).map(
      (item) => `- ${item}`,
    ),
    "",
    "## Claims requiring proof",
    ...(
      kit?.claims_policy.requires_new_proof ?? [
        "Any guaranteed performance claim.",
      ]
    ).map((item) => `- ${item}`),
    "",
    "## Production notes",
    editor.productionNotes,
    "",
    "_Generated from stored EarlySignal evidence. No full script included._",
  ].join("\n");
}

function Timeline({
  label,
  steps,
  testId,
}: {
  label: string;
  steps: BriefOutlineStep[];
  testId: string;
}) {
  return (
    <section>
      <div className="flex items-baseline justify-between gap-4">
        <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
          {label}
        </p>
        <p className="text-[10px] text-[var(--muted)]">
          {steps[0]?.start}–{steps.at(-1)?.end}
        </p>
      </div>
      <ol
        className="mt-4 border-t border-[var(--line-strong)]"
        data-testid={testId}
      >
        {steps.map((step, index) => (
          <li
            className="grid grid-cols-[84px_minmax(0,1fr)] gap-4 border-b border-[var(--line)] py-3 text-[12px] leading-6 sm:grid-cols-[110px_minmax(0,1fr)]"
            key={`${step.start}-${step.end}`}
          >
            <span className="mono text-[10px] text-[var(--lime-ink)]">
              {step.start}–{step.end}
            </span>
            <span>
              <span className="mr-2 text-[10px] text-[var(--muted)]">
                {String(index + 1).padStart(2, "0")}
              </span>
              {step.label}
            </span>
          </li>
        ))}
      </ol>
    </section>
  );
}

function BriefEditor({
  editor,
  onCancel,
  onChange,
  onSave,
  saving,
  validationError,
}: {
  editor: BriefEditorState;
  onCancel: () => void;
  onChange: (editor: BriefEditorState) => void;
  onSave: () => void;
  saving: boolean;
  validationError: string | null;
}) {
  const updateOutline = (
    key: "suggestedOpening" | "fullOutline",
    index: number,
    label: string,
  ) => {
    onChange({
      ...editor,
      [key]: editor[key].map((step, stepIndex) =>
        stepIndex === index ? { ...step, label } : step,
      ),
    });
  };

  return (
    <form
      className="mt-7 border-t border-[var(--line-strong)] pt-7"
      data-testid="brief-editor"
      onSubmit={(event) => {
        event.preventDefault();
        onSave();
      }}
    >
      <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <label className="sm:col-span-2 lg:col-span-4">
          <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
            Working title
          </span>
          <input
            className={`${FIELD_CLASS} mt-2`}
            onChange={(event) =>
              onChange({ ...editor, workingTitle: event.target.value })
            }
            value={editor.workingTitle}
          />
        </label>
        <label className="lg:col-span-2">
          <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
            Owner
          </span>
          <input
            className={`${FIELD_CLASS} mt-2`}
            onChange={(event) =>
              onChange({ ...editor, owner: event.target.value })
            }
            value={editor.owner}
          />
        </label>
        <label>
          <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
            Target publish date
          </span>
          <input
            className={`${FIELD_CLASS} mt-2`}
            onChange={(event) =>
              onChange({ ...editor, targetPublishDate: event.target.value })
            }
            type="date"
            value={editor.targetPublishDate}
          />
        </label>
        <label>
          <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
            Status
          </span>
          <select
            className={`${FIELD_CLASS} mt-2`}
            onChange={(event) =>
              onChange({
                ...editor,
                status: event.target.value as BriefStatus,
              })
            }
            value={editor.status}
          >
            {STATUS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="sm:col-span-2 lg:col-span-4">
          <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
            Audience takeaway
          </span>
          <textarea
            className={`${TEXTAREA_CLASS} mt-2 min-h-24`}
            onChange={(event) =>
              onChange({ ...editor, audienceTakeaway: event.target.value })
            }
            value={editor.audienceTakeaway}
          />
        </label>
      </div>

      <div className="mt-8 grid gap-8 lg:grid-cols-2">
        {(
          [
            ["Suggested opening", "suggestedOpening"],
            ["Full video outline", "fullOutline"],
          ] as const
        ).map(([label, key]) => (
          <fieldset key={key}>
            <legend className="text-[10px] font-semibold tracking-[0.1em] uppercase">
              {label}
            </legend>
            <div className="mt-3 space-y-3">
              {editor[key].map((step, index) => (
                <label
                  className="grid grid-cols-[82px_minmax(0,1fr)] items-center gap-3"
                  key={`${step.start}-${step.end}`}
                >
                  <span className="mono text-[11px] text-[var(--lime-ink)]">
                    {step.start}–{step.end}
                  </span>
                  <input
                    className={FIELD_CLASS}
                    onChange={(event) =>
                      updateOutline(key, index, event.target.value)
                    }
                    value={step.label}
                  />
                </label>
              ))}
            </div>
          </fieldset>
        ))}
      </div>

      <fieldset className="mt-8">
        <legend className="text-[10px] font-semibold tracking-[0.1em] uppercase">
          Required proof checklist
        </legend>
        <div className="mt-3 space-y-3">
          {editor.proofChecklist.map((item, index) => (
            <div
              className="grid grid-cols-[36px_minmax(0,1fr)] gap-2"
              key={item.id}
            >
              <label className="grid min-h-11 place-items-center border border-[var(--line-strong)]">
                <input
                  aria-label={`Proof ${index + 1} completed`}
                  checked={item.completed}
                  className="h-4 w-4"
                  onChange={(event) =>
                    onChange({
                      ...editor,
                      proofChecklist: editor.proofChecklist.map(
                        (proof, proofIndex) =>
                          proofIndex === index
                            ? { ...proof, completed: event.target.checked }
                            : proof,
                      ),
                    })
                  }
                  type="checkbox"
                />
              </label>
              <input
                aria-label={`Proof ${index + 1}`}
                className={FIELD_CLASS}
                onChange={(event) =>
                  onChange({
                    ...editor,
                    proofChecklist: editor.proofChecklist.map(
                      (proof, proofIndex) =>
                        proofIndex === index
                          ? { ...proof, text: event.target.value }
                          : proof,
                    ),
                  })
                }
                value={item.text}
              />
            </div>
          ))}
        </div>
      </fieldset>

      <label className="mt-8 block">
        <span className="text-[10px] font-semibold tracking-[0.1em] uppercase">
          Production notes
        </span>
        <textarea
          className={`${TEXTAREA_CLASS} mt-2 min-h-32`}
          onChange={(event) =>
            onChange({ ...editor, productionNotes: event.target.value })
          }
          value={editor.productionNotes}
        />
      </label>

      {validationError ? (
        <p className="mt-4 text-[11px] text-[var(--coral)]" role="alert">
          {validationError}
        </p>
      ) : null}
      <div className="mt-6 flex flex-wrap gap-2">
        <Button disabled={saving} type="submit" variant="primary">
          <Save size={14} /> {saving ? "Saving…" : "Save plan"}
        </Button>
        <Button disabled={saving} onClick={onCancel} type="button">
          <X size={14} /> Cancel
        </Button>
      </div>
    </form>
  );
}

export function ProducerBrief({
  brief,
  context,
  index,
  packaging,
}: {
  brief: Brief;
  context: DemoContext;
  index: number;
  packaging?: SignalPackaging;
}) {
  const client = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [editor, setEditor] = useState(() =>
    briefEditorState(brief, packaging, context.user_name),
  );
  const [feedback, setFeedback] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [shared, setShared] = useState(false);
  const document = briefEditorState(brief, packaging, context.user_name);
  const runtime = outlineDurationMinutes(document.fullOutline);
  const markdown = briefAsMarkdown(brief, packaging, document);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateBrief(context.workspace_id, brief.id, {
        title: editor.workingTitle.trim(),
        status: editor.status,
        brief_json: briefDocumentFromEditor(brief.brief_json, editor),
      }),
    onSuccess: async () => {
      setEditing(false);
      setFeedback("Video plan saved.");
      await client.invalidateQueries({ queryKey: ["briefs-v2"] });
    },
  });
  const productionMutation = useMutation({
    mutationFn: () =>
      updateBrief(context.workspace_id, brief.id, {
        status: "in_production",
      }),
    onSuccess: async () => {
      setFeedback("Production started.");
      await client.invalidateQueries({ queryKey: ["briefs-v2"] });
    },
  });

  const startEditing = () => {
    setEditor(briefEditorState(brief, packaging, context.user_name));
    setValidationError(null);
    setFeedback(null);
    setEditing(true);
  };

  const save = () => {
    const errors = validateBriefEditor(editor);
    if (errors.length) {
      setValidationError(
        "Complete the working title, owner, audience takeaway, proof checklist and continuous outline before saving.",
      );
      return;
    }
    setValidationError(null);
    saveMutation.mutate();
  };

  return (
    <article
      className="scroll-mt-8 py-9 sm:py-12"
      data-testid="producer-brief"
      id={`brief-${brief.id}`}
    >
      <div className="flex flex-wrap items-start justify-between gap-5">
        <div>
          <p className="text-[10px] font-semibold tracking-[0.12em] text-[var(--muted)] uppercase">
            Video plan {index + 1} · {statusLabel(brief.status)} · updated{" "}
            {relativeTime(brief.updated_at)}
          </p>
          <h2 className="editorial mt-3 max-w-[760px] text-[34px] leading-tight sm:text-[42px]">
            {brief.title}
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {brief.status === "in_production" ? (
            <span className="inline-flex min-h-9 items-center gap-2 bg-[var(--lime-soft)] px-3 text-[11px] font-semibold text-[var(--lime-ink)]">
              <Check size={14} /> Production started
            </span>
          ) : null}
          {!editing ? (
            <Button onClick={startEditing}>
              <Pencil size={14} /> Edit plan
            </Button>
          ) : null}
        </div>
      </div>

      {editing ? (
        <BriefEditor
          editor={editor}
          onCancel={() => {
            setEditing(false);
            setValidationError(null);
          }}
          onChange={setEditor}
          onSave={save}
          saving={saveMutation.isPending}
          validationError={
            validationError ||
            (saveMutation.isError ? saveMutation.error.message : null)
          }
        />
      ) : (
        <>
          <dl className="mt-7 grid grid-cols-2 border-y border-[var(--line-strong)] lg:grid-cols-4">
            {[
              ["Owner", document.owner],
              ["Target publish date", formatDate(document.targetPublishDate)],
              ["Status", statusLabel(document.status)],
              ["Runtime", runtime ? `${runtime} minutes` : "Check outline"],
            ].map(([label, value]) => (
              <div
                className="border-b border-[var(--line)] py-4 nth-[2n]:pl-4 nth-[2n+1]:pr-4 lg:border-r lg:border-b-0 lg:px-5 lg:first:pl-0 lg:last:border-r-0 lg:last:pr-0"
                key={label}
              >
                <dt className="text-[11px] font-semibold tracking-[0.1em] text-[var(--muted)] uppercase">
                  {label}
                </dt>
                <dd className="mt-2 text-[12px] font-semibold capitalize">
                  {value}
                </dd>
              </div>
            ))}
          </dl>

          <div className="mt-8 grid gap-8 lg:grid-cols-[1fr_260px]">
            <div className="space-y-8">
              <section className="grid gap-6 sm:grid-cols-2">
                <div>
                  <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                    Core idea
                  </p>
                  <p className="mt-3 text-[14px] leading-7">
                    {brief.brief_json.title}
                  </p>
                </div>
                <div>
                  <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                    What existing coverage misses
                  </p>
                  <p className="mt-3 text-[12px] leading-6 text-[var(--muted)]">
                    {brief.brief_json.unanswered_question}
                  </p>
                </div>
                <div className="border-t border-[var(--line)] pt-5 sm:col-span-2">
                  <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                    Audience takeaway
                  </p>
                  <p className="mt-3 text-[15px] leading-7">
                    {document.audienceTakeaway}
                  </p>
                </div>
              </section>

              <Timeline
                label="Suggested opening"
                steps={document.suggestedOpening}
                testId="suggested-opening"
              />
              <Timeline
                label="Full video outline"
                steps={document.fullOutline}
                testId="full-video-outline"
              />

              <section>
                <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                  Required proof checklist
                </p>
                <ul className="mt-4 border-t border-[var(--line-strong)]">
                  {document.proofChecklist.map((item) => (
                    <li
                      className="flex gap-3 border-b border-[var(--line)] py-3 text-[11px] leading-6"
                      key={item.id}
                    >
                      {item.completed ? (
                        <CheckSquare
                          className="mt-1 shrink-0 text-[var(--lime-ink)]"
                          size={15}
                        />
                      ) : (
                        <Square
                          className="mt-1 shrink-0 text-[var(--muted)]"
                          size={15}
                        />
                      )}
                      {item.text}
                    </li>
                  ))}
                </ul>
              </section>

              <section className="border-t border-[var(--line)] pt-7">
                <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                  Production notes
                </p>
                <p className="mt-3 text-[11px] leading-6 whitespace-pre-line text-[var(--muted)]">
                  {document.productionNotes || "No production notes saved."}
                </p>
              </section>

              <section className="grid gap-7 border-t border-[var(--line)] pt-7 sm:grid-cols-2">
                <div>
                  <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                    Claims allowed
                  </p>
                  <ul className="mt-3 space-y-2 text-[11px] leading-6">
                    {(
                      packaging?.packaging.claims_policy.allowed ??
                      brief.brief_json.evidence
                    ).map((claim) => (
                      <li key={claim}>✓ {claim}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
                    Claims requiring new proof
                  </p>
                  <ul className="mt-3 space-y-2 text-[11px] leading-6 text-[var(--muted)]">
                    {(
                      packaging?.packaging.claims_policy.requires_new_proof ?? [
                        "Any guaranteed performance claim.",
                      ]
                    ).map((claim) => (
                      <li key={claim}>! {claim}</li>
                    ))}
                  </ul>
                </div>
              </section>

              {packaging ? (
                <details className="group border-t border-[var(--line-strong)]">
                  <summary className="flex min-h-14 cursor-pointer list-none items-center justify-between text-[11px] font-semibold">
                    Packaging directions
                    <span className="text-[10px] font-normal text-[var(--muted)]">
                      Hooks, titles and thumbnails
                    </span>
                  </summary>
                  <div className="space-y-7 pb-6">
                    <div>
                      <p className="text-[10px] font-semibold uppercase">
                        Hook directions
                      </p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        {packaging.packaging.hook_directions
                          .slice(0, 3)
                          .map((hook) => (
                            <p
                              className="border-l-2 border-[var(--lime-strong)] pl-3 text-[11px] leading-6"
                              key={hook.strategy}
                            >
                              {hook.direction}
                            </p>
                          ))}
                      </div>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase">
                        Title directions
                      </p>
                      <ol className="mt-3 grid gap-x-7 gap-y-2 text-[11px] leading-6 sm:grid-cols-2">
                        {packaging.packaging.title_directions
                          .slice(0, 6)
                          .map((title) => (
                            <li key={title.strategy}>— {title.text}</li>
                          ))}
                      </ol>
                    </div>
                    <div>
                      <p className="text-[10px] font-semibold uppercase">
                        Thumbnail directions
                      </p>
                      <div className="mt-3 grid gap-3 sm:grid-cols-3">
                        {packaging.packaging.thumbnail_directions
                          .slice(0, 3)
                          .map((item) => (
                            <div
                              className="border border-[var(--line)] p-4 text-[11px] leading-5"
                              key={item.strategy}
                            >
                              <strong>{item.text}</strong>
                              <p className="mt-2 text-[var(--muted)]">
                                {item.main_visual}
                              </p>
                            </div>
                          ))}
                      </div>
                    </div>
                  </div>
                </details>
              ) : null}
            </div>

            <aside className="h-fit border-l border-[var(--line)] pl-6 max-lg:border-t max-lg:border-l-0 max-lg:pt-6 max-lg:pl-0">
              <dl className="space-y-5 text-[12px]">
                <div>
                  <dt className="text-[var(--muted)]">Format</dt>
                  <dd className="mt-1 font-semibold">
                    {brief.brief_json.format}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Production</dt>
                  <dd className="mt-1 font-semibold">
                    {brief.brief_json.production_time_days
                      ? `${brief.brief_json.production_time_days.min}–${brief.brief_json.production_time_days.max} days`
                      : brief.brief_json.effort}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Publish by</dt>
                  <dd className="mt-1 font-semibold">
                    {formatDate(document.targetPublishDate)}
                  </dd>
                </div>
                <div>
                  <dt className="text-[var(--muted)]">Main mismatch risk</dt>
                  <dd className="mt-1 leading-6">
                    {packaging?.packaging.clickbait_mismatch_risks[0] ??
                      brief.brief_json.avoid}
                  </dd>
                </div>
              </dl>

              <div className="mt-7 grid gap-2">
                <Button
                  className="min-h-11 justify-start"
                  onClick={async () => {
                    await copyText(markdown);
                    setCopied(true);
                  }}
                >
                  {copied ? <Check size={14} /> : <Clipboard size={14} />}
                  {copied ? "Copied" : "Copy plan"}
                </Button>
                <Button
                  className="min-h-11 justify-start"
                  onClick={async () => {
                    const url = `${window.location.origin}/briefs#brief-${brief.id}`;
                    await copyText(url);
                    setShared(true);
                    void trackProductEvent(context.workspace_id, {
                      event_type: "brief_shared",
                      event_key: `brief-shared:${createClientEventId()}:${brief.id}`,
                      signal_id: brief.signal_id,
                      metadata: { brief_id: brief.id },
                    }).catch(() => undefined);
                  }}
                >
                  {shared ? <Check size={14} /> : <Share2 size={14} />}
                  {shared ? "Link copied" : "Share link"}
                </Button>
                <Button
                  className="min-h-11 justify-start"
                  onClick={() =>
                    downloadMarkdown(filename(brief.title), markdown)
                  }
                >
                  <Download size={14} /> Export Markdown
                </Button>
                {brief.status !== "in_production" ? (
                  <Button
                    className="min-h-11 justify-start"
                    disabled={productionMutation.isPending}
                    onClick={() => productionMutation.mutate()}
                    variant="primary"
                  >
                    <Play size={14} /> Start production
                  </Button>
                ) : null}
                <p className="text-[10px] leading-5 text-[var(--muted)]">
                  After publishing, EarlySignal will look for the matching video
                  and measure it in Performance.
                </p>
                <Link
                  className="mt-2 inline-flex min-h-11 items-center justify-between border-t border-[var(--line)] pt-3 text-[12px] font-medium hover:underline"
                  href={`/opportunities/${brief.signal_id}`}
                >
                  Back to source idea <ExternalLink size={13} />
                </Link>
              </div>

              <details className="group mt-5 border-t border-[var(--line)]">
                <summary className="min-h-11 cursor-pointer py-3 text-[10px] text-[var(--muted)]">
                  Technical evidence reference
                </summary>
                <p className="mono text-[11px] leading-5 text-[var(--muted)]">
                  {brief.evidence_version}
                </p>
              </details>
            </aside>
          </div>
        </>
      )}

      {feedback ? (
        <p className="mt-5 text-[11px] text-[var(--lime-ink)]" role="status">
          {feedback}
        </p>
      ) : null}
      {productionMutation.isError ? (
        <p className="mt-5 text-[11px] text-[var(--coral)]" role="alert">
          {productionMutation.error.message}
        </p>
      ) : null}
    </article>
  );
}
