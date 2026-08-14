import {
  ArrowRight,
  Check,
  ExternalLink,
  LockKeyhole,
  Play,
  X,
} from "lucide-react";
import Link from "next/link";

import { LogoMark } from "@/components/logo";
import { LandingMotion } from "@/components/landing/landing-motion";

const workflow = [
  {
    number: "01",
    title: "Learn your channel",
    copy: "We read public upload history, recurring topics and the formats your audience already responds to.",
  },
  {
    number: "02",
    title: "Watch the edges",
    copy: "Focused searches monitor narrow conversations across relevant channels—not broad trend charts.",
  },
  {
    number: "03",
    title: "Make the call",
    copy: "You get a topic, timing window, content gap and direct links to the evidence behind it.",
  },
] as const;

const questions = [
  {
    number: "01",
    question: "Is this actually rising?",
    answer: "See velocity, spread and lifecycle—not a popularity snapshot.",
  },
  {
    number: "02",
    question: "Does it fit my channel?",
    answer:
      "Recommendations are ranked against your topics, audience and production reality.",
  },
  {
    number: "03",
    question: "Is there still room?",
    answer:
      "Open the content gap, evidence and source links before committing.",
  },
] as const;

const evidenceRows = [
  "The topic is moving beyond isolated experiments.",
  "Coverage spans eight independent creator channels.",
  "Audience demand clusters around practical use and recurring objections.",
] as const;

function Brand({ light = false }: { light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5">
      <LogoMark size={27} />
      <span
        className={`text-[18px] font-semibold tracking-[-0.04em] ${light ? "text-white" : "text-[var(--ink)]"}`}
      >
        EarlySignal
      </span>
    </span>
  );
}

function SignalWave() {
  return (
    <svg
      aria-hidden="true"
      className="landing-signal-line h-12 w-full"
      preserveAspectRatio="none"
      viewBox="0 0 640 48"
    >
      <path
        d="M0 24h436l9-5 7 17 10-28 10 38 10-31 9 20 10-11h139"
        fill="none"
        pathLength="1"
        stroke="var(--landing-lime)"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

function ProductPreview() {
  return (
    <div className="landing-product-stack relative mx-auto w-full max-w-[690px] lg:mx-0">
      <div className="absolute top-8 right-0 bottom-[-22px] left-12 border border-black/20 bg-white" />
      <div className="landing-float relative grid min-h-[510px] grid-cols-1 overflow-hidden border border-black/50 bg-white shadow-[0_26px_60px_rgb(19_23_20_/_14%)] sm:grid-cols-[150px_minmax(0,1fr)]">
        <aside className="hidden flex-col border-r border-[var(--line)] px-5 py-5 sm:flex">
          <Brand />
          <nav className="mt-8 space-y-1 text-[10px] sm:text-[12px]">
            <span className="block bg-[var(--ink)] px-3 py-2.5 font-medium text-white">
              Today
            </span>
            <span className="block px-3 py-2.5 text-[var(--muted)]">
              Library
            </span>
            <span className="block px-3 py-2.5 text-[var(--muted)]">
              Video plans
            </span>
          </nav>
          <span className="mt-auto px-3 text-[10px] text-[var(--muted)]">
            Evidence mode
          </span>
        </aside>

        <div className="min-w-0 p-4 sm:p-6">
          <div className="flex items-start justify-between border-b border-[var(--line)] pb-4">
            <div>
              <p className="editorial text-[27px] leading-none sm:text-[34px]">
                Today
              </p>
              <p className="mt-2 text-[9px] text-[var(--muted)] sm:text-[11px]">
                What needs your decision?
              </p>
            </div>
            <span className="text-[9px] text-[var(--muted)] sm:text-[10px]">
              Stored example
            </span>
          </div>

          <article className="mt-5 border-l-2 border-[var(--landing-lime)] bg-[#fbfdf5] p-4 sm:p-5">
            <div className="flex flex-col gap-4 sm:flex-row sm:justify-between">
              <div className="max-w-[320px]">
                <p className="text-[9px] font-semibold tracking-[0.12em] text-[var(--lime-ink)] uppercase">
                  Emerging signal
                </p>
                <h2 className="editorial mt-2 text-[24px] leading-[1.05] sm:text-[31px]">
                  Free, local and unlimited AI video generation
                </h2>
              </div>
              <div className="shrink-0 sm:text-right">
                <span className="editorial block text-[42px] leading-none sm:text-[54px]">
                  71
                </span>
                <span className="text-[9px] text-[var(--lime-ink)]">
                  EarlySignal score
                </span>
              </div>
            </div>

            <div className="mt-5 grid grid-cols-2 gap-4 border-y border-[var(--line)] py-4 text-[10px] sm:grid-cols-3 sm:text-[11px]">
              <span>
                <strong className="block text-[15px] font-medium">26</strong>
                evidence videos
              </span>
              <span>
                <strong className="block text-[15px] font-medium">8</strong>
                channels
              </span>
              <span className="col-span-2 sm:col-span-1">
                <strong className="block text-[15px] font-medium">
                  Emerging
                </strong>
                lifecycle
              </span>
            </div>

            <div className="mt-4">
              <p className="text-[10px] font-semibold sm:text-[11px]">
                Why this is worth reviewing
              </p>
              <p className="mt-2 text-[10px] leading-5 text-[var(--muted)] sm:text-[11px]">
                Evidence is spreading across independent channels while audience
                questions converge on practical limitations and cost.
              </p>
            </div>

            <div className="mt-5 flex items-center justify-between border-t border-[var(--line)] pt-4 text-[10px] font-medium sm:text-[11px]">
              <span>Open evidence</span>
              <ArrowRight aria-hidden="true" size={15} />
            </div>
          </article>
        </div>
      </div>
    </div>
  );
}

function WorkflowPanels() {
  return (
    <div className="mt-12 grid border-y border-[var(--line-strong)] lg:grid-cols-3">
      <article
        className="border-b border-[var(--line)] p-5 sm:p-7 lg:border-r lg:border-b-0"
        data-reveal="up"
        data-reveal-order="1"
      >
        <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
          Channel URL
        </p>
        <div className="mt-4 flex border border-[var(--line-strong)]">
          <span className="min-w-0 flex-1 truncate px-3 py-3 text-[10px] text-[var(--muted)] sm:text-[11px]">
            youtube.com/@yourchannel
          </span>
          <span className="grid w-11 place-items-center bg-[var(--ink)] text-white">
            <ArrowRight size={15} />
          </span>
        </div>
        <div className="mt-5 space-y-3 text-[11px]">
          {["Upload history", "Recurring topics", "Format patterns"].map(
            (label) => (
              <div
                className="flex items-center justify-between border-b border-[var(--line)] pb-3"
                key={label}
              >
                <span>{label}</span>
                <Check className="text-[var(--lime-strong)]" size={14} />
              </div>
            ),
          )}
        </div>
      </article>

      <article
        className="border-b border-[var(--line)] p-5 sm:p-7 lg:border-r lg:border-b-0"
        data-reveal="up"
        data-reveal-order="2"
      >
        <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
          Focused searches
        </p>
        <div className="mt-4 space-y-2">
          {[
            "Local AI video limits",
            "Open models on owned hardware",
            "Independent AI benchmarks",
          ].map((label, index) => (
            <div
              className="flex items-center gap-3 border-l-2 border-[var(--landing-lime)] bg-[var(--surface-subtle)] px-3 py-3"
              key={label}
            >
              <span className="mono text-[9px] text-[var(--muted)]">
                0{index + 1}
              </span>
              <span className="text-[11px]">{label}</span>
            </div>
          ))}
        </div>
        <p className="mt-5 text-[10px] leading-5 text-[var(--muted)]">
          Narrow lanes replace one broad “AI trends” query.
        </p>
      </article>

      <article className="p-5 sm:p-7" data-reveal="up" data-reveal-order="3">
        <div className="flex items-center justify-between border-b border-[var(--line)] pb-4">
          <p className="text-[10px] font-semibold tracking-[0.12em] uppercase">
            Today
          </p>
          <span className="text-[9px] text-[var(--lime-ink)]">
            Best fit first
          </span>
        </div>
        <h3 className="editorial mt-5 text-[25px] leading-[1.08]">
          A specific topic, with room to add something new.
        </h3>
        <dl className="mt-6 space-y-3 text-[10px]">
          <div className="flex justify-between border-b border-[var(--line)] pb-3">
            <dt className="text-[var(--muted)]">Timing</dt>
            <dd>Evidence window</dd>
          </div>
          <div className="flex justify-between border-b border-[var(--line)] pb-3">
            <dt className="text-[var(--muted)]">Content gap</dt>
            <dd>Unanswered question</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-[var(--muted)]">Sources</dt>
            <dd>Direct links</dd>
          </div>
        </dl>
      </article>
    </div>
  );
}

export function LandingPage() {
  return (
    <div
      className="landing-page min-h-screen overflow-x-hidden bg-white text-[var(--ink)]"
      style={{ "--landing-lime": "#b8eb12" } as React.CSSProperties}
    >
      <LandingMotion />
      <header className="sticky top-0 z-50 border-b border-black/20 bg-white/92 backdrop-blur-xl">
        <div className="mx-auto flex h-[72px] max-w-[1480px] items-center justify-between px-5 sm:px-8 lg:px-12">
          <Link aria-label="EarlySignal home" href="/">
            <Brand />
          </Link>
          <nav
            aria-label="Landing page navigation"
            className="hidden items-center gap-8 text-[12px] md:flex"
          >
            <a className="hover:underline" href="#how-it-works">
              How it works
            </a>
            <a className="hover:underline" href="#evidence">
              Evidence
            </a>
            <a className="hover:underline" href="#for-creators">
              For creators
            </a>
          </nav>
          <div className="flex items-center gap-2 sm:gap-4">
            <Link
              className="hidden min-h-11 items-center px-2 text-[12px] font-medium sm:inline-flex"
              href="/login"
            >
              Sign in
            </Link>
            <Link
              className="inline-flex min-h-11 items-center gap-2 bg-[var(--ink)] px-4 text-[12px] font-semibold !text-white transition-transform hover:-translate-y-px sm:px-5"
              href="/register"
            >
              Start free <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </header>

      <main>
        <section className="landing-hero mx-auto grid max-w-[1480px] gap-12 px-5 pt-12 pb-12 sm:px-8 sm:pt-16 lg:grid-cols-2 lg:items-center lg:px-12 lg:pt-20 lg:pb-16">
          <div className="landing-enter max-w-[700px]">
            <h1 className="editorial text-[52px] leading-[0.91] sm:text-[72px] lg:text-[clamp(68px,5.7vw,92px)]">
              Know what to publish before the trend gets obvious.
            </h1>
            <div className="mt-5 max-w-[640px]">
              <SignalWave />
            </div>
            <p className="mt-5 max-w-[620px] text-[15px] leading-7 text-[var(--muted)] sm:text-[17px] sm:leading-8">
              EarlySignal finds narrow, rising YouTube topics that fit your
              channel—then shows the evidence, timing and content gap behind
              each recommendation.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <Link
                className="inline-flex min-h-13 items-center justify-center gap-3 bg-[var(--ink)] px-6 text-[13px] font-semibold !text-white transition-[transform,box-shadow] hover:-translate-y-0.5 hover:shadow-[0_14px_30px_rgb(31_36_34_/_18%)]"
                href="/register"
              >
                Analyze my channel <ArrowRight size={16} />
              </Link>
              <a
                className="inline-flex min-h-13 items-center justify-center border border-[var(--ink)] px-6 text-[13px] font-semibold transition-colors hover:bg-[var(--surface-subtle)]"
                href="#product"
              >
                See a live example
              </a>
            </div>
            <p className="mt-5 flex items-center gap-2 text-[11px] text-[var(--muted)]">
              <LockKeyhole aria-hidden="true" size={13} /> Public YouTube data.
              No channel permissions.
            </p>
          </div>

          <div className="landing-enter-delayed scroll-mt-28" id="product">
            <ProductPreview />
          </div>
        </section>

        <section
          aria-label="Product principles"
          className="mx-auto grid max-w-[1480px] border-y border-black/25 px-5 sm:grid-cols-3 sm:px-8 lg:px-12"
        >
          {[
            "Channel-specific",
            "Evidence on every claim",
            "Built for the next upload",
          ].map((item, index) => (
            <div
              className="flex items-center gap-5 border-b border-black/15 py-5 last:border-b-0 sm:border-r sm:border-b-0 sm:px-6 sm:first:pl-0 sm:last:border-r-0 sm:last:pr-0"
              data-reveal="up"
              data-reveal-order={index + 1}
              key={item}
            >
              <span className="mono text-[11px] text-[var(--muted)]">
                0{index + 1}
              </span>
              <span className="editorial text-[20px] sm:text-[22px]">
                {item}
              </span>
            </div>
          ))}
        </section>

        <section
          className="landing-section scroll-mt-24 px-5 py-20 sm:px-8 sm:py-28 lg:px-12"
          id="how-it-works"
        >
          <div className="mx-auto max-w-[1384px]">
            <h2
              className="editorial max-w-[1180px] text-[48px] leading-[0.96] sm:text-[68px] lg:text-[82px]"
              data-reveal="up"
            >
              From channel URL to next-video decision.
            </h2>
            <p
              className="mt-5 max-w-[720px] text-[14px] leading-7 text-[var(--muted)] sm:text-[16px]"
              data-reveal="up"
              data-reveal-order="1"
            >
              One input. Three layers of intelligence. Every recommendation
              stays traceable to source evidence.
            </p>

            <ol className="mt-12 grid gap-8 lg:grid-cols-3 lg:gap-0">
              {workflow.map((step, index) => (
                <li
                  className="relative border-t border-[var(--ink)] pt-6 lg:pr-10 lg:not-last:mr-10"
                  data-reveal="up"
                  data-reveal-order={index + 1}
                  key={step.number}
                >
                  <div className="flex items-start gap-5">
                    <span className="editorial text-[48px] leading-none text-[var(--lime-strong)]">
                      {step.number}
                    </span>
                    <div>
                      <h3 className="editorial text-[27px] leading-none sm:text-[31px]">
                        {step.title}
                      </h3>
                      <p className="mt-4 text-[12px] leading-6 text-[var(--muted)] sm:text-[13px]">
                        {step.copy}
                      </p>
                    </div>
                  </div>
                  {index < workflow.length - 1 ? (
                    <ArrowRight
                      aria-hidden="true"
                      className="absolute top-[-9px] right-0 hidden bg-white lg:block"
                      size={18}
                    />
                  ) : null}
                </li>
              ))}
            </ol>

            <WorkflowPanels />
          </div>
        </section>

        <section
          className="landing-section scroll-mt-20 bg-[#111311] px-5 py-20 text-white sm:px-8 sm:py-28 lg:px-12"
          id="evidence"
        >
          <div className="mx-auto max-w-[1384px]">
            <div className="grid gap-8 lg:grid-cols-[1.05fr_0.95fr] lg:items-end">
              <h2
                className="editorial max-w-[760px] text-[52px] leading-[0.94] sm:text-[72px] lg:text-[84px]"
                data-reveal="left"
              >
                Not a trend list. A decision system.
              </h2>
              <p
                className="max-w-[610px] text-[15px] leading-7 text-white/68 sm:text-[17px] sm:leading-8"
                data-reveal="up"
                data-reveal-order="1"
              >
                Broad topics are easy to find. The hard part is knowing whether
                a narrow shift fits your audience, is early enough to matter and
                leaves room for a distinct video.
              </p>
            </div>

            <div className="mt-14 grid gap-10 lg:grid-cols-2 lg:gap-16">
              <div data-reveal="left" data-reveal-order="1">
                <h3 className="text-[12px] font-semibold tracking-[0.12em] text-white/45 uppercase">
                  Most trend tools
                </h3>
                <ul className="mt-3">
                  {[
                    "Broad keywords",
                    "Popularity after the fact",
                    "No channel context",
                    "No source trail",
                  ].map((item) => (
                    <li
                      className="flex min-h-14 items-center gap-4 border-b border-white/18 text-[17px] text-white/48"
                      key={item}
                    >
                      <X aria-hidden="true" size={18} /> {item}
                    </li>
                  ))}
                </ul>
              </div>
              <div
                className="border-l border-[var(--landing-lime)] pl-6 lg:pl-12"
                data-reveal="right"
                data-reveal-order="2"
              >
                <h3 className="text-[12px] font-semibold tracking-[0.12em] text-[var(--landing-lime)] uppercase">
                  EarlySignal
                </h3>
                <ul className="mt-3">
                  {[
                    "Channel fit",
                    "Timing window",
                    "Uncovered audience question",
                    "Evidence links",
                  ].map((item) => (
                    <li
                      className="flex min-h-14 items-center gap-4 border-b border-white/18 text-[17px]"
                      key={item}
                    >
                      <Check
                        aria-hidden="true"
                        className="text-[var(--landing-lime)]"
                        size={18}
                      />
                      {item}
                    </li>
                  ))}
                </ul>
              </div>
            </div>

            <article
              className="mt-12 border border-white/28 px-4 py-5 sm:px-7 sm:py-7"
              data-reveal="scale"
            >
              <div className="flex flex-col gap-4 border-b border-white/25 pb-6 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h3 className="editorial text-[34px] sm:text-[46px]">
                    Why this is moving now
                  </h3>
                  <p className="mt-2 text-[13px] text-[var(--landing-lime)] sm:text-[15px]">
                    Free, local and unlimited AI video generation
                  </p>
                </div>
                <div className="sm:text-right">
                  <p className="text-[12px] text-white/68">
                    26 videos · 8 channels
                  </p>
                  <Link
                    className="mt-2 inline-flex items-center gap-2 text-[12px] font-medium text-[var(--landing-lime)]"
                    href="/register"
                  >
                    Open all evidence <ExternalLink size={14} />
                  </Link>
                </div>
              </div>
              <ol>
                {evidenceRows.map((summary, index) => (
                  <li
                    className="grid min-h-16 gap-2 border-b border-white/18 py-4 last:border-b-0 sm:grid-cols-[180px_1fr] sm:items-center"
                    key={summary}
                  >
                    <span className="flex items-center gap-3 text-[11px]">
                      <span className="grid h-7 w-7 place-items-center border border-white/40">
                        <Play aria-hidden="true" size={11} />
                      </span>
                      Evidence group 0{index + 1}
                    </span>
                    <span className="text-[12px] leading-6 text-white/70 sm:text-[13px]">
                      {summary}
                    </span>
                  </li>
                ))}
              </ol>
              <p className="mt-4 text-[9px] leading-5 text-white/42">
                Stored production snapshot, captured July 28, 2026. Claims stay
                attached to their underlying evidence records.
              </p>
            </article>
          </div>
        </section>

        <section
          className="landing-section scroll-mt-20 px-5 py-20 sm:px-8 sm:py-28 lg:px-12"
          id="for-creators"
        >
          <div className="mx-auto max-w-[1384px]">
            <span
              className="block h-0.5 w-9 bg-[var(--landing-lime)]"
              data-reveal="line"
            />
            <h2
              className="editorial mt-5 text-[46px] leading-[0.98] sm:text-[66px] lg:text-[76px]"
              data-reveal="up"
            >
              Built for the moment before obvious.
            </h2>
            <div className="mt-10 border-t border-[var(--line-strong)]">
              {questions.map((item) => (
                <article
                  className="grid gap-4 border-b border-[var(--line-strong)] py-7 sm:grid-cols-[70px_minmax(0,1fr)] lg:grid-cols-[80px_minmax(0,1fr)_420px] lg:items-center lg:py-10"
                  data-reveal="up"
                  data-reveal-order={Number(item.number)}
                  key={item.number}
                >
                  <span className="editorial text-[38px] text-[var(--lime-strong)] sm:text-[46px]">
                    {item.number}
                  </span>
                  <h3 className="editorial text-[35px] leading-[0.98] sm:text-[49px] lg:text-[58px]">
                    {item.question}
                  </h3>
                  <p className="text-[14px] leading-7 text-[var(--muted)] sm:col-start-2 lg:col-start-auto lg:text-[16px]">
                    {item.answer}
                  </p>
                </article>
              ))}
            </div>
          </div>
        </section>

        <section className="bg-[#111311] px-5 py-14 text-white sm:px-8 sm:py-18 lg:px-12">
          <div className="mx-auto max-w-[1384px]" data-reveal="up">
            <h2 className="editorial max-w-[980px] text-[42px] leading-[0.98] sm:text-[58px] lg:text-[68px]">
              Your next strong video is probably forming now.
            </h2>
            <p className="mt-4 text-[14px] text-white/68 sm:text-[16px]">
              Paste your channel once. EarlySignal keeps watching the edges.
            </p>
            <form
              action="/register"
              className="mt-7 flex max-w-[930px] flex-col gap-3 sm:flex-row"
              method="get"
            >
              <label className="sr-only" htmlFor="landing-channel">
                YouTube channel URL or handle
              </label>
              <input
                autoComplete="url"
                className="min-h-14 min-w-0 flex-1 border border-white/45 bg-transparent px-4 text-[14px] text-white placeholder:text-white/42 focus:border-[var(--landing-lime)] focus:outline-none"
                id="landing-channel"
                name="channel"
                placeholder="youtube.com/@yourchannel"
                type="text"
              />
              <button
                className="inline-flex min-h-14 items-center justify-center gap-3 bg-[var(--landing-lime)] px-8 text-[14px] font-semibold text-[#111311] transition-[transform,filter] hover:-translate-y-px hover:brightness-105"
                type="submit"
              >
                Start free <ArrowRight size={16} />
              </button>
            </form>
            <p className="mt-4 text-[11px] text-white/48">
              Public data only. No YouTube permissions required.
            </p>
          </div>
        </section>
      </main>

      <footer className="border-t border-black/20 bg-white px-5 py-8 sm:px-8 lg:px-12">
        <div className="mx-auto flex max-w-[1384px] flex-col gap-6 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:gap-6">
            <Brand />
            <span className="hidden h-8 w-px bg-[var(--line-strong)] sm:block" />
            <p className="text-[11px] text-[var(--muted)]">
              Evidence-backed creator intelligence.
            </p>
          </div>
          <nav className="flex flex-wrap gap-x-6 gap-y-3 text-[11px]">
            <a className="hover:underline" href="#how-it-works">
              How it works
            </a>
            <a className="hover:underline" href="#evidence">
              Evidence
            </a>
            <Link className="hover:underline" href="/login">
              Sign in
            </Link>
          </nav>
        </div>
      </footer>
    </div>
  );
}
