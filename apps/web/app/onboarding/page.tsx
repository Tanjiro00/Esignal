"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowRight,
  Check,
  LoaderCircle,
  Search,
  Sparkles,
  Youtube,
} from "lucide-react";
import { FormEvent, useEffect, useRef, useState } from "react";

import { ErrorState, PageLoading } from "@/components/ui";
import {
  autoSetupOnboarding,
  getDemoContext,
  getOnboardingStatus,
  trackProductEvent,
} from "@/lib/api";
import { createClientEventId } from "@/lib/client-id";
import type { DemoContext, OnboardingStatus } from "@/lib/types";

type OnboardingData = {
  context: DemoContext;
  onboarding: OnboardingStatus;
};

const analysisStages = [
  {
    title: "Reading your channel",
    detail: "Public videos, titles, formats and upload patterns",
  },
  {
    title: "Learning your niche",
    detail: "Audience, core topics and useful adjacent territory",
  },
  {
    title: "Building search lanes",
    detail: "Concrete English-language searches instead of broad AI topics",
  },
  {
    title: "Starting monitoring",
    detail: "New evidence will begin flowing into Today automatically",
  },
];

export default function OnboardingPage() {
  const queryClient = useQueryClient();
  const started = useRef(false);
  const [channelInput, setChannelInput] = useState(() => {
    if (typeof window === "undefined") return "";
    return (
      window.sessionStorage.getItem("earlysignal_pending_channel")?.trim() ?? ""
    );
  });
  const [analysisStage, setAnalysisStage] = useState(0);
  const query = useQuery<OnboardingData>({
    queryKey: ["onboarding-simple"],
    queryFn: async () => {
      const context = await getDemoContext();
      const onboarding = await getOnboardingStatus(context.workspace_id);
      return { context, onboarding };
    },
  });

  useEffect(() => {
    if (!query.data || started.current) return;
    started.current = true;
    window.sessionStorage.setItem(
      "earlysignal_onboarding_started_at",
      String(Date.now()),
    );
    void trackProductEvent(query.data.context.workspace_id, {
      event_type: "onboarding_started",
      event_key: `onboarding-started:${createClientEventId()}`,
      metadata: { version: "onboarding-zero-config-v1" },
    }).catch(() => undefined);
  }, [query.data]);

  const setupMutation = useMutation({
    mutationFn: (youtubeChannel: string) =>
      autoSetupOnboarding(query.data!.context.workspace_id, youtubeChannel),
    onMutate: () => setAnalysisStage(0),
    onSuccess: async (onboarding) => {
      window.sessionStorage.removeItem("earlysignal_pending_channel");
      setAnalysisStage(analysisStages.length - 1);
      queryClient.setQueryData<DemoContext>(["workspace-context"], (current) =>
        current
          ? {
              ...current,
              onboarding_status: onboarding.status,
            }
          : current,
      );
      await queryClient.invalidateQueries({
        queryKey: ["onboarding-simple"],
      });
      await queryClient.invalidateQueries({ queryKey: ["workspace-context"] });
      void trackProductEvent(query.data!.context.workspace_id, {
        event_type: "onboarding_step_completed",
        event_key: `onboarding-auto:${createClientEventId()}`,
        metadata: {
          step: "automatic_channel_analysis",
          version: "onboarding-zero-config-v1",
        },
      }).catch(() => undefined);
    },
  });

  useEffect(() => {
    const data = query.data;
    if (
      data?.onboarding.status !== "completed" ||
      !data.onboarding.owned_channel
    ) {
      return;
    }
    queryClient.setQueryData<DemoContext>(["workspace-context"], (current) => ({
      ...(current ?? data.context),
      onboarding_status: "completed",
    }));
  }, [query.data, queryClient]);

  useEffect(() => {
    if (!setupMutation.isPending) return;
    const timer = window.setInterval(() => {
      setAnalysisStage((current) =>
        Math.min(current + 1, analysisStages.length - 1),
      );
    }, 3_500);
    return () => window.clearInterval(timer);
  }, [setupMutation.isPending]);

  if (query.isLoading)
    return <PageLoading label="Preparing your channel setup" />;
  if (query.isError)
    return (
      <ErrorState message={query.error.message} retry={() => query.refetch()} />
    );
  if (!query.data) return null;

  const { onboarding } = query.data;
  const owned = onboarding.owned_channel;
  const ready = onboarding.status === "completed" && Boolean(owned);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = channelInput.trim() || owned?.canonical_url || "";
    if (!value) return;
    setupMutation.mutate(value);
  }

  return (
    <div className="mx-auto min-h-screen max-w-[1040px] px-5 py-10 sm:px-8 sm:py-16">
      <header className="mx-auto max-w-[760px] text-center">
        <div className="mx-auto grid h-11 w-11 place-items-center rounded-full bg-[var(--lime-soft)] text-[var(--lime-ink)]">
          <Youtube size={20} aria-hidden="true" />
        </div>
        <p className="mt-5 text-[11px] font-semibold tracking-[0.14em] text-[var(--lime-ink)] uppercase">
          One step. No settings required.
        </p>
        <h1 className="editorial mt-3 text-[42px] leading-[1.05] sm:text-[58px]">
          Paste your YouTube channel.
          <br />
          We’ll do the rest.
        </h1>
        <p className="mx-auto mt-5 max-w-[620px] text-[14px] leading-7 text-[var(--muted)]">
          EarlySignal reads public channel history, learns what fits your
          audience and creates a diverse set of narrow trend searches. No
          password or YouTube permissions.
        </p>
      </header>

      <main className="mx-auto mt-10 max-w-[820px]">
        {setupMutation.isPending ? (
          <section
            className="border border-[var(--line-strong)] bg-white p-6 sm:p-9"
            aria-live="polite"
          >
            <div className="flex items-start gap-4">
              <LoaderCircle
                className="mt-1 animate-spin text-[var(--lime-ink)]"
                size={22}
                aria-hidden="true"
              />
              <div>
                <p className="text-[10px] font-semibold tracking-[0.14em] uppercase">
                  Analyzing channel
                </p>
                <h2 className="editorial mt-2 text-[32px]">
                  {analysisStages[analysisStage].title}
                </h2>
                <p className="mt-2 text-[12px] leading-6 text-[var(--muted)]">
                  {analysisStages[analysisStage].detail}
                </p>
              </div>
            </div>
            <ol className="mt-8 grid gap-3 sm:grid-cols-4">
              {analysisStages.map((stage, index) => (
                <li
                  key={stage.title}
                  className={`border-t-2 pt-3 text-[11px] leading-5 ${
                    index <= analysisStage
                      ? "border-[var(--ink)] text-[var(--ink)]"
                      : "border-[var(--line)] text-[var(--muted)]"
                  }`}
                >
                  {index < analysisStage ? (
                    <Check className="mb-2" size={14} aria-hidden="true" />
                  ) : index === analysisStage ? (
                    <span className="mb-2 block h-3.5 w-3.5 rounded-full bg-[var(--lime-strong)]" />
                  ) : (
                    <span className="mb-2 block h-3.5 w-3.5 rounded-full border border-[var(--line-strong)]" />
                  )}
                  {stage.title}
                </li>
              ))}
            </ol>
          </section>
        ) : (
          <section className="border border-[var(--line-strong)] bg-white p-6 sm:p-9">
            {ready ? (
              <div className="mb-8 flex flex-col gap-5 border-b border-[var(--line)] pb-8 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="flex items-center gap-2 text-[10px] font-semibold tracking-[0.12em] text-[var(--lime-ink)] uppercase">
                    <Check size={14} aria-hidden="true" />
                    Channel connected
                  </p>
                  <h2 className="editorial mt-2 text-[34px]">{owned?.title}</h2>
                  <p className="mt-2 text-[12px] text-[var(--muted)]">
                    {onboarding.active_query_count} focused searches ·{" "}
                    {onboarding.reference_channel_count} reference channels
                  </p>
                </div>
                <a
                  href="/today"
                  className="inline-flex h-11 items-center justify-center gap-2 bg-[var(--ink)] px-5 text-[12px] font-semibold !text-white"
                >
                  Open Today <ArrowRight size={15} aria-hidden="true" />
                </a>
              </div>
            ) : null}

            <div className="flex items-start gap-3">
              {ready ? (
                <Sparkles
                  className="mt-1 text-[var(--lime-ink)]"
                  size={20}
                  aria-hidden="true"
                />
              ) : (
                <Search
                  className="mt-1 text-[var(--lime-ink)]"
                  size={20}
                  aria-hidden="true"
                />
              )}
              <div>
                <h2 className="editorial text-[30px]">
                  {ready
                    ? "Want fresher recommendations?"
                    : "Which channel should we learn?"}
                </h2>
                <p className="mt-2 text-[12px] leading-6 text-[var(--muted)]">
                  {ready
                    ? "Run the analysis again after your channel focus changes. Existing manual settings stay untouched."
                    : "A channel URL or @handle is enough. Profile, reference channels and search directions are automatic."}
                </p>
              </div>
            </div>

            {setupMutation.error ? (
              <p
                className="mt-6 border-l-2 border-[var(--coral)] pl-3 text-[12px] leading-6 text-[var(--coral)]"
                role="alert"
              >
                {setupMutation.error.message}
              </p>
            ) : null}

            <form
              className="mt-7 flex flex-col gap-3 sm:flex-row"
              onSubmit={submit}
            >
              <label className="sr-only" htmlFor="youtube-channel">
                YouTube channel URL or handle
              </label>
              <input
                id="youtube-channel"
                value={channelInput}
                onChange={(event) => setChannelInput(event.target.value)}
                placeholder={owned?.canonical_url || "youtube.com/@yourchannel"}
                className="h-13 min-w-0 flex-1 border border-[var(--line-strong)] bg-white px-4 text-[14px] transition outline-none focus:border-[var(--ink)]"
                autoComplete="url"
              />
              <button
                type="submit"
                disabled={!channelInput.trim() && !owned}
                className="inline-flex h-13 shrink-0 items-center justify-center gap-2 bg-[var(--ink)] px-6 text-[12px] font-semibold !text-white transition hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
              >
                {ready ? "Re-analyze channel" : "Analyze my channel"}
                <ArrowRight size={15} aria-hidden="true" />
              </button>
            </form>

            <p className="mt-4 text-[10px] leading-5 text-[var(--muted)]">
              Public data only. You can fine-tune topics and production limits
              later in Settings—but you do not need to do it now.
            </p>
          </section>
        )}

        <div className="mt-5 grid gap-px overflow-hidden border border-[var(--line)] bg-[var(--line)] sm:grid-cols-3">
          {[
            ["01", "Channel-specific", "Searches follow your actual audience."],
            [
              "02",
              "More diverse",
              "Multiple narrow lanes replace two broad topics.",
            ],
            [
              "03",
              "Always updating",
              "Weak searches are measured and replaced.",
            ],
          ].map(([number, title, detail]) => (
            <div className="bg-[var(--paper)] p-5" key={number}>
              <p className="text-[11px] font-semibold tracking-[0.14em] text-[var(--muted)]">
                {number}
              </p>
              <p className="mt-2 text-[12px] font-semibold">{title}</p>
              <p className="mt-1 text-[10px] leading-5 text-[var(--muted)]">
                {detail}
              </p>
            </div>
          ))}
        </div>
      </main>
    </div>
  );
}
