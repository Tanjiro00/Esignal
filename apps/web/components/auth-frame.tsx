import { Check } from "lucide-react";
import Link from "next/link";

import { LogoMark } from "@/components/logo";

const benefits = [
  "Specific YouTube opportunities, not broad trend lists",
  "Recommendations calibrated to your channel and production limits",
  "Every claim linked to stored evidence",
];

export function AuthFrame({
  children,
  mode,
}: {
  children: React.ReactNode;
  mode: "login" | "register";
}) {
  return (
    <main className="grid min-h-screen bg-white lg:grid-cols-[minmax(0,1.05fr)_minmax(460px,0.95fr)]">
      <section className="flex min-h-[330px] flex-col justify-between border-b border-[var(--line)] bg-[var(--surface-subtle)] px-6 py-7 sm:px-10 lg:min-h-screen lg:border-r lg:border-b-0 lg:px-14 lg:py-10">
        <Link
          aria-label="EarlySignal"
          className="flex items-center gap-3"
          href="/"
        >
          <LogoMark />
          <span className="text-[20px] font-semibold tracking-[-0.04em]">
            EarlySignal
          </span>
        </Link>

        <div className="max-w-[660px] py-12 lg:py-20">
          <h1 className="editorial max-w-[620px] text-[46px] leading-[0.98] sm:text-[64px] lg:text-[76px]">
            Find the right video before everyone makes it.
          </h1>
          <p className="mt-7 max-w-[570px] text-[15px] leading-7 text-[var(--muted)]">
            EarlySignal turns emerging YouTube evidence into a clear decision:
            act, watch or skip — for your channel.
          </p>
          <ul className="mt-9 grid gap-4">
            {benefits.map((benefit) => (
              <li
                className="flex items-start gap-3 text-[13px] leading-6"
                key={benefit}
              >
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-[var(--lime-soft)] text-[var(--lime-ink)]">
                  <Check size={12} strokeWidth={2.2} />
                </span>
                {benefit}
              </li>
            ))}
          </ul>
        </div>

        <p className="text-[10px] leading-5 text-[var(--muted)]">
          YouTube-first creator intelligence · English AI and technology
        </p>
      </section>

      <section className="flex items-center justify-center px-6 py-12 sm:px-10 lg:px-14">
        <div className="w-full max-w-[470px]">
          <p className="text-[11px] font-semibold tracking-[0.12em] text-[var(--lime-ink)] uppercase">
            {mode === "login" ? "Welcome back" : "Start with your channel"}
          </p>
          <h2 className="editorial mt-3 text-[42px] leading-tight sm:text-[52px]">
            {mode === "login" ? "Sign in" : "Create your workspace"}
          </h2>
          <p className="mt-3 text-[13px] leading-6 text-[var(--muted)]">
            {mode === "login"
              ? "Continue where your team left off."
              : "Connect one YouTube channel and get your first calibrated opportunity."}
          </p>
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </main>
  );
}
