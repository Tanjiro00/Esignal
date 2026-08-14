import clsx from "clsx";

export function AuthField({
  label,
  hint,
  error,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string;
}) {
  return (
    <label className="block text-[12px] font-medium">
      {label}
      <input
        className={clsx(
          "mt-2 h-12 w-full border bg-white px-3 text-[14px] transition-colors outline-none",
          error
            ? "border-[var(--coral)] focus:border-[var(--coral)]"
            : "border-[var(--line-strong)] focus:border-[var(--ink)]",
        )}
        {...props}
      />
      {error ? (
        <span className="mt-2 block text-[11px] text-[var(--coral)]">
          {error}
        </span>
      ) : hint ? (
        <span className="mt-2 block text-[10px] leading-5 text-[var(--muted)]">
          {hint}
        </span>
      ) : null}
    </label>
  );
}
