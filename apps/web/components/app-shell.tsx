"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BarChart3,
  ChevronDown,
  FileText,
  LogOut,
  Radar,
  Settings,
  ShieldCheck,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { LogoMark } from "@/components/logo";
import { ErrorState, PageLoading } from "@/components/ui";
import { ApiError, getDemoContext, logoutAccount } from "@/lib/api";

const primary = [
  { label: "Today", href: "/today", icon: Sparkles },
  { label: "Library", href: "/opportunities", icon: Radar },
  {
    label: "Video plans",
    mobileLabel: "Plans",
    href: "/briefs",
    icon: FileText,
  },
  {
    label: "Performance",
    mobileLabel: "Performance",
    href: "/results",
    icon: BarChart3,
  },
  { label: "Settings", href: "/settings", icon: Settings },
];

const admin = [
  { label: "Review", href: "/admin/review" },
  { label: "Evaluation", href: "/admin/evaluation" },
  { label: "UX analytics", href: "/admin/ux" },
  { label: "Operations", href: "/admin/operations" },
  { label: "Queries", href: "/admin/queries" },
  { label: "Providers", href: "/admin/providers" },
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const queryClient = useQueryClient();
  const isPublic =
    pathname === "/" || pathname === "/login" || pathname === "/register";
  const isOnboarding = pathname === "/onboarding";
  const contextQuery = useQuery({
    queryKey: ["workspace-context"],
    queryFn: getDemoContext,
    enabled: !isPublic,
    retry: false,
  });
  const context = contextQuery.data;
  const logoutMutation = useMutation({
    mutationFn: logoutAccount,
    onSettled: () => {
      queryClient.clear();
      window.location.assign("/login");
    },
  });

  useEffect(() => {
    if (
      !isPublic &&
      contextQuery.error instanceof ApiError &&
      contextQuery.error.status === 401
    ) {
      const next = pathname === "/" ? "/today" : pathname;
      router.replace(`/login?next=${encodeURIComponent(next)}`);
    }
  }, [contextQuery.error, isPublic, pathname, router]);

  useEffect(() => {
    if (context && context.onboarding_status !== "completed" && !isOnboarding) {
      router.replace("/onboarding");
    }
  }, [context, isOnboarding, router]);

  if (isPublic) {
    return <>{children}</>;
  }
  if (contextQuery.isLoading || !context) {
    if (contextQuery.isError) {
      if (
        contextQuery.error instanceof ApiError &&
        contextQuery.error.status === 401
      ) {
        return <PageLoading label="Opening secure sign in" />;
      }
      return (
        <ErrorState
          message={contextQuery.error.message}
          retry={() => contextQuery.refetch()}
        />
      );
    }
    return <PageLoading label="Opening your workspace" />;
  }
  if (isOnboarding) {
    return <div className="min-h-screen bg-[var(--canvas)]">{children}</div>;
  }

  const workspaceName = context?.workspace_name ?? "Workspace";
  const initials = workspaceName
    .split(/\s+/)
    .slice(0, 2)
    .map((word) => word[0])
    .join("")
    .toUpperCase();

  return (
    <div className="min-h-screen bg-[var(--canvas)]">
      <a className="skip-link" href="#main-content">
        Skip to main content
      </a>
      <header className="fixed inset-x-0 top-0 z-40 flex h-[var(--topbar)] items-center justify-between border-b border-[var(--line)] bg-white/90 px-4 backdrop-blur-xl lg:hidden">
        <Link
          aria-label="EarlySignal Today"
          className="flex items-center gap-2.5"
          href="/today"
        >
          <LogoMark />
          <span className="text-[17px] font-semibold tracking-[-0.035em]">
            EarlySignal
          </span>
        </Link>
        <Link
          aria-label={`Open account settings for ${workspaceName}`}
          className="grid h-9 w-9 place-items-center rounded-full bg-[var(--ink)] text-[10px] font-semibold !text-white shadow-sm transition-transform duration-200 hover:scale-105"
          href="/settings#account"
        >
          {initials}
        </Link>
      </header>

      <aside className="fixed inset-y-0 left-0 z-30 hidden w-[var(--sidebar)] flex-col border-r border-[var(--line)] bg-white px-4 py-6 lg:flex">
        <Link
          aria-label="EarlySignal Today"
          className="mb-10 flex h-7 items-center gap-2.5 px-2"
          href="/today"
        >
          <LogoMark />
          <span className="text-[18px] font-semibold tracking-[-0.035em]">
            EarlySignal
          </span>
        </Link>

        <nav aria-label="Primary navigation">
          {primary.map((item) => {
            const Icon = item.icon;
            const active =
              pathname.startsWith(item.href) ||
              (item.href === "/opportunities" &&
                pathname.startsWith("/signals")) ||
              (item.href === "/results" && pathname.startsWith("/outcomes"));
            return (
              <Link
                aria-current={active ? "page" : undefined}
                className={`relative mb-1 flex min-h-11 items-center gap-3 rounded-xl px-3 pl-5 text-[14px] transition-[transform,background-color,color] duration-200 ease-out hover:translate-x-0.5 ${
                  active
                    ? "bg-[var(--lime-soft)] font-semibold text-[var(--ink)]"
                    : "text-[var(--muted)] hover:bg-[var(--surface-subtle)] hover:text-[var(--ink)]"
                }`}
                href={item.href}
                key={item.href}
              >
                {active ? (
                  <span className="absolute left-2 h-2 w-2 rounded-full bg-[var(--lime-strong)] shadow-[0_0_0_4px_rgb(189_219_69_/_18%)]" />
                ) : null}
                <Icon aria-hidden="true" size={17} strokeWidth={1.7} />
                {item.label}
              </Link>
            );
          })}
        </nav>

        {context?.is_admin ? (
          <details className="mt-7 border-t border-[var(--line)] pt-4">
            <summary className="flex min-h-11 cursor-pointer list-none items-center gap-3 px-3 text-[12px] font-medium text-[var(--muted)]">
              <ShieldCheck size={16} /> Admin tools
            </summary>
            <nav aria-label="Admin navigation" className="mt-1 pl-8">
              {admin.map((item) => (
                <Link
                  className={`block min-h-9 py-2 text-[12px] ${
                    pathname.startsWith(item.href)
                      ? "font-semibold text-[var(--ink)]"
                      : "text-[var(--muted)] hover:text-[var(--ink)]"
                  }`}
                  href={item.href}
                  key={item.href}
                >
                  {item.label}
                </Link>
              ))}
            </nav>
          </details>
        ) : null}

        <div className="mt-auto">
          {context?.demo ? (
            <p className="mb-4 border-l-2 border-[var(--lime-strong)] pl-3 text-[10px] leading-5 text-[var(--muted)]">
              Demo workspace · synthetic evidence is isolated from live data.
            </p>
          ) : null}
          <details className="soft-disclosure group border-t border-[var(--line)] pt-3">
            <summary className="flex min-h-12 cursor-pointer list-none items-center gap-3 px-2">
              <span className="grid h-9 w-9 shrink-0 place-items-center rounded-full bg-[var(--ink)] text-[11px] font-semibold text-white">
                {initials}
              </span>
              <span className="min-w-0 flex-1 text-[11px]">
                <strong className="block truncate font-medium">
                  {context.user_name}
                </strong>
                <span className="mt-1 block truncate text-[var(--muted)]">
                  {workspaceName}
                </span>
              </span>
              <ChevronDown
                aria-hidden="true"
                className="transition-transform group-open:rotate-180"
                size={14}
              />
            </summary>
            <div className="mt-2 rounded-xl border border-[var(--line)] bg-white p-3 shadow-[var(--shadow-soft)]">
              <p className="truncate text-[10px] text-[var(--muted)]">
                {context.user_email}
              </p>
              <Link
                className="mt-3 flex min-h-10 items-center gap-2 border-t border-[var(--line)] pt-3 text-[11px] font-medium"
                href="/settings#account"
              >
                <Settings size={14} /> Account settings
              </Link>
              <button
                className="flex min-h-10 w-full items-center gap-2 text-left text-[11px] font-medium text-[var(--coral)]"
                disabled={logoutMutation.isPending}
                onClick={() => logoutMutation.mutate()}
                type="button"
              >
                <LogOut size={14} />
                {logoutMutation.isPending ? "Signing out…" : "Sign out"}
              </button>
            </div>
          </details>
        </div>
      </aside>

      <main
        className="min-h-screen px-0 pt-[var(--topbar)] pb-20 lg:pt-0 lg:pb-0 lg:pl-[var(--sidebar)]"
        id="main-content"
      >
        {children}
      </main>

      <nav
        aria-label="Primary navigation"
        className="fixed inset-x-0 bottom-0 z-40 grid h-[calc(68px+env(safe-area-inset-bottom))] grid-cols-5 border-t border-[var(--line)] bg-white/90 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_28px_rgb(31_36_34_/_7%)] backdrop-blur-xl lg:hidden"
      >
        {primary.map((item) => {
          const Icon = item.icon;
          const active =
            pathname.startsWith(item.href) ||
            (item.href === "/opportunities" &&
              pathname.startsWith("/signals")) ||
            (item.href === "/results" && pathname.startsWith("/outcomes"));
          return (
            <Link
              aria-current={active ? "page" : undefined}
              className={`relative flex min-h-14 flex-col items-center justify-center gap-1 text-[10px] font-medium transition-[transform,color] duration-200 active:scale-95 ${
                active ? "text-[var(--ink)]" : "text-[var(--muted)]"
              }`}
              href={item.href}
              key={item.href}
            >
              <Icon
                aria-hidden="true"
                className={active ? "text-[var(--lime-strong)]" : undefined}
                size={19}
                strokeWidth={active ? 2 : 1.5}
              />
              {"mobileLabel" in item ? item.mobileLabel : item.label}
              {active ? (
                <span className="absolute bottom-1 h-1 w-5 rounded-full bg-[var(--lime-strong)]" />
              ) : null}
            </Link>
          );
        })}
      </nav>
    </div>
  );
}
