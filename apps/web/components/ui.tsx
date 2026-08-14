import clsx from "clsx";
import { ArrowUpRight } from "lucide-react";
import Link from "next/link";

export function Button({
  children,
  className,
  variant = "secondary",
  ...props
}: React.ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return (
    <button
      className={clsx(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border px-3 text-center text-[13px] leading-tight font-medium whitespace-normal transition-[transform,box-shadow,background-color,border-color,color] duration-200 ease-out hover:-translate-y-px active:translate-y-0 disabled:translate-y-0 disabled:cursor-not-allowed disabled:opacity-45",
        variant === "primary" &&
          "border-[var(--ink)] bg-[var(--ink)] !text-white shadow-[0_8px_18px_rgb(31_36_34_/_14%)] hover:bg-black hover:shadow-[0_10px_22px_rgb(31_36_34_/_20%)] disabled:!text-white",
        variant === "secondary" &&
          "border-[var(--line-strong)] bg-white hover:border-[var(--ink)] hover:shadow-sm",
        variant === "ghost" &&
          "border-transparent bg-transparent hover:bg-[var(--surface-subtle)]",
        variant === "danger" &&
          "border-[var(--coral)] bg-white text-[var(--coral)] hover:bg-red-50",
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function LinkButton({
  children,
  href,
  className,
}: {
  children: React.ReactNode;
  href: string;
  className?: string;
}) {
  return (
    <Link
      className={clsx(
        "inline-flex min-h-10 items-center justify-center gap-2 rounded-xl border border-[var(--ink)] bg-[var(--ink)] px-3 text-center text-[13px] leading-tight font-medium whitespace-normal !text-white shadow-[0_8px_18px_rgb(31_36_34_/_14%)] transition-[transform,box-shadow,background-color] duration-200 ease-out hover:-translate-y-px hover:bg-black hover:shadow-[0_10px_22px_rgb(31_36_34_/_20%)] active:translate-y-0",
        className,
      )}
      href={href}
    >
      {children}
      <ArrowUpRight size={14} strokeWidth={1.6} />
    </Link>
  );
}

export function StatusDot({
  tone = "healthy",
}: {
  tone?: "healthy" | "warning" | "risk" | "neutral";
}) {
  return (
    <span
      aria-hidden="true"
      className={clsx(
        "inline-block h-2 w-2 shrink-0 rounded-full",
        tone === "healthy" && "bg-[var(--lime-strong)]",
        tone === "warning" && "bg-[var(--amber)]",
        tone === "risk" && "bg-[var(--coral)]",
        tone === "neutral" && "bg-[var(--faint)]",
      )}
    />
  );
}

export function PageLoading({
  label = "Loading evidence",
}: {
  label?: string;
}) {
  return (
    <div className="mx-auto max-w-[1240px] px-6 py-10">
      <p className="mb-5 text-[11px] tracking-[0.12em] text-[var(--muted)] uppercase">
        {label}
      </p>
      <div className="skeleton mb-3 h-12 w-2/5" />
      <div className="skeleton mb-10 h-4 w-1/3" />
      <div className="space-y-2">
        {[1, 2, 3, 4].map((item) => (
          <div className="skeleton h-32 w-full" key={item} />
        ))}
      </div>
    </div>
  );
}

export function ErrorState({
  message,
  retry,
}: {
  message: string;
  retry?: () => void;
}) {
  return (
    <div className="mx-auto max-w-[900px] px-6 py-24">
      <p className="editorial text-3xl">Evidence could not be loaded.</p>
      <p className="mt-3 max-w-xl text-sm leading-relaxed text-[var(--muted)]">
        {message}
      </p>
      {retry && (
        <Button className="mt-6" onClick={retry}>
          Try again
        </Button>
      )}
    </div>
  );
}
