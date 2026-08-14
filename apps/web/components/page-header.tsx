export function PageHeader({
  title,
  description,
  aside,
}: {
  title: string;
  description: string;
  aside?: React.ReactNode;
}) {
  return (
    <header className="mb-8 flex flex-col items-start justify-between gap-5 border-b border-[var(--line)] pb-6 sm:flex-row sm:items-end sm:gap-6">
      <div className="min-w-0">
        <h1 className="editorial text-[36px] leading-none sm:text-[42px]">
          {title}
        </h1>
        <p className="mt-3 text-[11px] text-[var(--muted)]">{description}</p>
      </div>
      {aside ? <div className="w-full sm:w-auto">{aside}</div> : null}
    </header>
  );
}
